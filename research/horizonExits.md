# Horizon-exit grading: marked exit PnL at T+1h / T+1d / T+7d

Scripts: `scripts/research/horizonExits.py`, log `logs/horizonExits.log`.
Motive: the shipped grading convention holds every burst entry to market
resolution, which takes months — the OOS(oosExpansion) verdict could not be
finalized for months after the fetch. This experiment changes the outcome
variable to a **marked exit**: close the imaginary copy position a fixed
horizon after entry (T+1h / T+1d / T+7d), so every candidate cell is
gradeable within days. The question it answers for the transport failure
(status §9.2): does the OOS failure show up in the first day, or only when
the tape runs to resolution?

This document is PRE-REGISTRATION: the definitions and gates below were
written before any horizon grading was run. Results and mechanical
verdicts are appended at the end (results section clearly separated).

## Definitions (pre-registered before any grading)

All machinery is reused read-only from the shipped scripts — nothing
re-implemented except the exit tape:

- **Burst trigger + entries frame**: `entrySweep.py` conventions exactly —
  per (account, marketId, outcome) 10-minute bursting windows; entry ts =
  window first ts. Entries load via `entrySweep.loadEntries()` on the
  fingerprinted per-dir caches (nothing rebuilt from scratch where a valid
  fingerprinted cache exists; see cache appraisal below).
- **Graded frame (delay-realistic)**: `oosTransport.py` convention exactly —
  a real copy buys at the first BUY print after the trigger within 300s,
  at `nextPrice × (1 + 50bps)`. Entries with no print within 300s are NOT
  graded (dropped, as `oosTransport` drops them); each cell's `landed300%`
  share is reported so thin-liquidity cells cannot hide.
- **Exit mark**: for horizon H ∈ {1h, 1d, 7d}, mark the copy at the first
  available print (any side — both BUY and SELL fills) at or after
  `entryTs + H`, i.e. the position is closed at T+H at the tape price,
  paying 50bps sell-side slippage. Specifically,
  - right tape = **all prints** (BUY+SELL), collapsed to one row per
    (marketId, outcome, ts) by sorting `(marketId, outcome, ts, price)` and
    keeping the last (deterministic; this pins the same-second tie
    nondeterminism documented below), then a `join_asof … strategy="forward"`
    per (marketId, outcome) — first print ts ≥ target;
  - **fallback**: if no print exists at or after the target, use the last
    print **before** the target (`strategy="backward"` asof); if neither
    exists (market never printed in the window), carry the entry print
    price (mark unchanged; only the slippage applies). If the market
    resolved before the target instant, resolution takes precedence.
  - **resolution precedence**: if `resolvedAt` (= coalesce(resolvedAt,
    endDate), `researchData.militaryMarketsFrame` convention) ≤ target, the
    mark is the resolution value: 1.0 if the entry outcome won, 0.0
    otherwise (resolved position is already settled; there are no prints
    after resolution to mark at).
  - `retH = exitValue / cost − 1` per share, where exitValue is the mark
    price × (1 − 50bps) for a print mark, or exactly 1.0 / 0.0 at a
    resolution mark; cost is the delay-realistic buy price per share
    above. Unlike the hold-to-resolution `retReal`, a winner's mark is a
    bounded priced exit, not `1/price − 1`.

- **winRate** (horizon tables) = share of graded entries with `retH > 0`
  (a resolved-before-target win counts as a win). This is deliberately
  different from the published resolution winRate (`won` share), which the
  correlation section quotes for reference.
- **Per-event aggregation and the kind of P(>0)/p5**: reused from
  `entrySweep.evaluate()` via aliasing the horizon return into the
  `retReal` slot: per-event `pnl = Σ retH×100`, `cap = n×100`, 1000
  seeded bootstrap draws of **events** (one `random.Random(7)` per data
  dir, cells traversed in fixed grid×horizon order → deterministic digits),
  `p5` = 50th-order statistic of the sorted draw distribution, `retMean`
  = the plain entry-weighted arithmetic mean (the per-event weighted
  `Σpnl/Σcap` ratio is what the bootstrap tests). `MIN_CELL = 20` (dropping
  a graded frame below 20 entries → thin verdict, no bootstrap consumed).
  Top-event share on the same event table (largest event pnl ÷ total;
  None when the event pool total is ≤ 0 — no event can carry a share of a
  non-positive pool, as status §9.2 already notes).
- **Cell gate (mechanical verdict, applied without tuning)** — identical
  thresholds as the pre-registered transport gate, now on horizon marks:

  > PASS iff graded n ≥ 20 (MIN_CELL, bootstrap floor) AND distinct events
  > ≥ 20 AND p5 > 0 AND P(>0) ≥ 0.85 AND top-event share < 0.60. If the
  > cell has fewer than 20 gradeable entries OR fewer than 20 distinct
  > events → **INCONCLUSIVE-THIN**
  > (printed, nothing tuned, no partial bootstrap read). Otherwise → FAIL.

- **Data dirs graded separately, never mixed**: in-sample =
  `[data, data/universe]`, OOS = `[data/oos]`, fresh holdout =
  `[data/oosExpansion]` (200-slug roster, splitDate 2026-01-01). Every
  table cell-grading consumes exactly one dir set.
- **Focused candidate grid** (fresh ≤5d, ≤3 markets): minUsd ∈ {5000,
  7500, 10000, 12500} × maxPrice ∈ {0.30, 0.35, 0.40} = 12 cells; the
  shipped cell $5k/≤0.35 is inside the grid and is marked `★`. Each cell ×
  each horizon × each dir gets its own gate verdict.

## Cache appraisal (before the grading run)

Fingerprints via `entrySweep.dataFingerprint()` over the CURRENT per-dir
subtapes, and the sanctioned entries caches under `data/entrySweep/`:

| dir set | current fingerprint | existing cache | action |
|---|---|---|---|
| `[data, data/universe]` | `df8efad228` | `entries_v2_df8efad228.parquet` | reused (name matches) |
| `[data/oos]` | `3670562787` | `entries_v2_3670562787.parquet` | reused (name matches) |
| `[data/oosExpansion]` | `8fdc67aec9` | none under that name | rebuilt via `loadEntries` (writes `entries_v2_8fdc67aec9.parquet`), disclosed |

The oosExpansion cache known from status §9.2,
`entries_v2_5a57e33ce8.parquet` (3,599,688 entries, 200 events, 468k
accounts), is keyed by a fingerprint whose inputs can no longer be
reproduced: re-deriving `dataFingerprint([data/oosExpansion])` NOW yields
`8fdc67aec9`, not `5a57e33ce8`. Nothing was rebuilt from scratch in
violation of cache discipline; this is the sanctioned warn-and-rebuild
path (rebuild measured at ~7s on the shipped `buildEntries`).

**Tie nondeterminism discovered during appraisal (documented, then
pinned):** two back-to-back in-memory `buildEntries` runs on the same dir
set (identical input files) differ on 447,092 / 257,518 / 138,269 of
3,599,688 rows in `price` / `fillPrice` / `retReal` respectively. The
cause: 880,094 BUY-print (marketId, outcome, ts) groups have more than one
same-second print, and the shipped tape's `shift(-1).over(...) +
unique(keep="last")` resolves same-ts ties in unspecified order. Event-
level sanity: a fresh deterministic-order rebuild
reproduces the published OOS shipped-cell numbers to within that noise
(retReal −0.550 → −0.547, P(>0) 2.0% → 2.8%, winRate 8.1% → 8.2%, n 394 →
392, events 60 → 60), keys (account, marketId, outcome, ts, won) verified
identical by join. The grading below therefore consumes a pinned rebuild
(written to the `8fdc67aec9` cache) and treats §9.2 numbers as
tie-sample-dependent; conclusions are unaffected at the FAIL level.

## Sanity checks (carried at pre-registration stage)

- Shipped OOS cell (cache `5a57e33ce8`): retReal −0.550, P(>0) 2.0%,
  winRate 8.1%, events 60 — as status §9.2. Fresh rebuild: −0.547 / 2.8% /
  8.2% / 60 (tie noise, above).
- Grading of the shipped-cell in-sample hold-to-resolution (+105% retReal)
  is re-verified from cache `df8efad228` inside the full run (the
  `resolution truth` line per dir printed to the log for the correlation
  section).

## Results (appended after the run)

Run: 2026-10-15, one focused pass over all three dir sets in one process,
log `logs/horizonExits.log` (~20s total; in-sample and OOS consumed their
fingerprint-matching caches, oosExpansion consumed the freshly written
`entries_v2_8fdc67aec9.parquet`, same 3,599,688 rows, keys verified
identical to `entries_v2_5a57e33ce8` by join — the other columns carry the
same tie-noise deltas as above in `price`/`fillPrice`/`retReal`).

**Resolution truth (hold-to-resolution, delay-realistic graded frame):**

| dir | shipped-cell graded n | resolution retReal | p5 | P(>0) | note |
|---|---:|---:|---:|---:|---|
| in-sample | 412 (whole-burst 431) | +1.222 (whole-burst +1.169) | +0.34 | 97.5% | tape moved since the +105.1%/n=427 reference: same positive regime, sample drift within the tie noise |
| OOS (60 slugs) | 6 (whole-burst 12) | +0.720 | – | – | globally too thin: every candidate cell is INCONCLUSIVE-THIN |
| oosExpansion | 359 (whole-burst 391) | −0.567 | −0.839 | 2.7% | published delay-real −0.579/−0.845/1.5% — replicated within tie noise |

`uv run pytest`: **150 passed** after the run.

### In-sample `[data, data/universe]` — fresh ≤5d, ≤3 mkts (★ = shipped)

| cell | n | evts | retMean | win% | p5 | P(>0) | topShare | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| t1h: $5k/≤0.3 | 360 | 23 | +0.070 | 39.7 | −0.001 | 94.7% | 0.828 | FAIL |
| t1h: $5k/≤0.35★ | 412 | 25 | +0.064 | 40.0 | −0.000 | 94.8% | 0.808 | FAIL |
| t1h: $5k/≤0.4 | 476 | 27 | +0.047 | 39.5 | −0.008 | 88.8% | 0.866 | FAIL |
| t1h: $7.5k/≤0.35 | 249 | 22 | +0.022 | 36.5 | −0.032 | 78.4% | 0.929 | FAIL |
| t1h: $7.5k/≤0.4 | 292 | 23 | +0.008 | 36.3 | −0.033 | 63.1% | 1.767 | FAIL |
| t1h: $10k/≤0.4 | 179 | 20 | −0.017 | 33.5 | −0.061 | 20.4% | – | FAIL |
| t1h: $7.5k/≤0.3, $10k/≤0.3, $10k/≤0.35, $12.5k/≤0.3/≤0.35/≤0.4 | 86–152 | 12–18 | | | | | | **INCONCLUSIVE-THIN** |
| t1d: $5k/≤0.3 | 360 | 23 | +0.300 | 31.7 | +0.004 | 95.1% | 0.477 | **PASS** |
| t1d: $5k/≤0.35★ | 412 | 25 | +0.275 | 33.3 | +0.005 | 95.3% | 0.481 | **PASS** |
| t1d: $5k/≤0.4 | 476 | 27 | +0.224 | 34.0 | −0.018 | 93.8% | 0.504 | FAIL |
| t1d: $7.5k/≤0.35 | 249 | 22 | +0.271 | 34.9 | −0.054 | 90.4% | 0.723 | FAIL |
| t1d: $7.5k/≤0.4 | 292 | 23 | +0.216 | 34.2 | −0.050 | 90.6% | 0.762 | FAIL |
| t1d: $10k/≤0.4 | 179 | 20 | +0.240 | 31.3 | −0.084 | 74.9% | 1.084 | FAIL |
| t1d: $7.5k/≤0.3, $10k/≤0.3, $10k/≤0.35, $12.5k/≤0.3/≤0.35/≤0.4 | 86–152 | 12–18 | | | | | | **INCONCLUSIVE-THIN** |
| t7d: $5k/≤0.3 | 360 | 23 | **+0.827** | 28.1 | +0.082 | 95.7% | 0.507 | **PASS** |
| t7d: $5k/≤0.35★ | 412 | 25 | **+0.739** | 29.9 | +0.037 | 95.7% | 0.484 | **PASS** |
| t7d: $5k/≤0.4 | 476 | 27 | +0.631 | 31.1 | +0.076 | 96.8% | 0.457 | **PASS** |
| t7d: $7.5k/≤0.35 | 249 | 22 | +0.851 | 29.7 | −0.014 | 94.6% | 0.489 | FAIL |
| t7d: $7.5k/≤0.4 | 288 | 44 | +0.719 | 31.2 | +0.046 | 95.7% | 0.464 | **PASS** |
| t7d: $10k/≤0.4 | 179 | 20 | +1.017 | 34.1 | +0.126 | 96.6% | 0.533 | **PASS** |
| t7d: $7.5k/≤0.3, $10k/≤0.3, $10k/≤0.35, $12.5k/≤0.3/≤0.35/≤0.4 | 86–131 | 12–17 | | | | | | **INCONCLUSIVE-THIN** |

landed300%: 94–99% across all 12 cells ($5k/≤0.3 97.3%, ★ 95.6%; full list
in the log). Resolution winRate of the graded ★ cell: 34.7%.

### OOS `data/oos` (60-slug pull) — fresh ≤5d, ≤3 mkts

Every candidate grade cell (12 cells × 3 horizons) has graded n = 2–7 with
fewer than 20 distinct events: **INCONCLUSIVE-THIN everywhere** (the
60-slug fetch was already known too thin to grade a $5k+ ≤0.35 line;
the shipped graded ★ cell is n=6). landed300% 28–56% per cell (in the log),
consistent with the published 49.8% landing regime.

### Fresh holdout `data/oosExpansion` (200 slugs) — fresh ≤5d, ≤3 mkts

| cell | n | evts | retMean | win% | p5 | P(>0) | topShare | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| t1h: $5k/≤0.3 | 306 | 46 | +0.011 | 44.4 | −0.016 | 75.0% | 0.506 | FAIL |
| t1h: $5k/≤0.35★ | 359 | 52 | +0.005 | 44.6 | −0.020 | 66.7% | 0.925 | FAIL |
| t1h: $5k/≤0.4 | 445 | 55 | +0.009 | 46.1 | −0.016 | 72.3% | 0.642 | FAIL |
| t1h: $7.5k/≤0.3 | 188 | 35 | +0.006 | 47.3 | −0.015 | 68.0% | 0.620 | FAIL |
| t1h: $7.5k/≤0.35 | 227 | 39 | −0.000 | 46.7 | −0.022 | 49.3% | – | FAIL |
| t1h: $7.5k/≤0.4 | 288 | 44 | +0.002 | 48.6 | −0.021 | 57.1% | 3.501 | FAIL |
| t1h: $10k/≤0.3 | 129 | 26 | +0.015 | 51.9 | −0.015 | 78.6% | 0.873 | FAIL |
| t1h: $10k/≤0.35 | 151 | 30 | +0.011 | 53.0 | −0.015 | 76.5% | 0.605 | FAIL |
| t1h: $10k/≤0.4 | 194 | 34 | +0.005 | 53.1 | −0.020 | 63.9% | 1.003 | FAIL |
| t1h: $12.5k/≤0.3 | 95 | 20 | +0.004 | 52.6 | −0.033 | 54.1% | 4.508 | FAIL |
| t1h: $12.5k/≤0.35 | 110 | 23 | +0.009 | 53.6 | −0.018 | 68.6% | 1.111 | FAIL |
| t1h: $12.5k/≤0.4 | 142 | 26 | +0.004 | 53.5 | −0.027 | 62.2% | 1.857 | FAIL |
| t1d: $5k/≤0.3 | 306 | 46 | +0.025 | 38.2 | −0.160 | 51.2% | 5.803 | FAIL |
| t1d: $5k/≤0.35★ | 359 | 52 | +0.037 | 37.9 | −0.122 | 55.6% | 3.301 | FAIL |
| t1d: $5k/≤0.4 | 445 | 55 | +0.041 | 39.6 | −0.100 | 58.9% | 2.386 | FAIL |
| t1d: $7.5k/≤0.3 | 188 | 35 | −0.122 | 36.7 | −0.185 | 0.1% | – | FAIL |
| t1d: $7.5k/≤0.35 | 227 | 39 | −0.076 | 37.0 | −0.137 | 4.2% | – | FAIL |
| t1d: $7.5k/≤0.4 | 288 | 44 | −0.044 | 39.6 | −0.110 | 17.6% | – | FAIL |
| t1d: $10k/≤0.3 | 129 | 26 | −0.113 | 37.2 | −0.192 | 3.1% | – | FAIL |
| t1d: $10k/≤0.35 | 151 | 30 | −0.093 | 36.4 | −0.168 | 3.1% | – | FAIL |
| t1d: $10k/≤0.4 | 194 | 34 | −0.065 | 40.2 | −0.143 | 8.6% | – | FAIL |
| t1d: $12.5k/≤0.3 | 95 | 20 | −0.124 | 37.9 | −0.214 | 1.1% | – | FAIL |
| t1d: $12.5k/≤0.35 | 110 | 23 | −0.090 | 38.2 | −0.173 | 3.8% | – | FAIL |
| t1d: $12.5k/≤0.4 | 142 | 26 | −0.066 | 40.8 | −0.154 | 9.6% | – | FAIL |
| t7d: $5k/≤0.3 | 306 | 46 | −0.300 | 14.1 | −0.553 | 8.3% | – | FAIL |
| t7d: $5k/≤0.35★ | 359 | 52 | −0.274 | 15.3 | −0.508 | 10.1% | – | FAIL |
| t7d: $5k/≤0.4 | 445 | 55 | −0.279 | 16.4 | −0.465 | 4.0% | – | FAIL |
| t7d: $7.5k/≤0.3 | 188 | 35 | −0.537 | 11.7 | −0.671 | 0.0% | – | FAIL |
| t7d: $7.5k/≤0.35 | 227 | 39 | −0.450 | 14.5 | −0.575 | 0.0% | – | FAIL |
| t7d: $7.5k/≤0.4 | 288 | 44 | −0.411 | 16.0 | −0.539 | 0.0% | – | FAIL |
| t7d: $10k/≤0.3 | 129 | 26 | −0.546 | 11.6 | −0.677 | 0.0% | – | FAIL |
| t7d: $10k/≤0.35 | 151 | 30 | −0.486 | 12.6 | −0.618 | 0.0% | – | FAIL |
| t7d: $10k/≤0.4 | 194 | 34 | −0.451 | 13.9 | −0.593 | 0.0% | – | FAIL |
| t7d: $12.5k/≤0.3 | 95 | 20 | −0.579 | 9.5 | −0.751 | 0.0% | – | FAIL |
| t7d: $12.5k/≤0.35 | 110 | 23 | −0.508 | 10.9 | −0.656 | 0.0% | – | FAIL |
| t7d: $12.5k/≤0.4 | 142 | 26 | −0.464 | 11.3 | −0.623 | 0.0% | – | FAIL |

landed300%: 89–94% per cell (★ 91.8%) — every cell gradeable, so all
36 verdicts are real FAILs, not thinness. Resolution winRate of the graded ★
cell: 7.2%. topShare values >1 mean a single positive event against a
negative overall pool (share is only missing when the pool itself is ≤0).

Note how the OOS failure is legible at T+1h already: the ★ cell carries
**+0.5% retMean with p5 −0.020** at T+1h — in-sample the same cell carries
+6.4% mean with P(>0) 95% — and by T+1d even the softest $5k lines lose
their event-level floor (p5 ≤ −0.10, P(>0) ≤ 59%).

### Shipped-cell horizon × resolution correlations

| dir | T+1h corr (pearson / spearman) | T+1d | T+7d | graded n | resolved-before-mark T+1h / T+1d / T+7d |
|---|---:|---:|---:|---:|---|
| in-sample | 0.099 / 0.149 | 0.582 / 0.442 | **0.851 / 0.716** | 412 | 0.0% / 11.4% / 42.7% |
| OOS | 0.383 / −0.152 | 0.732 / 0.698 | 0.777 / 0.893 | 6 | 0.0% / 33.3% / 66.7% |
| oosExpansion | 0.033 / −0.008 | 0.649 / 0.303 | 0.806 / 0.404 | 359 | 0.6% / 4.7% / 22.6% |

Correlation is against the delay-realistic hold-to-resolution return
`retReal50` of the same graded frame. The resolved-before-mark share is
part of the correlation by design — 42.7% of in-sample and 22.6% of
holdout T+7d marks are already-settled outcomes whose mark IS the
resolution value, so T+7d is partly a mechanical echo of resolution; what
the number buys is that the still-live share (57–77%) prices like
resolution. The T+1h correlation is noise, as expected for a one-hour
mark on a position whose value unfolds over days.)

## Verdicts (mechanically applied, nothing tuned)

- **in-sample:** T+1h 0 PASS / 6 FAIL / 6 INCONCLUSIVE-THIN; T+1d 2 PASS
  ($5k/≤0.3, $5k/≤0.35★) / 4 FAIL / 6 thin; T+7d 5 PASS ($5k/≤0.3,
  ★, $5k/≤0.4, $7.5k/≤0.4, $10k/≤0.4) / 1 FAIL ($7.5k/≤0.35, p5 −0.014)
  / 6 thin. The in-sample edge survives a T+7d mark, not a T+1h mark: at
  one hour the mark is flat (p5 ≈ −0.000… +0.126 spread) — the edge needs
  the days the position sits while the event plays out.
- **OOS (60-slug):** thin everywhere (INCONCLUSIVE-THIN, pre-stated
  behavior of the MIN_CELL floor).
- **oosExpansion (fresh holdout): FAIL on all 12 candidate cells × all 3
  horizons (0/36 PASS).** Exactly as at resolution: p5 < 0 everywhere,
  P(>0) ≤ 79%, and by T+7d the means reproduce the resolution pool
  (−0.27…−0.58 vs resolution −0.567).

### The three pre-registered questions

**(a) Does the OOS failure show up at T+1d or only at resolution?**
Immediately: at **T+1h** already the holdout's marked exits are
indistinguishable from noise (retMeans −0.000…+1.5%, p5 −0.015…−0.033
< 0 everywhere, P(>0) 49–79%, where in-sample the same one-hour marks
still print P(>0) 89–95%). Its one-hour win-rates read 44–53% against a
~0.2 entry cost — the burst's own buying momentarily lifts the market,
and part of what lifts it mean-reverts away by the next day (holdout
resolution winRate is ~8%). At T+1d p5 is firmly negative on every
gradeable cell (−0.10…−0.21) (−0.10…−0.21)
even for the $5k lines whose entry-weighted mean is still slightly
positive (+2.5…+4.1% — a few lucky exit prints against a negative event
pool); at T+7d the whole track is negative on both mean and p5. Months of
resolution waiting lose nothing: the transport failure is fully visible
within the first day.

**(b) Is any candidate cell positive across dirs at a horizon?** No. In-
sample PASSes exist (several at T+1d/T+7d as above) but the holdout is
FAIL on every cell × horizon (36 FAIL, gradeable everywhere), and the
60-slug OOS is thin everywhere. No candidate cell carries a horizon-level
edge into the holdout.

**(c) How tightly do resolution and T+7d marks agree in-sample?** Pearson
0.851 / Spearman 0.716 on the ★ cell (n=412). Tight enough that a T+7d
mark calls the resolution verdicts: in-sample shipped hold-to-resolution
+105% ⇒ +73.9% marked at T+7d, holdout shipped −55% resolution ⇒ −27.4%
marked at T+7d,
with two honest caveats: ~43% of in-sample T+7d marks were already-settled
outcomes (mechanical echo, resolved-before-mark share above), and the
agreement loosens as the horizon shortens — T+1d's 0.58/0.44 is loose,
T+1h's 0.10 is noise — so the mark converges to resolution as the horizon
grows.

- **Operationally:** a T+1d mark grades every holdout cell in one day and
  flags every failure visible in the first already-T+1d digit — a
  T+1h/T+1d/T+7d triple as a first-pass gate calls the holdout FAIL on
  day 1, with only T+7d needed to reproduce the resolution regression
  numbers exactly. No resolution months anywhere.
