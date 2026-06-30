# Phase 3a — Engine Core

**Source:** spec.md §16.3 (pt 1), §6, §7, §8 | docs/architecture.md §5, §6, §7
**Status:** ⬜ Not started
**Prerequisites:** [Phase 2](phase2-parent-watcher.md) complete (RawEvent shape stable, ingestion adapter working)

---

## Goal

Build the position state machine and all trading rules — the brain of the system. By the end of this phase, the engine can receive a batch of `RawEvent`s, update sibling balances, compute cluster net exposure, evaluate entry/exit conditions, and produce `Action` objects (enter, exit, adjust, alert). No execution yet — this phase is pure logic, fully testable with mock events and no DB writes beyond state persistence.

## Spec references

- spec §6 — Protocol 2: Position state machine (states, transitions, event processor)
- spec §7 — Protocol 3: Entry rules (conditions, mirror sizing, hedge filter, re-entry)
- spec §8 — Protocol 4: Exit rules (priority chain, TP/SL, max hold, resolution)
- spec §7.7 — Net cluster mirroring (target formula, delta calculation)
- arch §5 — State machine implementation approach
- arch §6 — Data flows (new sibling trade → entry, IN_POSITION delta, exit)

## Prerequisites

- Phase 2 complete: `RawEvent` model defined, ingestion adapter produces events
- Config schema has all exit fields (pre-flight fix already applied)
- `ClusterPosition` model exists with `state`, `net_exposure`, `sibling_balances`, `tp_sl_suspended`

## Modules to build

### 1. `src/poly_crawler/engine/state_machine.py` — Position FSM

The core state machine. One instance per `cluster_positions` row. Processes events and returns actions.

**States (spec §6.2):**

```python
class PositionState(str, Enum):
    WATCHING = "watching"
    SIGNAL = "signal"
    IN_POSITION = "in_position"
    CLOSED = "closed"
    SKIPPED = "skipped"
```

**Interface:**

```python
class PositionFSM:
    def __init__(self, db_row: ClusterPosition, config: Config):
        self.state = PositionState(db_row.state)
        self.row = db_row
        self.config = config

    async def process(self, ctx: EngineContext) -> list[Action]:
        """Dispatch to state handler, return list of actions to execute."""
        handler = {
            PositionState.WATCHING: self._handle_watching,
            PositionState.IN_POSITION: self._handle_in_position,
            PositionState.SIGNAL: self._handle_signal,
            PositionState.SKIPPED: self._handle_skipped,
            PositionState.CLOSED: self._handle_closed,
        }[self.state]
        return await handler(ctx)
```

**State handlers (spec §6.4):**

| Handler | Logic |
|---------|-------|
| `_handle_watching` | If `tp_sl_suspended` and net ~0 → clear flag. If net non-zero, not suspended, entry rules pass → SIGNAL or IN_POSITION (depends on review mode). Check re-entry window. |
| `_handle_in_position` | Mirror net delta. If net ~0 → CLOSED (`cluster_hedged`). Check exit priority: TP, SL, max hold, resolution → CLOSED. |
| `_handle_signal` | If approved → IN_POSITION. If rejected → SKIPPED. Optional timeout → EXPIRED. |
| `_handle_skipped` | If net ~0 → WATCHING. Else stay SKIPPED. |
| `_handle_closed` | Persist close reason, PnL. Set `last_closed_at`. If TP/SL → set `tp_sl_suspended`. → WATCHING (same tick). |

**Action types:**

```python
@dataclass
class Action:
    type: Literal["enter", "exit", "adjust", "alert", "state_change"]
    cluster_position_id: UUID
    market_id: str
    side: str | None = None
    shares: int | None = None
    reason: str | None = None
    alert_type: str | None = None
    metadata: dict[str, Any] | None = None
```

### 2. `src/poly_crawler/engine/net_calculator.py` — Net exposure + mirror targets

Pure math. Computes cluster net from sibling balances and calculates mirror targets.

**Functions:**

| Function | Purpose |
|----------|---------|
| `compute_net(sibling_balances: dict) -> int` | `sum(Yes) - sum(No)` across all siblings |
| `compute_delta(old_net: int, new_net: int) -> int` | `new_net - old_net` |
| `mirror_target(net: int, mirror_pct: float, cap_shares: int | None) -> int` | `sign(net) × min(abs(net) × mirror_pct, cap_shares)` |
| `cap_shares(mirror_cap_usd: float | None, mid_price: float) -> int | None` | Convert USD cap to share cap at current price |
| `is_net_flat(net: int, min_net_usd: float) -> bool` | True if `abs(net)` below threshold |
| `net_to_usd(net: int, price: float) -> float` | Convert net shares to USD value |

### 3. `src/poly_crawler/engine/entry_rules.py` — §7.1 entry conditions

Evaluates whether a cluster position should enter. All conditions must pass.

**Functions:**

| Function | Purpose |
|----------|---------|
| `evaluate_entry(ctx: EngineContext) -> bool` | Run all entry checks, return True/False |
| `check_min_buy_usd(net_usd: float, min_buy_usd: float) -> bool` | `abs(net_usd) >= min_buy_usd` |
| `check_market_tags(market_tags: list, allowed_tags: list) -> bool` | Empty allowed = all pass; else tag must be in list |
| `check_max_odds(trade_price: float, config: EntryConfig) -> bool` | If enabled, `trade_price <= max_odds` |
| `check_not_suspended(position: ClusterPosition) -> bool` | `tp_sl_suspended` must be False |
| `check_not_skipped(state: PositionState) -> bool` | State must not be SKIPPED |

**Entry odds check (spec §7.1):** `max_odds` applies to the **fill price of the specific sibling trade that moved cluster net from zero to non-zero** — not the current mid. Once IN_POSITION, entry rules are not re-applied.

### 4. `src/poly_crawler/engine/exit_rules.py` — §8 exit conditions

Evaluates exit priority chain. First match wins.

**Functions:**

| Function | Purpose |
|----------|---------|
| `evaluate_exit(ctx: EngineContext) -> ExitDecision | None` | Run priority chain, return first match or None |
| `check_net_flat(net: int, min_net_usd: float) -> ExitDecision | None` | Priority 1: cluster hedged/flat |
| `check_take_profit(entry_price: float, current_price: float, config: ExitConfig) -> ExitDecision | None` | Priority 2: TP hit (skipped if disabled) |
| `check_stop_loss(entry_price: float, current_price: float, config: ExitConfig) -> ExitDecision | None` | Priority 3: SL hit (skipped if disabled) |
| `check_max_hold(entry_time: datetime, config: ExitConfig) -> ExitDecision | None` | Priority 4: max hold exceeded (skipped if null) |
| `check_resolution(market_id: str, data_api: DataApiClient) -> ExitDecision | None` | Priority 5: market resolved (skipped if `close_on_resolution` false) |

**ExitDecision:**

```python
@dataclass
class ExitDecision:
    reason: str  # cluster_hedged, tp_hit, sl_hit, max_hold, resolved
    set_tp_sl_suspended: bool = False  # True only for tp_hit/sl_hit
```

### 5. `src/poly_crawler/engine/hedge_filter.py` — §7.5 intra-fill hedges

Translates trade events into balance deltas based on `hedge_filter_mode`.

**Functions:**

| Function | Purpose |
|----------|---------|
| `apply_hedge_filter(event: RawEvent, mode: str, config: EntryConfig) -> list[BalanceDelta]` | Returns balance deltas to apply |
| `net_only(event: RawEvent) -> list[BalanceDelta]` | Each leg updates balance directly |
| `filter_before_net(event: RawEvent, threshold: float) -> list[BalanceDelta]` | If one side > threshold × other → dominant only; else ignore fill |

**BalanceDelta:**

```python
@dataclass
class BalanceDelta:
    account_id: UUID
    market_id: str
    yes_delta: int
    no_delta: int
```

### 6. `src/poly_crawler/engine/reentry.py` — §7.6 follow re-entry

Checks if a non-zero net after a recent flat qualifies as a re-entry.

**Functions:**

| Function | Purpose |
|----------|---------|
| `is_reentry_eligible(position: ClusterPosition, config: EntryConfig) -> bool` | `follow_reentry_after_sell` is on AND `last_closed_at` is within `reentry_window_minutes` |
| `check_reentry_window(last_closed_at: datetime, window_minutes: int) -> bool` | Time delta check |

### 7. `src/poly_crawler/engine/processor.py` — Main poll cycle

The orchestrator. Runs one complete poll cycle: poll → sort → process events → reconcile → persist.

**Interface (from arch §4.3):**

```python
class Engine:
    def __init__(
        self,
        ingestion: IngestionAdapter,
        execution: ExecutionAdapter,  # Phase 3b — stub for now
        config: Config,
        db: AsyncSession,
    ): ...

    async def run_poll_cycle(self):
        """One cycle: poll → event process → reconcile → execute."""
        events = await self.ingestion.poll_batch()
        for event in sorted(events, key=lambda e: e.timestamp):
            await self._process_event(event)
        await self._reconcile_positions()
```

**`_process_event` logic (spec §6.4):**

```
1. Identify affected (cluster, market) from event
2. Load or create ClusterPosition row
3. Apply hedge filter → update sibling_balances
4. Recompute net_exposure
5. Create PositionFSM instance
6. Call fsm.process(ctx) → list of Actions
7. Execute actions (enter/exit/adjust/alert)
8. Persist state changes
```

**EngineContext:**

```python
@dataclass
class EngineContext:
    event: RawEvent
    position: ClusterPosition
    config: Config
    net: int
    delta: int
    sibling_balances: dict[str, Any]
```

## Data flow

### New sibling trade → entry (arch §7.1)

```
1. Poll cycle starts
2. EventDetector: account 0x... bought +200 Yes in "will-x-win"
3. RawEvent created → engine._process_event()
4. Load cluster_position for (cluster, market) → WATCHING
5. NetCalculator: update sibling_balances, recalc net = +200
6. EntryRules.evaluate(net=+200, market_tags, odds, minBuyUsd)
   → passes → review required?
   - live_only + paper → auto IN_POSITION
   - review required → SIGNAL
7. [Phase 3b] ExecutionAdapter.execute_entry() → FillResult
8. [Phase 3b] PaperTrade persisted, cluster_position updated
9. Alert: type=entry
```

### IN_POSITION — net delta (arch §7.2)

```
1. Poll: balances now 250 Yes (+50 delta)
2. NetCalculator: delta = +50
3. ExitRules: TP/SL/max-hold — none hit
4. EntryRules: skipped (already IN_POSITION)
5. Mirror delta: +50 × mirrorPct
6. [Phase 3b] PaperTrade: reason=net_adjustment
7. cluster_position.updated_at bumped
```

### Exit — cluster net flat (arch §7.3)

```
1. Poll: sibling sold 200 Yes → net = +50 (below min_net_usd=100)
2. ExitRules: net ≈ 0 → cluster_hedged
3. [Phase 3b] ExecutionAdapter: close position (sell 200 Yes)
4. [Phase 3b] PaperTrade: exit, reason=cluster_hedged
5. cluster_position → CLOSED → immediately → WATCHING
6. last_closed_at set. tp_sl_suspended NOT set (reason ≠ tp/sl)
7. Alert: type=exit
```

## Config changes

None. All config keys already exist (pre-flight fix applied `ExitConfig` fields).

## DB changes

None. `cluster_positions` table already has all needed columns. This phase reads and updates `state`, `net_exposure`, `last_known_net`, `sibling_balances`, `tp_sl_suspended`, `last_closed_at`, `last_closed_reason`.

## Test plan

These are all pure-function tests — fast, no DB, no execution. Highest value tests in the entire project.

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_state_machine.py` | Every FSM transition: W→S, W→P, P→C, C→W, S→P, S→SK, SK→W; tp_sl_suspended clearing; CLOSED auto-transitions to WATCHING same tick |
| `tests/unit/test_entry_rules.py` | min_buy_usd gate (above/below threshold); max_odds enabled/disabled; market_tags empty (all pass) vs allow-list; not_suspended check; not_skipped check; condition combinations |
| `tests/unit/test_exit_rules.py` | Net flat detection; TP hit (enabled/disabled); SL hit (enabled/disabled); max_hold exceeded (null = off); resolution check; priority ordering (first match wins); tp_sl_suspended set only on tp/sl |
| `tests/unit/test_net_calculator.py` | Net calc (sum Yes - sum No); delta calculation; mirror target with pct; mirror target with cap; cap_shares conversion; is_net_flat threshold; net sign flip handling |
| `tests/unit/test_hedge_filter.py` | net_only mode (each leg applied); filter_before_net dominant leg (>2×); filter_before_net near-tie (ignored); filter_before_net one-sided (same as net_only) |
| `tests/unit/test_reentry.py` | Re-entry within window; re-entry outside window; follow_reentry_after_sell disabled; last_closed_at null; net ~0 → non-zero detection |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_engine_cycle.py` | Full cycle with mock events: WATCHING → entry → IN_POSITION → delta → exit → CLOSED → WATCHING. DB persistence of state changes. Uses mock ExecutionAdapter (Phase 3b not needed). |

## Acceptance criteria

- [ ] `PositionState` enum with all 5 states
- [ ] `PositionFSM` dispatches to correct handler per state
- [ ] WATCHING handler evaluates entry rules, routes to SIGNAL or IN_POSITION
- [ ] IN_POSITION handler mirrors deltas, checks exit priority
- [ ] CLOSED handler persists reason, sets tp_sl_suspended on TP/SL, auto-transitions to WATCHING
- [ ] Net calculator computes net, delta, mirror targets correctly
- [ ] Entry rules: all 6 conditions evaluated, all-must-pass logic
- [ ] Exit rules: priority chain, first-match-wins, TP/SL only when enabled
- [ ] Hedge filter: both modes produce correct balance deltas
- [ ] Re-entry: window timing correct, disabled when config off
- [ ] `Engine.run_poll_cycle()` processes events in timestamp order
- [ ] All unit + integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | How to get current price for TP/SL evaluation? | Use last trade price from Data API, or mid from orderbook? Spec says TP/SL on "mirrored position PnL" — need entry price + current price. |
| 2 | Market resolution check — synchronous or cached? | `data_api.is_market_resolved()` per exit check could be slow. Cache resolution status per market per poll cycle. |
| 3 | ExecutionAdapter stub for Phase 3a | Use a no-op adapter that logs actions but doesn't fill. Phase 3b replaces with real paper adapter. |
| 4 | Should the processor batch DB writes or commit per event? | Batch per poll cycle for performance. Commit after all events + reconciliation processed. |
