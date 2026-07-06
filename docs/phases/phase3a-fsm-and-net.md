# Phase 3a — FSM & Net Calculator

**Status:** ⬜ Not started
**Prerequisites:** [Phase 2](phase2-parent-watcher.md) complete (`RawEvent` shape stable)
**Human-readable docs:** [position-state-machine.md](../protocols/position-state-machine.md)

---

## Goal

Build the position state machine, net exposure calculator, and poll-cycle processor — the structural core of the engine. Trading rules (entry/exit/hedge) live in [phase3a-trading-rules.md](phase3a-trading-rules.md) and plug into this FSM. No real execution yet — use a no-op `ExecutionAdapter` stub until Phase 3b.

---

## Behavioral specification

### Two layers (do not confuse)

| Layer | What it tracks |
|-------|----------------|
| **Cluster watch** | Flagged parent + all siblings; scanners always on |
| **Cluster position** | One state machine row per **market** the cluster touches |

A **FUND** event adds a sibling to watch — it does **not** create a position. A `cluster_positions` row is created **lazily** on first market activity.

### States

```
                    ┌─────────────────────────────────────┐
                    │            WATCHING                  │
                    └──────────────┬──────────────────────┘
                                   │
           entry rules + review    │    entry rules, no review
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
             ┌────────────┐                 ┌─────────────┐
             │   SIGNAL   │                 │ IN_POSITION │
             └─────┬──────┘                 └──────┬──────┘
                   │                               │
                   ▼                               ▼
             IN_POSITION / SKIPPED            CLOSED → WATCHING
```

| State | Meaning |
|-------|---------|
| `WATCHING` | No mirrored hold; net ~0 or reset after close |
| `SIGNAL` | Entry rules passed; awaiting human review |
| `IN_POSITION` | Actively mirroring cluster net |
| `CLOSED` | **Bookkeeping only** — exit logged, then **same tick** → `WATCHING` |
| `SKIPPED` | Review rejected or chose not to mirror |

### Persisted fields (`cluster_positions`)

| Field | Meaning |
|-------|---------|
| `sibling_balances` | `accountId → { yesShares, noShares }` |
| `net_exposure` | sum(Yes) − sum(No) across siblings |
| `last_known_net` | Previous net for delta mirroring |
| `mirrored_shares` | Our current hold |
| `last_closed_at` | For follow re-entry (rules doc) |
| `tp_sl_mirror_suspended_until_flat` | Set on TP/SL exit; cleared when net ~0 |

### Event processor (each poll batch)

Process events in **timestamp order**, then reconciliation (Phase 4). For each `(cluster, market)`:

1. **Update balances → net** — apply hedge filter from rules doc; reconciliation overwrites (Phase 4).
2. **`IN_POSITION`** — mirror net delta; if net ~0 → `CLOSED` (`cluster_hedged`); else check exit rules.
3. **`WATCHING`** — clear TP/SL suspend if net ~0; if net non-zero and entry rules pass → `SIGNAL` or `IN_POSITION`.
4. **`SIGNAL`** — approved → `IN_POSITION`; rejected → `SKIPPED`; optional timeout → `EXPIRED`.
5. **`SKIPPED`** — if net ~0 → `WATCHING`.
6. **`CLOSED`** — persist reason, PnL; set `last_closed_at`; TP/SL → set suspend flag → `WATCHING` same tick.

### Net exposure math

```
net = sum(yesShares) - sum(noShares)  # across all siblings
delta = new_net - old_net
targetShares = sign(net) × min(abs(net) × mirrorPct, capShares)
is_net_flat = abs(net_usd) < conflict.min_net_usd
```

Detailed entry/exit/hedge/re-entry rules: [phase3a-trading-rules.md](phase3a-trading-rules.md).

### Optional timeouts

```yaml
position:
  signalExpireMinutes: null
  marketWatchExpireDays: null
```

### Account watchlist (not FSM)

| watchStatus | Meaning |
|-------------|---------|
| `active` | Included in cluster polls |
| `expired` | No trades within `watch.accountExpireDays` — reactivates on new trade |

---

## Implementation

### Modules to build

#### 1. `engine/state_machine.py` — Position FSM

```python
class PositionState(str, Enum):
    WATCHING = "watching"
    SIGNAL = "signal"
    IN_POSITION = "in_position"
    CLOSED = "closed"
    SKIPPED = "skipped"

class PositionFSM:
    async def process(self, ctx: EngineContext) -> list[Action]: ...
```

State handlers call into rules modules from [phase3a-trading-rules.md](phase3a-trading-rules.md).

#### 2. `engine/net_calculator.py` — Pure math

| Function | Purpose |
|----------|---------|
| `compute_net(sibling_balances)` | sum(Yes) − sum(No) |
| `compute_delta(old, new)` | new − old |
| `mirror_target(net, mirror_pct, cap_shares)` | Target mirrored size |
| `is_net_flat(net, min_net_usd)` | Below dust threshold |

#### 3. `engine/processor.py` — Poll cycle orchestrator

```python
class Engine:
    async def run_poll_cycle(self):
        events = await self.ingestion.poll_batch()
        for event in sorted(events, key=lambda e: e.timestamp):
            await self._process_event(event)
        await self._reconcile_positions()  # stub until Phase 4
```

**`_process_event`:** load/create `ClusterPosition` → apply hedge filter → recompute net → FSM.process → execute actions (stub) → persist.

#### 4. No-op execution stub

```python
class NoOpExecutionAdapter(ExecutionAdapter):
    async def execute_entry(self, signal): return FillResult(success=True, ...)
    async def execute_exit(self, signal): return FillResult(success=True, ...)
```

---

## Config changes

None — all keys exist from Phase 0.

---

## DB changes

None — updates `cluster_positions` state fields.

---

## Test plan

| File | Coverage |
|------|----------|
| `tests/unit/test_state_machine.py` | All FSM transitions; CLOSED → WATCHING same tick; tp_sl suspend clearing |
| `tests/unit/test_net_calculator.py` | Net, delta, mirror target, cap, is_net_flat |
| `tests/integration/test_engine_cycle.py` | Mock events → state persistence (no-op execution) |

Rules-specific tests: [phase3a-trading-rules.md](phase3a-trading-rules.md).

---

## Acceptance criteria

- [ ] All 5 `PositionState` values implemented
- [ ] FSM dispatches to correct handler per state
- [ ] Net calculator: net, delta, mirror targets, flat detection
- [ ] `Engine.run_poll_cycle()` processes events in timestamp order
- [ ] CLOSED auto-transitions to WATCHING on same tick
- [ ] No-op execution stub logs actions without filling
- [ ] All tests pass; lint clean

---

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | DB commit granularity | Batch per poll cycle (recommended) |
| 2 | Rules module integration | Import from `entry_rules`, `exit_rules`, etc. (trading-rules phase) |
