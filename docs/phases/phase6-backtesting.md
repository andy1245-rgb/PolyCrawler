# Phase 6 — Backtesting

**Source:** spec.md §16.6, §17 | docs/architecture.md §12
**Status:** ⬜ Not started
**Prerequisites:** [Phase 3b](phase3b-paper-execution.md) complete (paper engine works)

---

## Goal

Replay historical scenarios against the paper engine to compare PnL under different configs. Validate the three scoring variants (A/B/C) against labeled wallets. This phase lets you answer "what min_buy / TP / SL / discovery threshold actually worked?" without risking capital or re-running live.

## Spec references

- spec §17 — Backtesting (replay historical scenarios, compare PnL, data sources)
- spec §4.1.1 — Formula validation (implement A/B/C, ship validation script on ~20 labeled wallets)
- spec §16.6 — Backtesting deliverable
- spec §12.2 — Global analytics (include/exclude sessions, run analytics on selected/filtered)

## Prerequisites

- Phase 3b complete: `Engine`, `PaperExecutionAdapter`, `EventLogger` all working
- `backtest_runs` table exists (Phase 0)
- `labeled_wallets.json` fixture with known-good wallet classifications
- Historical event data available (from Dune query or Data API local store)

## Modules to build

### 1. `src/poly_crawler/analytics/backtest_runner.py` — Backtest executor

Feeds historical `RawEvent`s through the engine with a given config snapshot. Records results as a `backtest_run` linked to a session.

**Interface:**

```python
class BacktestRunner:
    def __init__(self, config: Config, db: AsyncSession): ...

    async def run(
        self,
        events: list[RawEvent],
        config_snapshot: dict[str, Any],
        score_variant: str = "sqrt",
        name: str | None = None,
    ) -> BacktestRun:
        """Replay events through the engine, return backtest run with stats."""
```

**Process:**

```
1. Create a Session (mode="backtest", private=true by default)
2. Create a BacktestRun row (session_id, config_snapshot, score_variant, started_at)
3. Create a mock IngestionAdapter that yields events from the provided list
4. Create a PaperExecutionAdapter with mock orderbooks
5. Initialize Engine with mock adapters + backtest config
6. Run poll cycles for each event batch
7. Collect: paper_trades, alerts, position states, PnL
8. Update BacktestRun: completed_at, status="completed"
9. Return BacktestRun with summary stats
```

### 2. `src/poly_crawler/analytics/backtest_stats.py` — Result aggregation

Computes summary statistics from a completed backtest run.

**Functions:**

| Function | Purpose |
|----------|---------|
| `compute_run_stats(session, backtest_run_id) -> BacktestStats` | Aggregate all paper_trades for a run |
| `compare_runs(run_ids: list[UUID]) -> list[BacktestStats]` | Side-by-side comparison of multiple runs |
| `compute_hypothetical_pnl(trades, mirror_caps: float) -> float` | What-if PnL at different mirror caps |

**BacktestStats:**

```python
@dataclass
class BacktestStats:
    run_id: UUID
    config_snapshot: dict[str, Any]
    score_variant: str
    total_trades: int
    entries: int
    exits: int
    total_pnl_usd: float
    win_rate: float
    avg_latency_ms: float
    max_drawdown_usd: float
    sharpe_ratio: float | None
    best_trade_usd: float
    worst_trade_usd: float
```

### 3. `scripts/validate_scores.py` — Score variant validation

Runs all three profit variants (A/log, B/sqrt, C/piecewise) against labeled wallets and reports which best separates suspicious from normal.

**Process (spec §4.1.1):**

```
1. Load labeled_wallets.json (~20 wallets: 10 suspicious, 10 normal)
2. For each wallet, compute cluster_score under each variant:
   - Variant A: profit_log
   - Variant B: profit_sqrt (current default)
   - Variant C: profit_piecewise
3. Report: separation quality, false positive rate, false negative rate
4. Recommend min_cluster_score threshold per variant
5. Output: table comparing variants + recommended threshold
```

**Output format:**

```
Variant A (log):     suspicious avg=15.2, normal avg=2.1, separation=13.1
Variant B (sqrt):    suspicious avg=18.3, normal avg=1.8, separation=16.5  ← best
Variant C (piecewise): suspicious avg=12.7, normal avg=3.0, separation=9.7

Recommended min_cluster_score (variant B): 8.0
  - False positive rate: 0/10 (0%)
  - False negative rate: 1/10 (10%)
```

### 4. `src/poly_crawler/analytics/event_replay.py` — Historical event loader

Loads historical events from a data source and converts them to `RawEvent` format for the backtest runner.

**Functions:**

| Function | Purpose |
|----------|---------|
| `load_events_from_json(path: Path) -> list[RawEvent]` | Load pre-recorded events from JSON |
| `load_events_from_dune(query_id: str, api_key: str) -> list[RawEvent]` | Fetch events from Dune query results |
| `load_events_from_data_api(addresses: list[str], start: datetime, end: datetime) -> list[RawEvent]` | Fetch historical events from Polymarket Data API |

### 5. Update `src/poly_crawler/api/routes/stats.py` — Backtest comparison routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stats/backtests` | List all backtest runs |
| GET | `/stats/backtests/{id}` | Backtest run detail + stats |
| GET | `/stats/backtests/compare?ids=...` | Compare multiple runs side-by-side |

## Data flow

### Backtest execution

```
1. User provides: historical events + config to test
2. BacktestRunner.run(events, config_snapshot, score_variant="sqrt")
3. Create Session (mode="backtest", private=true)
4. Create BacktestRun (session_id, config_snapshot, score_variant, started_at)
5. For each event batch (sorted by timestamp):
   a. Feed to Engine via mock IngestionAdapter
   b. Engine processes: FSM transitions, paper fills, trade persistence
6. After all events processed:
   a. compute_run_stats() → BacktestStats
   b. Update BacktestRun: completed_at, status="completed"
7. Return BacktestRun + BacktestStats
```

### Score validation

```
1. Load labeled_wallets.json (10 suspicious, 10 normal)
2. For each variant (A, B, C):
   a. For each wallet: compute cluster_score
   b. Group by label (suspicious vs normal)
   c. Compute separation = |suspicious_avg - normal_avg|
3. Report best variant + recommended threshold
4. Save results to docs/ or scripts/output/
```

## Config changes

None. Backtest uses existing config schema — just varies the values per run.

## DB changes

None. `backtest_runs`, `sessions`, `paper_trades` all exist. Backtest runs are stored as sessions with `mode="backtest"`.

## Test plan

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_backtest_stats.py` | PnL calculation; win rate; hypothetical PnL at different mirror caps; comparison logic |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_backtest_runner.py` | Full backtest: load events from fixture → run through engine → verify paper_trades persisted → verify BacktestRun completed |
| `tests/integration/test_score_validation.py` | validate_scores.py on labeled_wallets.json → verify all 3 variants produce scores → verify separation metrics |

### Scripts

| File | What it tests |
|------|---------------|
| `scripts/validate_scores.py` | End-to-end script execution; output format correctness |

## Acceptance criteria

- [ ] `BacktestRunner.run()` replays events through the engine and persists results
- [ ] Backtest runs stored as sessions with `mode="backtest"`
- [ ] `BacktestStats` includes PnL, win rate, trade counts, latency
- [ ] `compare_runs()` produces side-by-side comparison
- [ ] `validate_scores.py` runs all 3 variants on labeled wallets
- [ ] Score validation recommends a `min_cluster_score` threshold
- [ ] Historical events loadable from JSON, Dune, or Data API
- [ ] All unit + integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Dune API access | Need Dune API key for historical event queries. User must provide. Alternative: Data API local store. |
| 2 | How many labeled wallets? | Spec says ~20 (10 suspicious, 10 normal). Currently `labeled_wallets.json` has 1 cluster. Need to expand to 20 wallets. |
| 3 | Backtest orderbook data | Paper fills need historical orderbooks. Where to source? May need to record orderbooks during live paper runs for future backtests. |
| 4 | Should backtests run via CLI or API? | Both. CLI for batch validation scripts, API for dashboard-triggered backtests. |
| 5 | Sharpe ratio calculation | Need risk-free rate assumption (0% for crypto?). May skip in v0.1 if complex. |
