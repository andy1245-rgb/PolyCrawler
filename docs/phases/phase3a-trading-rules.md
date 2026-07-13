# Phase 3a — Trading Rules

**Status:** ⬜ Not started
**Prerequisites:** Can develop **in parallel** with [phase3a-fsm-and-net.md](phase3a-fsm-and-net.md) (pure functions). Integration requires both before Phase 3b.
**Human-readable docs:** [entry-rules.md](../protocols/entry-rules.md), [exit-rules.md](../protocols/exit-rules.md), [review-and-autonomy.md](../protocols/review-and-autonomy.md)

---

## Goal

Implement all trading rule modules — entry conditions, exit priority chain, intra-fill hedge filter, follow re-entry, and review gates. Pure logic, fully testable without DB or execution. The FSM in [phase3a-fsm-and-net.md](phase3a-fsm-and-net.md) calls these modules.

---

## Behavioral specification

### Protocol 3 — Entry rules

Entry is **not** gated by cluster score. Applies when a flagged parent's cluster develops non-zero net exposure.

**All conditions must pass** (evaluated after poll batch, timestamp order):

| Rule | Config | Default |
|------|--------|---------|
| State `WATCHING`, not `tp_sl_mirror_suspended_until_flat` | — | required |
| State not `SKIPPED` | — | required |
| Cluster net non-zero (above `conflict.min_net_usd`) | — | required |
| \|net\| USD ≥ minimum | `entry.minBuyUsd` | $500 |
| Market tag allow-list (empty = all) | `entry.marketTags` | `[]` |
| Max entry odds on trade that moved net | `entry.maxOddsEnabled`, `entry.maxOdds` | on; 0.5 |
| Review gate | `review.mode` | `live_only` |

Once `IN_POSITION`, sibling trades only produce `net_adjustment` — entry rules **not** re-applied.

**Mirrored size:**

```
targetShares = sign(net) × min(abs(net) × entry.mirrorPct, capShares)
```

**Post-entry fast polling:**

```yaml
entry:
  postEntryPollIntervalSec: 10
  postEntryPollCount: 6   # 1 minute fast window
```

### Intra-fill hedges (§7.5)

When one wallet buys both Yes and No in a single fill:

| Mode | Behavior | Default |
|------|----------|---------|
| `net_only` | Each leg updates balance → cluster net | **Yes** |
| `filter_before_net` | Dominant leg only if >2× other; else ignore fill | No |

Prefer `net_only` — event path matches reconciliation path.

### Follow re-entry (§7.6)

If cluster net was ~0 and becomes non-zero within `reentryWindowMinutes`, treat as new entry (subject to entry rules).

```yaml
entry:
  followReentryAfterSell: true
  reentryWindowMinutes: 5
```

Per-account round-trips that don't change cluster net do **not** trigger re-entry.

### Net cluster mirroring (§7.7)

```yaml
conflict:
  policy: net_cluster_position
  min_net_usd: 100
  dust_shares: 0.001
  always_alert: true
```

On sibling buy/sell/redeem:

1. Update sibling balance
2. Recalculate `net_exposure`
3. `delta = new_net − old_net`
4. Mirror `delta × mirrorPct` if above dust
5. Record `net_adjustment` with `source_sibling`

| Case | Behavior |
|------|----------|
| Net → 0 | Close mirror; `exitReason: cluster_hedged` |
| Net flips sign | Exit old side, enter new — two fills |
| Cap reached | No increase while net grows; may reduce when net shrinks |
| Opposing siblings | Log `CONFLICT`; still mirror net |

After TP/SL: set `tp_sl_mirror_suspended_until_flat` until net ~0.

### Protocol 4 — Exit rules

Poll interval while `IN_POSITION`: `exit.pollIntervalSec` (default 60s).

**Default:** hold until cluster net flat, redeem, reconciliation, or resolution. TP/SL off unless enabled.

**Exit priority (first match wins):**

1. Cluster net flat / hedged / redeemed
2. TP or SL on mirrored position (skipped when disabled)
3. Max hold time (skipped when null)
4. Market resolved (`data_api.isResolved`)

| Rule | Config | Default |
|------|--------|---------|
| Take profit | `exit.takeProfitEnabled`, `exit.takeProfitPct` | off; +50% when on |
| Stop loss | `exit.stopLossEnabled`, `exit.stopLossPct` | off; −25% when on |
| Max hold | `exit.maxHoldHours` | null |
| Slippage guard | `exit.maxSlippagePct` | live only |
| Auto-close on resolution | `exit.closeOnResolution` | true |

**Reconciliation (Phase 4):** rebuild balances from Data API; mirror implied delta if events missed.

### Protocol 5 — Review & autonomy

| Mode | Paper | Live |
|------|-------|------|
| `all` | Requires approval | Requires approval |
| `live_only` (default) | Auto-execute | Requires approval |
| `none` | Auto-execute | Auto-execute |

Review required → state stays `SIGNAL` until approved (`IN_POSITION`) or rejected (`SKIPPED`).

---

## Implementation

### Modules to build

| Module | Purpose |
|--------|---------|
| `engine/entry_rules.py` | `evaluate_entry(ctx) -> bool` — all conditions |
| `engine/exit_rules.py` | `evaluate_exit(ctx) -> ExitDecision \| None` — priority chain |
| `engine/hedge_filter.py` | `apply_hedge_filter(event, mode) -> list[BalanceDelta]` |
| `engine/reentry.py` | `is_reentry_eligible(position, config) -> bool` |

**ExitDecision:**

```python
@dataclass
class ExitDecision:
    reason: str  # cluster_hedged, tp_hit, sl_hit, max_hold, resolved
    set_tp_sl_suspended: bool = False
```

Wire into `PositionFSM` handlers in [phase3a-fsm-and-net.md](phase3a-fsm-and-net.md).

---

## Config changes

None.

---

## DB changes

None.

---

## Test plan

| File | Coverage |
|------|----------|
| `tests/unit/test_entry_rules.py` | minBuyUsd, maxOdds, tags, suspended, skipped |
| `tests/unit/test_exit_rules.py` | Priority chain, TP/SL disabled, max_hold null |
| `tests/unit/test_hedge_filter.py` | net_only vs filter_before_net modes |
| `tests/unit/test_reentry.py` | Window timing, disabled config |

---

## Acceptance criteria

- [ ] Entry: all 6+ conditions, all-must-pass
- [ ] Exit: first-match-wins priority chain
- [ ] Hedge filter: both modes produce correct balance deltas
- [ ] Re-entry: window timing correct
- [ ] Review mode routing: SIGNAL vs auto IN_POSITION
- [ ] All unit tests pass; lint clean

---

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | TP/SL price source | Last trade vs orderbook mid — cache per poll cycle |
| 2 | Market resolution check | Cache `is_market_resolved` per market per cycle |
