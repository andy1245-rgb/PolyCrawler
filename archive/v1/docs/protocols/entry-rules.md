# Protocol 3 — Entry Rules

**Source:** spec.md §7 | docs/architecture.md §6

---

Entry is **not** gated by cluster score. Entry applies when a flagged parent's cluster develops non-zero net exposure in a market.

## 7.1 Entry conditions

All conditions must pass. Evaluated on cluster net after processing all sibling events in the poll batch (timestamp order).

| Rule | Config key | Default |
|------|------------|---------|
| Cluster position state is `WATCHING` and not `tp_sl_suspended` | — | required |
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

## 7.4 Post-entry fast polling

After entry, poll at higher frequency for a short window:

```yaml
entry:
  postEntryPollIntervalSec: 10
  postEntryPollCount: 6   # 6 × 10s = 1 minute fast window
```

## 7.5 Intra-fill hedges

When one wallet buys both Yes and No in a single fill:

| Mode | Behavior | Default |
|------|----------|---------|
| `net_only` | Each leg updates balance → cluster net = sum(Yes) − sum(No) | **Yes** |
| `filter_before_net` | Inspect each fill: if one side >2× the other, count dominant only; else ignore entire fill | No |

Prefer `net_only` so event path and reconciliation path share the same shape. See spec §7.5 for full worked examples.

## 7.6 Follow re-entry after flat net

If cluster net goes ~0 then becomes non-zero again within `reentryWindowMinutes`, treat as new entry (subject to §7.1 rules).

## 7.7 Net cluster mirroring

Siblings share the same parent; the cluster is one trading entity. Position is mirrored at the cluster level using the formula in §7.3.
