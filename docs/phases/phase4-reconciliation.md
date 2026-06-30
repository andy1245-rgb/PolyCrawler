# Phase 4 — Reconciliation + RPC Batching

**Source:** spec.md §16.4, §8.2 | docs/architecture.md §6
**Status:** ⬜ Not started
**Prerequisites:** [Phase 3b](phase3b-paper-execution.md) complete (paper trading pipeline works end-to-end)

---

## Goal

Harden the paper engine against polling gaps. Add authoritative balance rebuilds from the Data API (reconciliation) and batch RPC calls (multicall) for efficiency. This phase catches missed events and ensures net exposure stays accurate even when polling misses trades between cycles.

## Spec references

- spec §8.2 — Position reconciliation (rebuild balances from Data API, mirror implied delta)
- spec §5.1 — Scanners (position balance scanner, reconciliation)
- spec §6.4 — Event processor step 1: "Reconciliation overwrites balances from Data API — always wins over event path"
- spec §15 — Tech stack: "RPC batching: web3.py + multicall for balance checks"
- arch §6 — Task scheduling (reconciliation every 3rd balance poll)

## Prerequisites

- Phase 3b complete: full paper cycle works, `paper_trades` being persisted
- `PollingIngestionAdapter.fetch_balances()` implemented (Phase 2)
- `RpcClient` with multicall capability (Phase 2)

## Modules to build

### 1. `src/poly_crawler/ingestion/polling/multicall.py` — Batch balance checks

Wraps Multicall3 contract on Polygon for efficient batch ERC-20/balance reads. Reduces RPC calls from N (one per account) to 1 (single multicall).

**Functions:**

| Function | Purpose |
|----------|---------|
| `MulticallBatch(rpc: RpcClient)` | Initialize with RPC client |
| `add_balance_check(token_address, account_address) -> None` | Queue a balance read |
| `async execute() -> dict[str, int]` | Execute batch, return all results |
| `async batch_account_balances(account_addresses: list[str]) -> dict` | Fetch USDC + position token balances for multiple accounts in one call |

**Multicall3 contract (Polygon):** `0xcA11bde05977b3631167028862bE2a173976CA11`

### 2. `src/poly_crawler/engine/reconciliation.py` — Reconciliation scanner

The authoritative balance rebuild. Runs every Nth poll cycle (default: every 3rd). Overwrites event-derived balances with API truth.

**Functions:**

| Function | Purpose |
|----------|---------|
| `async reconcile_positions(session, ingestion, config) -> list[ReconciliationResult]` | Full balance rebuild for all active cluster positions |
| `async reconcile_cluster(session, cluster_id, ingestion) -> ReconciliationResult` | Rebuild balances for one cluster |
| `compute_implied_delta(old_balances, new_balances) -> dict` | Delta between event-tracked and API-truth balances |

**ReconciliationResult:**

```python
@dataclass
class ReconciliationResult:
    cluster_position_id: UUID
    market_id: str
    old_net: int
    new_net: int
    implied_delta: int
    per_sibling_changes: dict[str, dict[str, int]]
    needs_mirror: bool
```

**Reconciliation logic (spec §8.2):**

```
1. Fetch all sibling balances per market from Data API (authoritative)
2. Overwrite cluster_position.sibling_balances with API data
3. Recompute net_exposure from new balances
4. Compare new_net vs last_known_net
5. If delta exists (we missed events):
   - Mirror the implied delta (same rules as §7.7)
   - If net went to ~0: close position (reason="reconciled")
   - Log reconciliation result
6. Persist updated balances + net
```

### 3. Update `src/poly_crawler/engine/processor.py` — Add reconciliation step

Add reconciliation to the poll cycle:

```python
class Engine:
    def __init__(self, ...):
        self._poll_count = 0
        self._reconciliation_interval = 3  # every 3rd poll

    async def run_poll_cycle(self):
        events = await self.ingestion.poll_batch()
        for event in sorted(events, key=lambda e: e.timestamp):
            await self._process_event(event)

        self._poll_count += 1
        if self._poll_count % self._reconciliation_interval == 0:
            await self._reconcile_positions()
```

### 4. Update `src/poly_crawler/scheduler/tasks.py` — RPC log cleanup

Add a daily cleanup task for `rpc_logs` (spec §18: 90-day retention).

| Task | Interval | Purpose |
|------|----------|---------|
| `rpc_log_cleanup` | Daily (86400s) | Delete `rpc_logs` rows older than `retention.raw_trades_days` |
| `reconciliation` | Every 3rd balance poll | Full balance rebuild (triggered by processor, not scheduler) |

### 5. Update `src/poly_crawler/ingestion/polling/rpc_client.py` — Use multicall

Refactor `fetch_balances()` to use the multicall batch instead of individual calls:

```python
async def fetch_balances(self, account_ids: list[UUID]) -> dict[UUID, dict[str, dict[str, int]]]:
    # Old: N individual RPC calls
    # New: 1 multicall batch
    batch = MulticallBatch(self._rpc)
    for account_id in account_ids:
        batch.add_balance_check(...)
    results = await batch.execute()
    # Map results to {account_id: {market_id: {yes, no}}}
```

## Data flow

### Reconciliation cycle

```
1. Poll cycle #3 (every 3rd) triggers reconciliation
2. For each active cluster_position (state=IN_POSITION or WATCHING with activity):
   a. Fetch all sibling balances from Data API (authoritative)
   b. Overwrite sibling_balances JSONB with API data
   c. Recompute net = sum(Yes) - sum(No)
   d. Compare new_net vs last_known_net
   e. If delta > dust:
      - Mirror implied delta (buy/sell to match)
      - PaperTrade: reason="net_adjustment", source="reconciliation"
   f. If new_net ≈ 0 (below min_net_usd):
      - Close position: reason="reconciled"
      - PaperTrade: event_type="exit", reason="reconciled"
   g. Log reconciliation result
3. Persist all changes
4. Log balance snapshots to sibling_balance_snapshots
```

### Missed event recovery

```
Scenario: Sibling sold 200 Yes between polls, we didn't catch the trade event.

1. Event path: sibling_balances still shows 200 Yes (stale)
2. net_exposure = 200 (stale, should be 0)
3. Reconciliation fires:
   a. Data API returns: 0 Yes for that sibling
   b. Overwrite sibling_balances: 200 → 0
   c. new_net = 0, old_net = 200
   d. implied_delta = -200
   e. Mirror: sell 200 Yes (close our mirror)
   f. PaperTrade: exit, reason="reconciled"
   g. cluster_position → CLOSED → WATCHING
```

## Config changes

| New key | Type | Default | Purpose |
|---------|------|---------|---------|
| `reconciliation_interval` | `int` | `3` | Run reconciliation every Nth poll cycle |

Add to a new `ReconciliationConfig` section or to `ExecutionConfig`.

## DB changes

None. All tables exist. This phase writes to: `sibling_balance_snapshots` (more frequently now), `paper_trades` (reconciliation adjustments), `rpc_logs` (cleaned up).

## Test plan

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_reconciliation.py` | Implied delta calculation; net change detection; needs_mirror threshold; per-sibling change tracking; net-to-zero reconciliation |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_reconciliation.py` | Full reconciliation cycle: stale balances → API truth → delta mirror → DB persistence; missed event recovery scenario; net-to-zero close via reconciliation |
| `tests/integration/test_multicall.py` | MulticallBatch with mock RPC: batch construction, execution, result mapping |

## Acceptance criteria

- [ ] `MulticallBatch` executes batch balance reads in a single RPC call
- [ ] Reconciliation runs every Nth poll cycle (configurable)
- [ ] Reconciliation overwrites `sibling_balances` from Data API
- [ ] Implied deltas are mirrored with correct paper trades (reason="net_adjustment", source="reconciliation")
- [ ] Net-to-zero via reconciliation closes position (reason="reconciled")
- [ ] `rpc_logs` cleanup task runs daily, deletes rows older than retention window
- [ ] `fetch_balances()` uses multicall instead of individual calls
- [ ] All unit + integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Reconciliation interval | Default every 3rd poll. May need tuning based on RPC cost vs accuracy tradeoff. |
| 2 | Should reconciliation also check for new markets? | If siblings have positions in markets we're not tracking, should we create new cluster_positions? Spec says positions are created lazily on first activity — reconciliation could be that activity. |
| 3 | Multicall3 vs individual calls fallback | If multicall fails, should we fall back to individual calls or fail hard? Recommend fallback with warning log. |
| 4 | Reconciliation and fast post-entry polls | Should reconciliation run during the 6× fast poll window? Probably not — fast polls are for immediate post-entry accuracy. |
