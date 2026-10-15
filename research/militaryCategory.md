# Military-category test: fresh-big-bet copying, realistic fills

Scripts: `scripts/research/militaryCategory.py`. Data: `data/` +
`data/universe/` now including the 9 military sibling events from
`configs/militaryUniverse.yaml` (us-x-iran-peace-deal, ceasefire-extended,
hezbollah-ceasefire-by, israel-strikes-iran-by 2026 ladder, us-strikes-iran
Oct 2025) — 1.95M extra fills, universe = 81 events. 46 of them are military
by slug keyword. Copies are $100; `retReal` pays the **next taker price in
the same market within 5 minutes** instead of the insider's own price — a
data-driven impact estimate, no optimism.

## Results

| Copy rule | n | Win% | Return | Realistic fill | Boot P(>0) | H1 / H2 | 10% slip |
|---|---:|---:|---:|---:|---:|---|---:|
| mil anyone ≥$1k ≤0.50 | 29,968 | 39% | +61% | +63% | 99% | +17% / +64% | +48% |
| **mil fresh ≥$1k ≤0.50** | 3,567 | 34% | +34% | +38% | 92% | +27% / +35% | +23% |
| **mil fresh ≥$5k ≤0.50** | 582 | 40% | +71% | **+82%** | 97% | +11% / +78% | **+58%** |
| mil fresh ≥$5k any px | 3,185 | 77% | +9% | +11% | 94% | −10% / +12% | −0% |
| non-mil fresh ≥$5k ≤0.50 (control) | 451 | 36% | +16% | +24% | 68% | +51% / −27% | +12% |

## Reading

- **This is the first strategy that survives everything**: positive mean in
  both time halves, 97–99% bootstrap probability, and it survives 10%
  adverse slippage plus the realistic-fill test. Everything previously
  tested failed at least one of these.
- The fresh signal (≤3 days old, ≤3 markets, ≥$5k, ≤0.50) beats the
  "anyone" benchmark per-copy and the non-military control collapses —
  the edge is category-specific, as hypothesized since `discoveryIdeas.md`.
- Any-price fresh copying dies (0.95+ favorites again); the ≤0.50 price cap
  is load-bearing.
- Concentration remains: `us-strikes-iran-by` alone carries $18.7k of PnL.
  H1+H2 both positive mitigates but does not remove this.
- Prior caveat carried over: this tests detection in hindsight on the fill
  tape. Live accuracy additionally needs real-time account-age tracking
  (our ages are lower bounds off the fill tape) and order-book sizing.

## Live configuration implied by the data

Copy any bet that is all of: account ≤5 days old with ≤3 markets seen so
far · single burst ≥$5k · entry price ≤0.35 · market on a military/strike
event · fill within minutes at the ask (the tape test shows the edge
survives paying up ~10%). This is implementable in real time from the
public trade tape + Gamma event tags.

## Parameter sweep (militarySweep.py, realistic fills)

36-cell grid over minUsd {2k,5k,10k,20k} × maxPrice {0.35,0.50,0.65} ×
ageDays {2,3,5}: **every cell is profitable** (P(>0) 92–99%), so the rule is
a plateau, not a tuned peak. The shipped point maximizes stability
(mean of neighbor cells) subject to sample size:

| Cell | n | retReal | P(>0) | H1 / H2 | stability |
|---|---:|---:|---:|---|---:|
| $5k @ ≤0.35, age ≤5 | 428 | +116% | 99% | +16% / +122% | +1.13 |
| $5k @ ≤0.50, age ≤5 | 622 | +85% | 98% | +9% / +94% | +0.88 |
| $10k @ ≤0.35, age ≤5 | 159 | +183% | 99% | +56% / +191% | +1.28 |

Tightening the price cap from 0.50 to 0.35 improves every cell and fixes the
weak H1. The watcher ships $5k / ≤0.35 / ≤5d (the $10k cell is stronger but
n=159 is thin for paper-trading validation; revisit as live data accrues).

Dataset-boundary check: excluding the first 30 days of the combined tape
(so no account can look artificially "fresh" from truncated history) gives
n=424, +117%, P(>0)=98% — the shipped cell is not a boundary artifact.

## Optimization findings (militaryOptimize.py, on the shipped cell)

Four policy questions answered on the n=425 shipped cell:

1. **Entry decay: none — the edge grows with delay.** Fill at the next tape
   price within 30s → +118%; within 1h → +142%. The insider's price is not
   the cheap price; drift toward resolution continues after their entry.
   Execution can be patient (limit at the ask), and the 10-min staleness
   window in `execute.py` is conservative.
2. **Exits: hold-to-resolution wins outright** — +105% vs +14% (take-profit
   2x), +3% (1.5x), +23% (stop-loss 0.5x). The longshot right tail is the
   edge; do not take profits or stop out.
3. **Liquidity: the edge survives where you can size.** 339/425 signals
   trade >1k shares/5min after entry, returning +109%; thin buckets are the
   weaker ones. Not an illiquidity artifact.
4. **Co-trade confirmation is anti-predictive** — lone fresh big bets +129%
   (38% win) vs signals with a second fresh account buying within 60s +51%
   (27% win). Synchronized fresh accounts skew to spray/speculator groups.
   Do NOT require cluster confirmation; `liveWatcher.py` correctly ignores it.

## Live system (built 2026-10-09)

- `scripts/liveWatcher.py` — running continuously: watches open military
  markets (Gamma, refreshed every 5 min), polls trade tape every 45s,
  maintains per-account state on disk, fires the sweep-selected rule, and
  logs each alert with CLOB order-book sizing (best ask + takeable shares
  within 10% of the insider's avg price). Accounts first seen during a
  market's backfill are permanently ineligible (their age is unverifiable).
- `scripts/paperPnl.py` — closes resolved signals into
  `data/live/paperPnl.csv` ($100 budget per signal, entry at best ask).
- Daily 9:23am report: closes new signals, prints cumulative paper P&L,
  restarts the watcher if it died.
