# Favorite-side burst copy: does a gradeable OOS cell exist anywhere?

**Pre-registration (written before any grading run; the script, the grid, the gates
and the conventions below are all fixed before the first evaluate() call).**
Script: `scripts/research/favoriteBursts.py`. Machinery: import, never fork —
`entrySweep.loadEntries` (per-dir fingerprint cache), `entrySweep.filterCell` /
`evaluate` (1000-draw per-event pnl/cap bootstrap, 2025-06-01 half split,
MIN_CELL), and `oosTransport.addLanded` / `delayRealReturn` for the
delay-realistic pricing. Nothing re-implemented, nothing tuned against the data.

## Hypothesis under test

The control cell on the fresh holdout (all $10k+ bursts, any price/age: ret +1.1%,
winRate 90.9%, n=16,896 — research/status.md §9.2) shows the military burst tape's
winners concentrate on favorites. The shipped longshot-copy line (≤0.35) is OOS-dead
on both pulls. Question: is there ANY cell of LARGE bursts on HIGH-priced favorites
(burst ≥ $5k, burst-average price ≥ 0.55) that is gradeable and passes out-of-sample
— i.e. does the favorite-copy family have a transportable film anywhere on the
(burst-size × price-band) surface? And as the opposite-extreme control: are large
bursts at ≤ 0.15 (deep lottery) the other dead end, so that the OOS failure is
MONOTONE in price across the whole ladder (which would make "price" the axis that
matters, not burst size or age)?

## Data dirs (graded separately, never mixed)

- **INS** `[data, data/universe]` — reference only (the hypothesis originates here).
- **OOS** `[data/oos]` — 60-slug pull (research/status.md §9.1/§9.2 era).
- **HOLD** `[data/oosExpansion]` — 200-slug fresh holdout (10.66M fills), the
  deciding dir.

Universe per dir: the military/strike event slugs (entrySweep's MILITARY tuple via
`militaryMarketsFrame`), burst entries = per (account, marketId, outcome) 10-minute
BUY windows, entry price = the burst's running average, held-to-resolution only
(unresolved entries dropped by the cache's ret-null filter).

## Pre-registered grid

- **Burst size:** `minUsd ∈ {$5k, $10k}` (usd ≥; no upper bound).
- **Price bands** on the burst-average entry price (bucket [lo, hi); the last
  rung is ≤ 1.0):
  - ladder rungs: `p ∈ [0,0.15)`, `[0.15,0.35)`, `[0.35,0.55)`, `[0.55,0.70)`,
    `[0.70,0.85)`, `[0.85,1.0]` — the six rungs serve the monotonicity question;
  - wide favorite band `[0.55,0.85)` (the pre-registered "favorite-copy" cell shape);
  - wide sub-favorite band `p ≤ 0.85` (everything below the heavy-favorite rung).
- **Age windows:** `0–1d` (ageDays > 0 & ≤ 1 — the OOS big bursts sit on day-0/1
  accounts, so this band is mandatory) and `≤5d` (ageDays ≤ 5, the shipped
  fresh shape). Age min is 0 for the 5d window (> -inf; i.e. no lower gate).
- **Account maturity:** marketsSoFar ≤ 3 (the shipped fresh shape), candidate
  cells only.
- **Control/anchor (not a candidate, reported for soundness):** `usd ≥ $10k`,
  ANY price, ANY age, ANY marketsSoFar — reproduces the status.md §9.2 control.

## Pre-registered gates (identical for hold-to-resolution and delay-realistic)

- **MIN_CELL = 20 entries.** Below → **INCONCLUSIVE-THIN** (no PASS/FAIL verdict).
- **PASS** iff n ≥ 20 AND p5 > 0 AND P(>0) ≥ 85% AND top-event pnl share < 60%.
- **FAIL** iff n ≥ 20 and any gate condition fails.
- Verdicts are per cell per dir per pricing convention; a cell is a transportable
  candidate only if it passes on BOTH OOS and HOLD (HOLD is the deciding dir).

## Pre-registered delay-realistic convention (research/status.md engineParity rule)

A delayed copy enters on the FIRST BUY print after the trigger in the same
(marketId, outcome) within a 300s fill window, priced at that print + 50bps
slippage. Entries whose window never lands are DROPPED (not repriced at the
trigger). `landed%` reported per cell. Both conventions graded for every cell:
`retReal` (cache convention: next-print fill price, trigger-price fallback) at
hold-to-resolution, and `drRetReal50` (dropped-if-no-land) for delay-realistic.

## Reported per cell

n, events, winRate (fraction of entries with ret > 0), ret, p5, P(>0),
top-event pnl share, h1/h2 (2025-06-01 split), landed%, and the delay-realistic
n / ret / p5 / P(>0). Bootstrap seed 7 per dir (same as the oosTransport runs).

(Results and verdicts appended below after the run.)

## Results (run 2026-10-17, `logs/favoriteBursts.log`)

- Machinery run as pre-registered: `esw.loadEntries` per dir (cache fingerprints:
  INS `entries_v2_df8efad228`, OOS `entries_v2_3670562787` — both hit; HOLD
  fingerprint missed because its digest inputs (stat/mtime/rows) drifted since the
  Oct-15 build — rebuilt with the same schema → **3,599,688 entries, bit-count
  identical to the documented tape**, then graded), `oot.addLanded` next-print
  tape per dir, `oot.evalCell` (=`esw.evaluate` + top-event share), bootstrap
  seed 7 per dir. `dr` columns = delay-realistic (300s window, next BUY print,
  +50bps, never-landed dropped); `drShare`/`share` = top-event pnl share of the
  (positive-or-negative) total; values >100% mean offsets elsewhere in the
  pool. Two minor regressions were fixed before any verdict was read: a key-name
  mapping (P>0/share/landed) and the ladder's landed join — no cell semantics
  were touched.
- Sibling-agent note: `entrySweep.py`/`oosTransport.py` gained a strictly
  ADDITIVE `--episodes` / `episodeUnits` path (flag off = exactly the shipped
  behavior) mid-task; this run executes the default path, unchanged from the
  status.md conventions.

### Soundness anchors (pre-registered control: usd ≥ $10k, ANY price/age/markets)

| dir | n | evts | winRate | ret | p5 | P(>0) | share | dr n / ret / p5 / share | verdict |
|---|---|---|---|---|---|---|---|---|---|
| HOLD | 16,896 | 183 | 90.9% | +1.1% | −0.001 | 94% | 47% | 14987 / +0.7% / −0.006 / 68% | FAIL |
| OOS | 331 | 52 | 94% | +4.8% | +0.022 | 100% | 20% | 226 / +5.9% / +0.019 / 30% | PASS |
| INS | 17,761 | 45 | 81.8% | +0.6% | −0.024 | 66% | 152% | 16747 / +0.3% / −0.034 / 290% | FAIL |

The status.md §9.2 control cell reproduces EXACTLY on HOLD (n=16,896, retReal
+1.1%, winRate 90.9%) — tape/winner coding verified against the frozen numbers.
But held to the same gates as a candidate, the anchor itself is NOT a strategy:
its +1.1% has p5 ≈ 0.000 (dr −0.006) and 47–68% single-event concentration. There
is no favorite-copy "control edge" to transport — the smooth ret was survivor
pool composition, not a graded distribution. (On INS the anchor's ret is a mix of
+113%/+119% longshot cells against −13–26% favorite cells.)

### HOLD (data/oosExpansion — the deciding dir): all 32 gradeable cells FAIL; 1 INCON-THIN; 0 PASS

| cell | n | evts | winRate | ret | p5 | P(>0) | share | h1/h2 | landed300 | delay-real n / ret / p5 / P(>0) / share | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $5k p<0.15 0-1d | 67 | 27 | 3% | −52.3% | −1.000 | 9% | 100% | −100%/−48% | 94.0% | 63 / −49.5% / −1.000 / 10% / 100% | FAIL |
| $5k p<0.15 5d | 106 | 29 | 5% | −31.5% | −1.000 | 29% | 100% | −100%/−27% | 95.3% | 101 / −28.4% / −1.000 / 30% / 100% | FAIL |
| $5k 0.15-0.35 0-1d | 187 | 42 | 12% | −52.8% | −0.766 | 3% | 100% | −19%/−62% | 88.8% | 166 / −61.5% / −0.827 / 1% / 100% | FAIL |
| $5k 0.15-0.35 5d | 283 | 48 | 10% | −62.3% | −0.799 | 0% | 100% | −41%/−68% | 90.5% | 256 / −67.9% / −0.840 / 0% / 100% | FAIL |
| $5k 0.35-0.55 0-1d | 251 | 49 | 34% | −28.0% | −0.431 | 2% | 100% | −27%/−29% | 84.9% | 213 / −30.8% / −0.464 / 3% / 100% | FAIL |
| $5k 0.35-0.55 5d | 355 | 50 | 35% | −23.9% | −0.450 | 5% | 100% | −32%/−20% | 87.6% | 311 / −26.2% / −0.469 / 4% / 100% | FAIL |
| $5k 0.55-0.70 0-1d | 321 | 50 | 73% | +18.8% | +0.007 | 96% | 43% | 34%/14% | 85.4% | 274 / +18.6% / −0.002 / 94% / 50% | FAIL |
| $5k 0.55-0.70 5d | 435 | 54 | 73% | +18.1% | −0.006 | 94% | 55% | 30%/15% | 88.0% | 383 / +18.0% / −0.039 / 90% / 60% | FAIL |
| $5k 0.70-0.85 0-1d | 401 | 62 | 83% | +7.7% | −0.067 | 80% | 58% | 1%/9% | 81.3% | 326 / +8.5% / −0.051 / 85% / 59% | FAIL |
| $5k 0.70-0.85 5d | 574 | 64 | 84% | +8.5% | −0.058 | 87% | 53% | −1%/10% | 84.0% | 482 / +9.3% / −0.048 / 86% / 57% | FAIL |
| $5k p≥0.85 0-1d | 2,551 | 140 | 98% | +1.1% | −0.006 | 86% | 66% | −1%/2% | 87.8% | 2240 / +0.6% / −0.014 / 72% / 121% | FAIL |
| $5k p≥0.85 5d | 3,403 | 144 | 98% | +1.4% | −0.004 | 91% | 52% | 0%/2% | 87.0% | 2962 / +1.0% / −0.011 / 80% / 80% | FAIL |
| $5k fav 0.55-0.85 0-1d | 722 | 80 | 79% | +12.6% | −0.029 | 91% | 47% | 19%/11% | 83.1% | 600 / +13.1% / −0.018 / 92% / 53% | FAIL |
| $5k fav 0.55-0.85 5d | 1,009 | 81 | 79% | +12.7% | −0.008 | 93% | 54% | 16%/12% | 85.7% | 865 / +13.1% / −0.018 / 93% / 59% | FAIL |
| $5k p<0.85 w 0-1d | 1,227 | 95 | 55% | −9.2% | −0.171 | 3% | 100% | −4%/−11% | 84.9% | 1042 / −11.5% / −0.201 / 2% / 100% | FAIL |
| $5k p<0.85 w 5d | 1,753 | 97 | 55% | −9.5% | −0.179 | 5% | 100% | −12%/−9% | 87.5% | 1533 / −11.1% / −0.210 / 3% / 100% | FAIL |
| $10k p<0.15 0-1d | 19 | 0 | – | – | – | – | – | –/– | 100% | 19 / – / – / – | INCON-THIN |
| $10k p<0.15 5d | 36 | 11 | 0% | −100% | −1.000 | 0% | 100% | –/−100% | 100% | 36 / −100% / −1.000 / 0% / 100% | FAIL |
| $10k 0.15-0.35 0-1d | 82 | 20 | 15% | −50.1% | −0.764 | 7% | 100% | −2%/−66% | 85.4% | 70 / −65.7% / −0.886 / 3% / 100% | FAIL |
| $10k 0.15-0.35 5d | 129 | 27 | 11% | −62.9% | −0.822 | 1% | 100% | −18%/−73% | 88.4% | 114 / −72.9% / −0.889 / 0% / 100% | FAIL |
| $10k 0.35-0.55 0-1d | 111 | 31 | 27% | −42.0% | −0.639 | 0% | 100% | −27%/−54% | 78.4% | 87 / −46.2% / −0.655 / 0% / 100% | FAIL |
| $10k 0.35-0.55 5d | 150 | 36 | 31% | −32.9% | −0.565 | 1% | 100% | −32%/−33% | 83.3% | 125 / −33.6% / −0.598 / 2% / 100% | FAIL |
| $10k 0.55-0.70 0-1d | 142 | 33 | 68% | +9.2% | −0.136 | 74% | 115% | 6%/10% | 83.8% | 119 / +8.7% / −0.169 / 67% / 144% | FAIL |
| $10k 0.55-0.70 5d | 179 | 36 | 68% | +9.0% | −0.144 | 72% | 120% | 9%/9% | 85.5% | 153 / +8.5% / −0.173 / 70% / 143% | FAIL |
| $10k 0.70-0.85 0-1d | 182 | 42 | 82% | +6.2% | −0.121 | 74% | 88% | 13%/5% | 80.8% | 147 / +8.0% / −0.120 / 77% / 73% | FAIL |
| $10k 0.70-0.85 5d | 262 | 46 | 84% | +7.9% | −0.090 | 80% | 64% | 8%/8% | 85.1% | 223 / +10.1% / −0.073 / 86% / 55% | FAIL |
| $10k p≥0.85 0-1d | 1,715 | 111 | 99% | +1.9% | +0.005 | 99% | 57% | 1%/2% | 91.0% | 1560 / +1.4% / −0.002 / 91% / 80% | FAIL |
| $10k p≥0.85 5d | 2,219 | 116 | 99% | +2.1% | +0.005 | 99% | 53% | 1%/2% | 90.3% | 2004 / +1.6% / −0.002 / 92% / 72% | FAIL |
| $10k fav 0.55-0.85 0-1d | 324 | 57 | 76% | +7.5%* | −0.091 | 78% | 97% | 9%/7% | 82.1% | 266 / +8.3% / −0.115 / 77% / 106% | FAIL |
| $10k fav 0.55-0.85 5d | 441 | 59 | 77% | +8.4% | −0.085 | 80% | 86% | 9%/8% | 85.3% | 376 / +9.4% / −0.084 / 82% / 87% | FAIL |
| $10k p<0.85 w 0-1d | 536 | 68 | 54% | −15.3% | −0.245 | 0% | 100% | −6%/−18% | 82.5% | 442 / −18.8% / −0.292 / 0% / 100% | FAIL |
| $10k p<0.85 w 5d | 756 | 70 | 53% | −17.1% | −0.251 | 0% | 100% | −10%/−19% | 86.1% | 651 / −19.3% / −0.296 / 0% / 100% | FAIL |

*typo-guard: +7.5% (positive; the fav band mixes the +9% mid rung with the +2%
≥0.85 rung).

The knife-edge is informative, not a pass: the $10k ≥0.85 cells pass the native
p5 gate (+0.005) and P(>0) 0.986–0.992 — and then die twice under the
pre-registered delay-realistic evaluation: dr p5 −0.002 (the +50bps next-print
entry consumes the entire ret) and dr top-event share 72%/80% (> the 60% gate).
Win 98–99% at +1–2% ret per burst IS the mechanical no-edge signature: you buy
near-money at market, and the ~1% price drift between burst-average and your
next-print is the whole "edge".

### OOS (data/oos, 60 slugs): 16 gradeable cells → 5 PASS / 11 FAIL; 17 INCON-THIN

| cell | n | evts | winRate | ret | p5 | P(>0) | share | h1/h2 | landed300 | delay-real n / ret / p5 / P(>0) / share | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| $5k p<0.15 both | 1 | 0 | – | – | – | – | – | –/– | 100% | 1 / – / – / – | INCON-THIN |
| $5k 0.15-0.35 both | 10/11 < 20 | 0 | ~40% | – | – | – | – | –/– | 45–50% | 5 / – / – / – | INCON-THIN |
| $5k 0.35-0.55 both | 14/16 | 0 | 56–64% | – | – | – | – | –/– | 56–57% | 8–9 / – / – / – | INCON-THIN |
| $5k 0.55-0.70 both | 16/19 | 0 | 50–58% | – | – | – | – | –/– | 56–63% | 9–12 / – / – / – | INCON-THIN |
| $5k 0.70-0.85 0-1d | 32 | 16 | 81% | +2.4% | −0.225 | 60% | 177% | 4%/2% | 75.0% | 24 / +4.2% / −0.269 / 65% / 130% | FAIL |
| $5k 0.70-0.85 5d | 43 | 18 | 77% | −3.3% | −0.312 | 47% | 100% | 4%/−8% | 79.1% | 34 / −4.3% / −0.313 / 46% / 100% | FAIL |
| $5k p≥0.85 0-1d | 181 | 42 | 100% | +3.0% | +0.022 | 100% | 7% | 3%/3% | 69.6% | 126 / +2.3% / +0.015 / 100% / 13% | PASS |
| $5k p≥0.85 5d | 229 | 43 | 100% | +3.2% | +0.023 | 100% | 12% | 3%/3% | 65.9% | 151 / +2.5% / +0.016 / 100% / 13% | PASS |
| $5k fav 0.55-0.85 0-1d | 48 | 22 | 71% | −5.9% | −0.333 | 38% | 100% | −6%/−6% | 68.8% | 33 / −1.2% / −0.358 / 53% / 100% | FAIL |
| $5k fav 0.55-0.85 5d | 62 | 23 | 71% | −5.4% | −0.318 | 39% | 100% | −4%/−7% | 74.2% | 46 / −2.7% / −0.325 / 50% / 100% | FAIL |
| $5k p<0.85 w 0-1d | 73 | 23 | 64% | +6.7% | −0.058 | 77% | 84% | 7%/7% | 64.4% | 47 / +11.4% / −0.101 / 80% / 75% | FAIL |
| $5k p<0.85 w 5d | 90 | 24 | 63% | +1.5% | −0.106 | 57% | 304% | −1%/4% | 67.8% | 61 / +5.8% / −0.163 / 67% / 115% | FAIL |
| $10k ≤0.85 (8 cells below 0.85) | 0–16 < 20 | 0 | – | – | – | – | – | –/– | 25–63% | 0–10 / – / – / – | INCON-THIN |
| $10k p≥0.85 0-1d | 86 | 30 | 100% | +2.4% | +0.014 | 100% | 20% | 2%/2% | 76.7% | 66 / +2.1% / +0.009 / 100% / 28% | PASS |
| $10k p≥0.85 5d | 105 | 33 | 100% | +2.7% | +0.015 | 100% | 18% | 3%/3% | 69.5% | 73 / +2.3% / +0.011 / 100% / 23% | PASS |
| $10k fav 0.55-0.85 0-1d | 20 | 11 | 75% | +1.9% | −0.290 | 59% | 312% | −10%/37% | 45.0% | 9 / – / – / – | FAIL |
| $10k fav 0.55-0.85 5d | 25 | 14 | 76% | +3.2% | −0.276 | 59% | 151% | −3%/20% | 52.0% | 13 / – / – / – | FAIL |
| $10k p<0.85 w 0-1d | 33 | 13 | 67% | +21.2% | +0.028 | 97% | 33% | 5%/82% | 36.4% | 12 / – / – / – | FAIL |
| $10k p<0.85 w 5d | 39 | 15 | 67% | +16.4% | +0.007 | 96% | 36% | 4%/59% | 41.0% | 16 / – / – / – | FAIL |
| anchor $10k+ any | 331 | 52 | 94% | +4.8% | +0.022 | 100% | 20% | 4%/6% | – | 226 / +5.9% / +0.019 / 99% / 30% | PASS |

OOS-sided caution, and why PASS here means nothing for transport: at ≥0.85 the
OOS winRate is **literally 100.0%** (43 events, not one burst on a heavy favorite
lost) — the p5/P(>0) values are print-noise of a degenerate all-win sample, and
the rets are +2.4–3.2%. The 60-slug pull simply had no losing heavy favorite in
its event fleet; the HOLD fleet (140+ events) immediately shows the 98–99% win
reality and ±0.00 p5. The $10k OOS PASS rows also carry landed300 66–77% (12–16
of 224–301 delay-realistic entries dropped) — the OOS book was thin at burst
time, so the OOS "passes" are the least delay-realistically graded cells in the
study. Per the pre-registration (PASS must hold on BOTH dirs), the OOS ≥0.85
passes are not transportable.

### INS (reference only): the price axis is INVERTED in-sample

| cell | n | evts | winRate | ret | p5 | P(>0) | dr p5 | verdict |
|---|---|---|---|---|---|---|---|---|
| $5k p≥0.85 5d | 2,046 | 44 | 93% | −2.7% | −0.056 | 9% | −0.066 | FAIL |
| $10k p≥0.85 5d | 1,174 | 38 | 93% | −3.7% | −0.059 | 5% | −0.066 | FAIL |
| $5k fav 0.55-0.85 5d | 828 | 32 | 62% | −12.8% | −0.216 | 1% | −0.217 | FAIL |
| $10k fav 0.55-0.85 5d | 377 | 26 | 59% | −18.6% | −0.262 | 0% | −0.255 | FAIL |
| $10k 0.15-0.35 5d | 102 | 17 | 48% | +113.1% | +0.416 | 99% | +0.393 | PASS |
| $10k p<0.15 5d | 54 | 9 | 33% | +325.5% | +1.064 | 99% | +1.242 | PASS |
| $5k p<0.85 w 5d | 1,523 | 37 | 52% | +28.7% | +0.017 | 96% | +0.043 | PASS |

Every favorite-side cell LOSES in-sample (−3% to −26%, P(>0) 0.5–9%) — the exact
dir where the longshot family's edge lived. The pre-registered wide-band note:
`p<0.85 w` passes INS (+28–40%) — it would look "positive" until you notice the
sign ownership is the longshot rungs and the favorite rungs inside it are pooled
losses; the wide band is a composition artifact, not a cell.

### Monotonicity control (task item 3): failure IS monotone in price — the price axis is real

$10k, ≤5d, ≤3 mkts, retReal (independent re-eval, rng 700; bootstrap drift vs the
table cells above is ≤0.02 on p5 wherever n is large, but grows to ~0.06 on the
9-event INS p<0.15 cell — drift is an n-sized effect, the ordering is not):

| rung | INS p5 (ret) | OOS p5 (ret) | HOLD p5 (ret) | HOLD winRate |
|---|---|---|---|---|
| p<0.15 | +1.003 (+325.5%) | – (—, n=0 thin) | **−1.000** (−100.0%) | 0.0% |
| 0.15-0.35 | +0.430 (+113.1%) | – (thin) | −0.822 (−62.9%) | 10.9% |
| 0.35-0.55 | −0.010 (+24.9%) | – (thin) | −0.551 (−32.9%) | 30.7% |
| 0.55-0.70 | −0.394 (−22.4%) | – (thin) | −0.144 (+9.0%) | 68.2% |
| 0.70-0.85 | −0.302 (−16.5%) | – (thin) | −0.090 (+7.9%) | 83.6% |
| p≥0.85 | −0.060 (−3.7%) | +0.015 (+2.7%) | **+0.005** (+2.1%) | 99.3% |

On HOLD the ladder runs −1.000 → −0.822 → −0.551 → −0.144 → −0.090 → +0.005:
monotone in price with zero exceptions, both directions (the ≤0.15 deep-lottery
complement — the task's opposite-extreme control — is a TOTAL loss: 36 large
bursts, 11 events, winRate 0%, every delay-realized entry resolves −100%).
"Price" is confirmed as the axis that separates winners from losers in the
burst-copy family. But monotonicity that terminates AT ZERO at the favorite end
is emptiness, not opportunity: the ladder's ceiling is the +0.005/−0.002 knife
edge, i.e. the whole surface maps to {p5 < 0} ∪ {p5 ≈ 0}. INS inverts the SAME
ordering (ladder declining toward the favorite end, deep end +1.00) — the sign
of the family is not invariant across fetch waves, which independently kills any
notion of a stable price-band rule.

### Verdict summary (pre-registered gates, per dir per convention)

- **HOLD (deciding): 32/32 gradeable cells FAIL, 1 INCON-THIN, 0 PASS.** No
  favorite-copy cell — at $5k or $10k, at [0.55,0.70), [0.70,0.85), [0.55,0.85),
  ≤0.85-wide, p≥0.85, or any sub-0.55 rung, at 0–1d or ≤5d — passes.
- **OOS: 5/16 gradeable PASS — all five are ≥0.85 favorites or the anchor,
  riding a 100%-win degenerate fleet that HOLD immediately reprices to ~99%/b≈0.**
  Transportable candidates (PASS on both OOS and HOLD): **zero**.
- **INS: 9 PASS — all on the longshot/deep side or wide-band compositions;
  zero favorite-side passes.** The hypothesis's home universe actively rejects it.
- **Age:** 0–1d vs ≤5d is immaterial for favorites (HOLD $10k ≥0.85: p5 +0.005
  both) — including the day-0/1 band, as pre-registered, changed nothing;
  there is no age slice where favorites become gradeably positive.

## Money-relevant takeaway

**The burst-copy family is OOS-dead at every point of the (burst-size × price)
surface, including the favorite side its own control cell pointed at.** The
control cell (all $10k+ bursts, +1.1%, 90.9% win) was an average over a
price-monotone ladder whose winners live at the extreme favorite end — but
followed to its own end, the favorite edge is +1–2% per burst at 98–100% win,
and it dies at the two pre-registered realistic-gate steps a copier cannot
skip: paying the NEXT print + 50bps instead of the burst average (p5 +0.005 →
−0.002, uniformly negative dr p5 on every ≥0.70 HOLD cell) and surviving
top-event concentration (dr share 68–80% in the largest cells). There is no
transportable film of the surface: price is monotone and real as an axis, but
its ceiling is ~breakeven for anyone copying at market after the burst starts.
Joining the §9.2 longshot verdict, both directions of the family now FAIL on
the fresh 200-slug holdout; the live paper-gate sample remains the only
deciding evidence stream for the shipped cells printing under it. No re-tunes,
no conditional passes: cells frozen.
