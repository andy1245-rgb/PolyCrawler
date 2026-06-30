# Phase 3b — Paper Execution

**Source:** spec.md §16.3 (pt 2), §10, §10.1, §12 | docs/architecture.md §4.2, §8
**Status:** ⬜ Not started
**Prerequisites:** [Phase 3a](phase3a-engine-core.md) complete (engine produces Actions, FSM works)

---

## Goal

Replace the execution stub with a real paper trading adapter. When the engine produces an "enter" or "exit" Action, the paper adapter simulates a fill using the orderbook walk model. Trades are persisted to `paper_trades`, sessions are managed, and all events are logged for analytics. After this phase, the full paper-trading pipeline works end-to-end.

## Spec references

- spec §10 — Execution modes (observe/paper/live, shared engine, swappable adapter)
- spec §10.1 — Paper fill model (orderbook walk at next poll, VWAP, slippage, pessimistic adjustment)
- spec §12 — Sessions & analytics (session lifecycle, config snapshot, data to persist)
- spec §7.2 — Recorded data on entry (market, cluster, net, fill, latency, session)
- arch §4.2 — ExecutionAdapter abstract interface
- arch §8 — Paper fill model pseudocode

## Prerequisites

- Phase 3a complete: `Engine` produces `Action` objects, `PositionFSM` works
- `IngestionAdapter.fetch_orderbook()` implemented in Phase 2
- `paper_trades`, `sessions`, `config_snapshots` tables exist (Phase 0)

## Modules to build

### Execution layer

#### 1. `src/poly_crawler/execution/base.py` — Abstract adapter + signal/fill models

The contract for execution. Already specified in [component-interfaces.md](../architecture/component-interfaces.md).

```python
class EntrySignal(BaseModel):
    cluster_position_id: UUID
    market_id: str
    side: Literal["yes", "no"]
    shares: int
    max_price: float | None = None

class FillResult(BaseModel):
    success: bool
    filled_shares: int
    avg_price: float
    slippage_bps: int
    book_snapshot: dict[str, Any] | None = None

class ExecutionAdapter(ABC):
    @abstractmethod
    async def execute_entry(self, signal: EntrySignal) -> FillResult: ...

    @abstractmethod
    async def execute_exit(self, signal: EntrySignal) -> FillResult: ...
```

#### 2. `src/poly_crawler/execution/paper/orderbook_walk.py` — §10.1 VWAP fill model

The core fill simulation. Walks the CLOB order book to compute volume-weighted average price.

**Algorithm (spec §10.1):**

```
1. Wait for next poll cycle after signal.
2. Fetch CLOB order book for the market/outcome.
3. Walk the book from cheapest up, consuming shares:
   - Take all shares at level 1 (cheapest)
   - Take partial from level 2 if needed
   - Continue until target filled or book exhausted
4. Compute VWAP = total_cost / filled_shares
5. Compute slippage = |VWAP - mid| / mid × 10000 (bps)
6. Apply pessimistic_slippage_pct if configured
```

**Function:**

```python
async def walk_orderbook(
    book: dict[str, Any],
    target_shares: int,
    pessimistic_slippage_pct: float = 0.0,
) -> FillResult:
    """Walk order book levels, return VWAP fill result."""
    remaining = target_shares
    total_cost = 0.0
    levels_consumed = []

    for level in sorted(book["levels"], key=lambda l: l["price"]):
        fill = min(remaining, level["shares"])
        total_cost += fill * level["price"]
        remaining -= fill
        levels_consumed.append({**level, "filled": fill})
        if remaining <= 0:
            break

    filled = target_shares - remaining
    avg_price = total_cost / filled if filled > 0 else 0.0

    mid = (book["bid"] + book["ask"]) / 2
    slippage = int(abs(avg_price - mid) / mid * 10000) if mid > 0 else 0

    # Apply pessimistic adjustment
    if pessimistic_slippage_pct > 0:
        avg_price *= (1 + pessimistic_slippage_pct)  # adverse direction

    return FillResult(
        success=remaining == 0,
        filled_shares=filled,
        avg_price=avg_price,
        slippage_bps=slippage,
        book_snapshot={"levels": levels_consumed},
    )
```

#### 3. `src/poly_crawler/execution/paper/adapter.py` — PaperExecutionAdapter

Concrete implementation using `orderbook_walk`. Fetches the book from the ingestion adapter, walks it, returns fill results.

```python
class PaperExecutionAdapter(ExecutionAdapter):
    def __init__(self, ingestion: IngestionAdapter, config: Config):
        self._ingestion = ingestion
        self._config = config

    async def execute_entry(self, signal: EntrySignal) -> FillResult:
        book = await self._ingestion.fetch_orderbook(signal.market_id, signal.side)
        return await walk_orderbook(
            book, signal.shares, self._config.paper.pessimistic_slippage_pct
        )

    async def execute_exit(self, signal: EntrySignal) -> FillResult:
        # Exit walks the opposite side of the book (sell = ask side)
        book = await self._ingestion.fetch_orderbook(signal.market_id, signal.side)
        return await walk_orderbook(
            book, signal.shares, self._config.paper.pessimistic_slippage_pct
        )
```

### Analytics layer

#### 4. `src/poly_crawler/analytics/session_manager.py` — Session lifecycle

Manages the creation and lifecycle of crawler sessions.

**Functions:**

| Function | Purpose |
|----------|---------|
| `create_session(config: Config, mode: str) -> Session` | Create a session row with config snapshot, mode, review_mode |
| `end_session(session_id: UUID) -> None` | Set `ended_at`, `status="completed"` |
| `get_active_session() -> Session | None` | Return the current running session |
| `snapshot_config(config: Config) -> ConfigSnapshot` | Create a `config_snapshots` row with full config JSON |

**Session ID generation:** Based on start date + length (spec §12.1 — exact format TBD).

#### 5. `src/poly_crawler/analytics/event_logger.py` — Structured event persistence

Persists all trade events, alerts, and balance snapshots. Called by the engine after each action.

**Functions:**

| Function | Purpose |
|----------|---------|
| `log_paper_trade(session, action, fill_result, event) -> PaperTrade` | Persist a trade with all fields from spec §7.2 |
| `log_alert(session, alert_type, parent_id, cluster_id, metadata) -> Alert` | Persist an alert |
| `log_balance_snapshot(account_id, cluster_id, market_id, yes, no) -> SiblingBalanceSnapshot` | Persist a balance snapshot |
| `log_config_snapshot(config) -> ConfigSnapshot` | Persist config at entry time |

**PaperTrade fields persisted (spec §7.2):**

- `cluster_position_id`, `session_id`, `event_type` (entry/net_adjustment/exit)
- `sibling_account_id`, `net_before`, `net_after`, `net_delta`
- `our_side` (yes/no), `our_shares`, `our_fill_price`, `our_fill_usd`
- `source_tx`, `reason`, `latency_ms`, `book_snapshot_id`, `slippage_bps`

### Engine integration

Update `Engine.__init__` to accept a real `ExecutionAdapter` instead of the Phase 3a stub:

```python
class Engine:
    def __init__(
        self,
        ingestion: IngestionAdapter,
        execution: ExecutionAdapter,  # Now PaperExecutionAdapter
        config: Config,
        db: AsyncSession,
        session_manager: SessionManager,
        event_logger: EventLogger,
    ): ...
```

When the FSM produces an "enter" action:

```
1. Build EntrySignal from Action (market_id, side, shares, max_price)
2. Call execution.execute_entry(signal) → FillResult
3. event_logger.log_paper_trade(...) with fill details
4. Update cluster_position (mirrored_yes/no, state=IN_POSITION)
5. Schedule fast post-entry polls (6 × 10s)
```

### Post-entry fast polling (spec §7.4)

After entry, the scheduler runs `fast_poll_for(cluster_position_id)`:

```
6 fast polls at post_entry_poll_interval_sec (10s)
→ After 6 cycles, revert to normal exit.poll_interval_sec (60s)
```

## Data flow

### Full entry cycle (with execution)

```
1. Engine.run_poll_cycle() → events processed
2. FSM produces Action(type="enter", side="yes", shares=200)
3. Engine builds EntrySignal(market_id, side="yes", shares=200, max_price=0.5)
4. PaperExecutionAdapter.execute_entry(signal)
   → fetch_orderbook(market_id, "yes")
   → walk_orderbook(book, 200 shares)
   → FillResult(avg_price=0.462, slippage_bps=27, filled=200)
5. event_logger.log_paper_trade(
     session, action, fill_result, event,
     event_type="entry", our_side="yes", our_shares=200,
     our_fill_price=0.462, our_fill_usd=92.40, slippage_bps=27
   )
6. Update cluster_position: mirrored_yes=200, state="in_position"
7. event_logger.log_alert(type="entry", cluster_id, ...)
8. scheduler.fast_poll_for(cluster_position_id)
```

### Full exit cycle (with execution)

```
1. FSM produces Action(type="exit", reason="cluster_hedged")
2. Engine builds EntrySignal(market_id, side="yes", shares=200)  # sell to close
3. PaperExecutionAdapter.execute_exit(signal)
   → fetch_orderbook(market_id, "yes")  # sell side
   → walk_orderbook(book, 200 shares)
   → FillResult(avg_price=0.44, filled=200)
4. event_logger.log_paper_trade(event_type="exit", reason="cluster_hedged")
5. Update cluster_position: mirrored_yes=0, state="closed" → "watching"
6. Set last_closed_at, last_closed_reason="cluster_hedged"
7. tp_sl_suspended NOT set (reason ≠ tp/sl)
```

## Config changes

None. `PaperConfig` already has `fill_model` and `pessimistic_slippage_pct`. `EntryConfig` has `post_entry_poll_interval_sec` and `post_entry_poll_count`.

## DB changes

None. All tables exist. This phase writes to: `paper_trades`, `alerts`, `sibling_balance_snapshots`, `sessions`, `config_snapshots`.

## Test plan

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_orderbook_walk.py` | VWAP calculation with known book levels; partial fill (book exhausted); slippage calculation; pessimistic adjustment; empty book handling; single-level book |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_paper_execution.py` | PaperExecutionAdapter with mock orderbook (from `sample_orderbook.json`); fill accuracy; book_snapshot persisted; slippage within expected range |
| `tests/integration/test_engine_cycle.py` | Full cycle: events → FSM → paper execution → DB persistence. Verify `paper_trades` rows created with correct fields. Verify state transitions persist. |
| `tests/integration/test_session_manager.py` | Session creation, config snapshot, end session, active session lookup |

### Fixtures used

| Fixture | Used by |
|---------|---------|
| `tests/fixtures/sample_orderbook.json` | Orderbook walk tests — bid/ask levels for Yes and No |

## Acceptance criteria

- [ ] `ExecutionAdapter` ABC + `EntrySignal`/`FillResult` models defined
- [ ] `walk_orderbook()` computes correct VWAP from book levels
- [ ] `PaperExecutionAdapter` implements `execute_entry` and `execute_exit`
- [ ] Entry actions produce `paper_trades` rows with all spec §7.2 fields
- [ ] Exit actions produce `paper_trades` rows with correct `event_type="exit"`
- [ ] `SessionManager` creates sessions with config snapshots
- [ ] `EventLogger` persists trades, alerts, balance snapshots
- [ ] Post-entry fast polling scheduled (6 × 10s)
- [ ] Full cycle works: WATCHING → enter → IN_POSITION → delta → exit → CLOSED → WATCHING
- [ ] All unit + integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Session ID format | spec §12.1 says "based off date start and length, exact way TBD". Suggest: `YYYYMMDD-HHmmss` format. |
| 2 | Should exit fill walk the bid or ask side? | Selling YES shares = walk bid side (sell into bids). Buying NO to close = walk ask side. Need clear mapping. |
| 3 | Latency measurement | `latency_ms` = signal timestamp → fill timestamp. Need to track when signal was produced vs when fill completed. |
| 4 | book_snapshot_id format | spec says "raw book snapshot reference". Suggest: hash of book levels or UUID. |
