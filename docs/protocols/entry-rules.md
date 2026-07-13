# Protocol 3 — Entry Rules

**Source:** [phase3a-trading-rules.md](../phases/phase3a-trading-rules.md) (behavioral spec)
**Related:** [architecture.md](../architecture.md) §6

---

Entry is **not** gated by cluster score. Entry applies when a flagged parent's cluster develops non-zero net exposure in a market.

## 7.1 Entry conditions

All conditions must pass. Evaluated on cluster net after processing all sibling events in the poll batch (timestamp order).

| Rule | Config key | Default |
|------|------------|---------|
| Cluster position state is `WATCHING` and not `tp_sl_mirror_suspended_until_flat` | — | required |
| Cluster position state is not `SKIPPED` | — | required |
| Cluster net becomes non-zero (above `conflict.min_net_usd`) | — | required |
| \|net\| USD ≥ minimum | `entry.minBuyUsd` | $500 |
| Optional: market tag allow-list | `entry.marketTags` | `[]` = all qualify |
| **Max entry odds** | `entry.maxOddsEnabled` + `entry.maxOdds` | on; 0.5 |
| Review gate | `review.mode` | see Protocol 5 |

### Max entry odds — explained

When `maxOddsEnabled: true`, the system checks the **fill price of the specific sibling trade that moved the cluster's net from zero to non-zero**.

Polymarket outcome tokens trade from $0.00 to $1.00 (they resolve to $1 or $0). The price **is** the implied probability:

| Price paid | Implied prob | Meaning |
|------------|-------------|---------|
| $0.30 | 30% | Market thinks unlikely; big upside if correct |
| $0.50 | 50% | Even money — the cutoff |
| $0.70 | 70% | Market already favors it; thinner edge |

**Default `maxOdds: 0.5`** means only mirror if the sibling bought at $0.50 or less. Above $0.50 is considered too expensive — buying "into the odds" with less profit potential.

**Why only the trade that moved net:** Once the cluster is `IN_POSITION`, subsequent sibling trades are `net_adjustment` events — entry rules are **not** re-applied. This is an entry gate only, not an ongoing constraint.

**Why the toggle exists:** `maxOddsEnabled: true` makes intent explicit rather than using a sentinel value. Set to `false` to skip the price check entirely.

## 7.2 Recorded data on entry

Each entry / adjustment records: market id/slug/title/tags, cluster id, parent wallet, cluster score at event time, net before/after, delta, side, source sibling, our mirrored size, fill price, latency, session id, mode, review outcome.

## 7.3 Mirrored size

```
targetShares = sign(net) × min(|net| × entry.mirrorPct, capShares)
```

`capShares` is `entry.mirrorCapUsd` converted at current mid (or last trade) price. Recompute target each cycle; trade the delta vs current hold.

## 7.4 Post-entry fast polling

After entry, poll at higher frequency for a short window:

```yaml
entry:
  postEntryPollIntervalSec: 10
  postEntryPollCount: 6   # 6 × 10s = 1 minute fast window
```

## 7.5 Intra-fill hedges

Sometimes **one wallet** buys **both Yes and No** in a **single fill** — misclick, UI quirk, arb, or intentional straddle. That is different from **cross-sibling** hedging (Alice Yes, Bob No), which cluster net already handles in §7.7.

§7.5 only asks: **when one fill has two legs, do we sanitize it before updating balances, or let the math net it?**

```yaml
entry:
  hedgeFilterMode: net_only          # net_only | filter_before_net
  ignoreHedgeTrades: true            # only when filter_before_net
  hedgeDominantThreshold: 2.0        # only when filter_before_net
```

### Mode: `net_only` (default)

**Pipeline:** each leg updates that sibling’s Yes/No balance → **cluster net = sum(Yes) − sum(No)**.

No special “this fill looks hedgy” branch.

Example:

```
Alice one fill: +800 Yes, +200 No
→ Alice balance: 800 Yes, 200 No
→ Cluster net: +600 Yes
→ Mirror delta per §7.7
```

**Why default:**

- One rule: balances in, net out — same as reconciliation.
- Consistent with cluster architecture (opposing exposure nets, including within one wallet).
- Simpler state machine event path.
- `conflict.min_net_usd` already ignores dust-level net.

**Reconciliation** (balance poll) is **authoritative** if trade parsing and on-chain balances disagree.

### Mode: `filter_before_net`

**Pipeline:** inspect **each fill** before applying balance deltas:

- If one side’s USD **> `hedgeDominantThreshold` ×** the other → apply **dominant leg only**.
- Else → **ignore the entire fill** (no balance update from that event).
- Then compute cluster net from balances.

Same fill as above:

```
+800 Yes, +200 No → dominant Yes (>2×) → only +800 Yes counted → net +800 (not +600)
```

Near tie:

```
+500 Yes, +450 No → neither > 2× → fill ignored → net unchanged
(net_only would yield +50 Yes net)
```

### When the modes agree vs diverge

| Scenario | `net_only` | `filter_before_net` |
|----------|------------|---------------------|
| One-sided buy (+1000 Yes only) | +1000 net | Same |
| Dominant hedge (+800 Yes, +200 No) | +600 net | **+800 net** |
| Near 50/50 (+500 Yes, +450 No) | +50 net | **0** (fill ignored) |
| Alice hedged fill + Bob +100 Yes | Net from all balances | Alice’s fill filtered; Bob same |
| Two separate txs (Yes then No) | Net from both | Each tx filtered separately — can diverge more |
| Reconciliation poll | **Truth wins** | **Truth wins** |

Both modes should **converge on reconciliation**. The toggle mainly affects **event-driven updates between polls** (entry timing, paper fill on signal poll).

### When to use `filter_before_net`

Turn on only if paper/backtests show **near-50/50 single fills** causing unwanted micro-entries (net briefly crosses `minBuyUsd`, then reconciliation flattens). Treat as a **noise knob**, not core architecture.

**Cost of `filter_before_net`:** event-derived balances can **temporarily disagree** with reconciliation; next poll may **jump** if a filtered fill actually landed on-chain.

### State machine interaction

```
net_only:           trade event → update each leg → recompute net → FSM transition

filter_before_net:  trade event → hedge filter → update balance → recompute net → FSM
                    poll          → overwrite balances from API → recompute net → FSM
```

Prefer **`net_only`** so the event path and reconciliation path share the same shape.

## 7.6 Follow re-entry after flat net

**Not** a cooldown that blocks re-entry. When enabled, if **cluster net** was ~0 (within `conflict.min_net_usd`) and becomes non-zero again within the window, treat as **new entry** (subject to §7.1 rules).

```yaml
entry:
  followReentryAfterSell: true   # default on
  reentryWindowMinutes: 5        # net must go from ~0 to non-zero within this window after going flat
```

Per-account sell-then-buy round-trips that **do not change cluster net** do **not** trigger re-entry. When `followReentryAfterSell` is on, it overrides `exit.addOnRepeatBuy` being false for that re-entry.

## 7.7 Sibling positions — net cluster mirroring

Siblings share the same parent funding wallet; the cluster is **one trading entity** for mirroring.

```yaml
conflict:
  policy: net_cluster_position   # alert_only retained as manual fallback only
  min_net_usd: 100               # |net| below this (USD) treated as zero
  dust_shares: 0.001             # float noise for balance comparisons
  always_alert: true             # log CONFLICT even when actively mirroring net
```

### Policy: `alert_only` (manual fallback)

- Log **`CONFLICT`** on opposing sibling balances; **no** automatic mirroring or net adjustments.
- For normal paper/live runs, use `net_cluster_position`.

### Policy: `net_cluster_position` (default)

**Per cluster, per market, maintain:**

- `net_exposure` — signed share count (positive = net Yes, negative = net No)
- `last_known_net` — for delta calculation
- Sibling balance map — each account’s Yes/No shares; updated every poll or trade event

**Target mirrored position:** see §7.3.

**On any sibling buy, sell, or redeem:**

1. Update that sibling’s balance (redeem → zero that position).
2. Recalculate `net_exposure`.
3. `delta = new_net − old_net`.
4. If `abs(delta)` above dust: mirror `delta × mirrorPct` (subject to cap).
   - `delta > 0` → increase net Yes exposure (buy Yes).
   - `delta < 0` → increase net No exposure (buy No, or reduce Yes — no shorting).
5. Record trade with reason `net_adjustment` and `source_sibling` account id.

Process events in **timestamp order** within a poll window.

**Edge cases:**

| Case | Behavior |
|------|----------|
| Net → 0 (within `min_net_usd`) | Close entire mirrored position; `exitReason: cluster_hedged` |
| Net flips sign (e.g. +100 Yes → −50 No) | Two legs: exit full Yes, then enter No — one adjustment event, two fills |
| Cap reached | Do not increase further while net grows; **may** reduce when net shrinks |
| First non-zero net | Entry subject to §7.1 (cluster net USD, odds on trade that moved net) |
| Net already non-zero, sibling adds same side | Mirror delta only; do not re-apply entry rules |
| Overlapping opposing balances | Log **`CONFLICT`** (if `always_alert`); still mirror net |
| Overlap ends | Log **`CONFLICT_RESOLVED`** |

**After TP/SL close:** set `tp_sl_mirror_suspended_until_flat`. Do not re-enter or resume mirroring until cluster net ~0 (clears flag), then allow fresh entry per §7.1 / §7.6. Other close reasons (hedge, redeem, resolution) do **not** set this flag.

**Alerts:** include net exposure, each sibling’s balance, market id, parent, cluster id.
