# Post-burst continuation, short-horizon marks: does the control-cell drift survive the tape today?

**Pre-registration (written BEFORE any grading run; the grid, the horizons, the
gates and the conventions below are all fixed before the first evaluate()
call). Results and mechanical verdicts are appended at the end in a clearly
separated section.**
Script: `scripts/research/burstContinuation.py`. Log: `logs/burstContinuation.log`.
Machinery: import, never fork — `entrySweep.loadEntries` (per-dir fingerprinted
caches), `entrySweep.filterCell` / `entrySweep.evaluate` (1000-draw per-event
pnl/cap bootstrap, 2025-06-01 half split, MIN_CELL), and
`oosTransport.addLanded` / `delayRealReturn` / `SLIP` for the delay-realistic
entry pricing. Nothing re-implemented except the exit-tape marking, which is
R2's (`research/horizonExits.py`) recipe verbatim plus two added horizons.
Nothing tuned against results.

## Position in the program (why this run exists)

- **R4** (`research/favoriteBursts.md`): copying bursts AT ANY PRICE with
  hold-to-resolution is ~breakeven OOS — the price-surface ceiling ≈ 0. The
  copy side of the burst family is dead.
- **R2** (`research/horizonExits.md`): on the delay-realistic graded frame the
  ≤0.35 longshot line's OOS marks are already noise-like at T+1h (p5
  −0.015…−0.033) and firmly negative by T+1d (p5 −0.10…−0.21).
- Neither graded the SHORT horizon of the **favorite/mid** bands: hold-to-
  resolution absorbs the mean-reversion structure timing, and R2's horizon
  marks covered the longshot line only.
- **The open claim under test (ideaGenAlpha family #1, "post-burst
  continuation, direct taker"):** LARGE bursts on already-traded books —
  FAVORITE/MID price bands — should drift **UP over the first minutes→hours**
  (the control-cell pattern, research/status.md §9.2: all $10k+ bursts at any
  price/age, ret +1.1%, winRate 90.9%, n=16,896 on the fresh holdout), BEFORE
  the mean reversion that killed the longshot copy line arrives. And that
  drift should stand **on BOTH OOS dirs separately**.

## Hypothesis under test (pre-registered)

**H1:** for burst entries in the favorite/mid price bands, the delay-realistic
short-horizon marks (T+1h → T+7d) drift UP: per-event bootstrap p5 > 0,
entry-weighted mean > 0, and the sign survives the era split and the
composed gate. If H1 holds on both OOS dirs, the output is one live-lane
paper gate expressed as an exact **(burstUsd, price band, horizon)** triple.
If every band fails everywhere, the family-1 recommendation dies with no
exceptions; if only the mean-side is positive with p5 ≤ 0 everywhere, the
honest verdict is "fat-tail artifact / no tradeable floor" and the run
records which bands (if any) the tape drifts UP on as description, not as a
candidate.

## Data dirs (graded separately, never mixed)

- **INS** `[data, data/universe]` — reference only (where the pattern was
  measured). Cache `entries_v2_df8efad228.parquet` (fingerprint match,
  reused).
- **OOS** `[data/oos]` — 60-slug pull, era §9.1/9.2. Cache
  `entries_v2_3670562787.parquet` (fingerprint match, reused).
- **HOLD** `[data/oosExpansion]` — 200-slug fresh holdout, the deciding dir.
  Cache `entries_v2_8fdc67aec9.parquet` (fingerprint match, reused — this is
  R2's pinned-order rebuild, 3,599,688 entries).

Universe per dir: the military/strike event slugs (entrySweep's MILITARY
tuple via its cache build), burst entries = per (account, marketId, outcome)
10-minute BUY windows, held only to resolved entries (the cache's ret-null
filter). **No age and no marketsSoFar gate** — this test re-states the
control cell (bursts at any account age), NOT the falsified fresh-account
copy shape. Category scope stays military (the dirs are military-roster
pulls; non-military expansion is out of scope here).

## Pre-registered grid (the stakes)

- **Burst stakes:** `usd ≥ 10k`, `usd ≥ 25k`, `usd ≥ 50k` (burst-window USD,
  `usd` column; no upper bound).
- **Price bands** on the burst entry `price` (the cached tape-joined opening
  print of the burst window — the same column every sibling cut its price
  bands on): [0.15,0.35) / [0.35,0.55) / [0.55,0.85) / [0.85,0.98), half-open
  lower/upper. 12 cells.
- **Anchor (soundness, not a candidate):** `usd ≥ 10k`, ANY price — must
  reproduce the shipped control cell before any table is trusted:
  HOLD n=16,896 / retReal +1.1% / winRate 90.9% (status §9.2, R4's
  reproduction); OOS n=331 / +4.8% / 94%; INS n=17,761 / +0.6% / 81.8%.
  ±tie-noise deltas (documented below) are reported per dir.

## Pre-registered horizons (fixed BEFORE grading; R2's exact mark recipe)

Per cell × dir × horizon, two conventions:

1. **native (whole-burst, cache convention):** hold to resolution, retReal =
   cache column (next-print fill price with trigger-price fallback; winners
   1/price − 1) — the shipped R1/R4 convention.
2. **delay-realistic (dropped-if-no-land):** a real copy enters on the FIRST
   BUY print after the trigger within the 300s window at that print + 50bps
   slippage; entries that never land are DROPPED. `landed300%` reported per
   cell. At resolution this is `oosTransport.delayRealReturn`'s retReal50.

**Horizon marks** (on the delay-realistic graded frame only — R2's recipe):
mark the position at the first available print (ANY side, BUY+SELL collapsed
to one price per (marketId, outcome, ts) by a **fully pinned**
`(marketId, outcome, ts, price)` sort + unique keep-last) at or after
`entryTs + H`, paying 50bps sell-side slippage; fallback = last print BEFORE
the target; fallback-of-fallback = the paid entry print nextPrice (market
went silent — mark carries, entry slippage applies). **Resolution
precedence:** `resolvedAt ≤ target` → mark is exactly 1.0 (won) / 0.0
(lost), no slippage. `retH = exitValue/cost − 1`, cost = nextPrice × 1.005.
Horizons (fixed a priori): **T+1h / T+6h / T+1d / T+3d / T+7d** (R2's
T+1h/T+1d/T+7d plus T+6h and T+3d to bracket the reversal timing).

Marks are computed only on the `usd ≥ 10k` population (the largest grid
stake) — marks are per-row arithmetic, so restricting the marked frame
before cell filtering changes nothing per graded row and keeps the asof
joins cheap.

## Pre-registered gates (mechanical verdicts, nothing tuned)

Identical to R2/R4's composed gate, applied per cell × dir × horizon:

- **MIN_CELL = 20** graded entries AND ≥ 20 distinct events → below that:
  **INCONCLUSIVE-THIN** (no verdict, no bootstrap consumed).
- **PASS iff** n ≥ 20 AND events ≥ 20 AND bootstrap p5 > 0 AND P(>0) ≥ 85%
  AND top-event pnl share < 60% (share of a non-positive pool → treated as
  failing; reported as "–", same convention as oosTransport's evalCell).
- **else FAIL.** A horizon mark's PASS rides on that mark's return column
  aliased through `entrySweep.evaluate` (seeded 1000-event bootstrap, ONE
  `random.Random(7)` per dir, cells × horizons traversed in fixed
  usd→band→horizon order → deterministic digits).
- **Composed live-lane PASS (candidate line):** a cell is a live-lane
  candidate only if it PASSES on BOTH OOS dirs (oos AND oosExpansion)
  **separately**, at the same (usd, band, horizon). INS is reference-only.
- **Delay-realistic floor:** the candidate's delay-realistic resolution
  grading must also satisfy p5 > 0 (entry cost reality cannot be faked by
  the mark): "delay-realistic > 0" is part of the composed candidate claim.

## Tie-nondeterminism handling (carried from R2's finding)

R2 showed the shipped tape's same-second BUY-print consolidation resolves
ties in unspecified order (cell membership can wobble ±entries between
runs). This run:

- pins the exit tape fully (sort includes `price` — R2's recipe verbatim);
- sorts the per-event status:
</think>Two edits crossed in transit — let me rewrite the doc completely so the file matches spec.<tool_call>write<arg_key>content</arg_key><arg_value># Post-burst continuation, short-horizon marks: does the control-cell drift survive the tape today?

**Pre-registration (written BEFORE any grading run; the grid, the horizons, the
gates and the conventions below are all fixed before the first evaluate()
call). Results and mechanical verdicts are appended at the end in a clearly
separated section.**
Script: `scripts/research/burstContinuation.py`. Log: `logs/burstContinuation.log`.
Machinery: import, never fork — `entrySweep.loadEntries` (per-dir fingerprinted
caches), `entrySweep.filterCell` / `entrySweep.evaluate` (1000-draw per-event
pnl/cap bootstrap, 2025-06-01 half split, MIN_CELL), and
`oosTransport.addLanded` / `delayRealReturn` / `SLIP` for the delay-realistic
entry pricing. Nothing re-implemented except the exit-tape marking, which is
R2's (`research/horizonExits.py`) recipe verbatim plus two added horizons.
Nothing tuned against results.

## Position in the program (why this run exists)

- **R4** (`research/favoriteBursts.md`): copying bursts AT ANY PRICE with
  hold-to-resolution is ~breakeven OOS — the price-surface ceiling ≈ 0. The
  copy side of the burst family is dead.
- **R2** (`research/horizonExits.md`): on the delay-realistic graded frame the
  ≤0.35 longshot line's OOS marks are already noise-like at T+1h (p5
  −0.015…−0.033) and firmly negative by T+1d (p5 −0.10…−0.21).
- Neither graded the SHORT horizon of the **favorite/mid** bands: hold-to-
  resolution absorbs the mean-reversion structure timing, and R2's horizon
  marks covered the longshot line only.
- **The open claim under test (ideaGenAlpha family #1, "post-burst
  continuation, direct taker"):** LARGE bursts on already-traded books —
  FAVORITE/MID price bands — should drift **UP over the first minutes→hours**
  (the control-cell pattern, status §9.2: all $10k+ bursts at any price/age,
  ret +1.1%, winRate 90.9%, n=16,896 on the fresh holdout), BEFORE the mean
  reversion that killed the longshot copy line arrives. And that drift should
  stand **on BOTH OOS dirs separately**.

## Hypothesis under test (pre-registered)

**H1:** for burst entries in the favorite/mid price bands, the delay-realistic
short-horizon marks (T+1h → T+7d) drift UP: per-event bootstrap p5 > 0,
entry-weighted mean > 0, and the sign survives the era split and the composed
gate. If H1 holds on both OOS dirs, the output is one live-lane paper gate
expressed as an exact **(burstUsd, price band, horizon)** triple. If every
band fails everywhere, the family-1 recommendation dies with no exceptions;
if only the mean-side is positive with p5 ≤ 0 everywhere, the honest verdict
is "fat-tail artifact / no tradeable floor" and the run records which bands
(if any) the tape drifts UP on as description, not as a candidate.

## Data dirs (graded separately, never mixed)

- **INS** `[data, data/universe]` — reference only (where the pattern was
  measured). Cache `entries_v2_df8efad228.parquet` (fingerprint match,
  reused).
- **OOS** `[data/oos]` — 60-slug pull, era §9.1/9.2. Cache
  `entries_v2_3670562787.parquet` (fingerprint match, reused).
- **HOLD** `[data/oosExpansion]` — 200-slug fresh holdout, the deciding dir.
  Cache `entries_v2_8fdc67aec9.parquet` (fingerprint match, reused — this is
  R2's pinned-order rebuild, 3,599,688 entries).

Universe per dir: the military/strike event slugs (entrySweep's MILITARY
tuple via its cache build), burst entries = per (account, marketId, outcome)
10-minute BUY windows, held only to resolved entries (the cache's ret-null
filter). **No age and no marketsSoFar gate** — this test re-states the
control cell (bursts at any account age), NOT the falsified fresh-account
copy shape. Category scope stays military (the dirs are military-roster
pulls; non-military expansion is out of scope here).

## Pre-registered grid (the stakes)

- **Burst stakes:** `usd ≥ 10k`, `usd ≥ 25k`, `usd ≥ 50k` (burst-window USD,
  `usd` column; no upper bound).
- **Price bands** on the burst entry `price` (the cached tape-joined opening
  print of the burst window — the same column every sibling run cut its
  price bands on): [0.15,0.35) / [0.35,0.55) / [0.55,0.85) / [0.85,0.98),
  half-open lower/upper. 12 cells.
- **Anchor (soundness, not a candidate):** `usd ≥ 10k`, ANY price — must
  reproduce the shipped control cell before any table is trusted: HOLD
  n=16,896 / retReal +1.1% / winRate 90.9% (status §9.2, R4's
  reproduction); OOS n=331 / +4.8% / 94%; INS n=17,761 / +0.6% / 81.8%.
  ±tie-noise deltas are reported per dir.

## Pre-registered horizons (fixed BEFORE grading; R2's exact mark recipe)

Per cell × dir × horizon, two conventions:

1. **native (whole-burst, cache convention):** hold to resolution, retReal =
   cache column (next-print fill price with trigger-price fallback; winners
   1/price − 1) — the shipped R1/R4 convention.
2. **delay-realistic (dropped-if-no-land):** a real copy enters on the FIRST
   BUY print after the trigger within the 300s window at that print + 50bps
   slippage; entries that never land are DROPPED. `landed300%` reported per
   cell. At resolution this is `oosTransport.delayRealReturn`'s retReal50.

**Horizon marks** (on the delay-realistic graded frame only — R2's recipe):
mark the position at the first available print (ANY side, BUY+SELL collapsed
to one price per (marketId, outcome, ts) by a **fully pinned**
`(marketId, outcome, ts, price)` sort + unique keep-last) at or after
`entryTs + H`, paying 50bps sell-side slippage; fallback = last print BEFORE
the target; fallback-of-fallback = the paid entry print nextPrice (market
went silent — mark carries, entry slippage applies). **Resolution
precedence:** `resolvedAt ≤ target` → mark is exactly 1.0 (won) / 0.0
(lost), no slippage. `retH = exitValue/cost − 1`, cost = nextPrice × 1.005.
Horizons (fixed a priori): **T+1h / T+6h / T+1d / T+3d / T+7d** (R2's
T+1h/T+1d/T+7d plus T+6h and T+3d to bracket the reversal timing).

Marks are computed only on the `usd ≥ 10k` population (the largest grid
stake) — marks are per-row arithmetic, so restricting the marked frame
before cell filtering changes nothing per graded row and keeps the asof
joins cheap.

## Pre-registered gates (mechanical verdicts, nothing tuned)

Identical to R2/R4's composed gate, applied per cell × dir × horizon:

- **MIN_CELL = 20** graded entries AND ≥ 20 distinct events → below that:
  **INCONCLUSIVE-THIN** (no verdict, no bootstrap consumed).
- **PASS iff** n ≥ 20 AND events ≥ 20 AND bootstrap p5 > 0 AND P(>0) ≥ 85%
  AND top-event pnl share < 60% (share of a non-positive pool → treated as
  failing; reported as "–", same convention as oosTransport's evalCell).
- **else FAIL.** A horizon mark's PASS rides on that mark's return column
  aliased through `entrySweep.evaluate` (seeded 1000-event bootstrap, ONE
  `random.Random(7)` per dir, cells × horizons traversed in fixed
  usd→band→horizon order → deterministic digits).
- **Composed live-lane PASS (candidate line):** a cell is a live-lane
  candidate only if it PASSES on BOTH OOS dirs (oos AND oosExpansion)
  **separately**, at the same (usd, band, horizon). INS is reference-only.
- **Delay-realistic floor:** the candidate's delay-realistic resolution
  grading must also satisfy p5 > 0 (entry cost reality cannot be faked by a
  mark): "delay-realistic > 0" is part of the composed candidate claim.

## Tie-nondeterminism handling (carried from R2's finding)

R2 showed the shipped tape's same-second BUY-print consolidation resolves
ties in unspecified order (cell membership can wobble ±entries between
runs). This run:

- pins the exit tape fully (sort includes `price`, R2's recipe verbatim);
- pins the per-event table before the RNG consumes it (entrySweep.evaluate
  already sorts on eventSlug);
- reuses `oosTransport.addLanded` / `delayRealReturn` exactly as shipped
  (their tape tie handling stays the shipped convention);
- reports the anchor-count deltas vs the prior runs so any ±entries wobble
  is visible next to the tables.

## Results (appended after the run)

Run 2026-10-17, one pass, `logs/burstContinuation.log` (~14s total). All three
dirs consumed their fingerprint-matching caches — **no rebuild of anything**
(HOLD graded from R2's pinned `entries_v2_8fdc67aec9.parquet`, 3,599,688
entries). Mark machinery was verified on-ground before the tables were read:
five sample rows (mid-band, holdout) × T+1h and T+1d recomputed by hand from
the exit tape — every branch (after-print, resolution-precedence, carry)
matches the machine marks to 1e-9. `uv run pytest`: 150 passed (the
0/3/0/45-style suite; the 3 failing tests are the sibling paperLanes run's
in-progress `tests/test_paperLanes.py` — its own uncommitted
`scripts/liveWatcher.py` NameError / fixture path / KeyError, not this
run's files). `ruff check` clean on `scripts/research/burstContinuation.py`.

### Count truing vs the shipped control cell (gate: reproduce before trusting)

| dir | anchor n (usd≥$10k, ANY price/age) | prior | Δn | retReal | winRate | dr n (R4's) |
|---|---:|---:|---:|---:|---:|---:|
| in-sample | 17,761 | 17,761 | **+0** | +0.6% | 81.8% | 16,747 (=R4) |
| oos | 331 | 331 | **+0** | +4.8% | 94.0% | 226 (=R4) |
| oosExpansion | 16,896 | 16,896 | **+0** | +1.1% | 90.9% | 14,987 (=R4) |

Zero wobble on every anchor: the ±1 tie-noise R2 documented did not appear
(the pinned HOLD cache + pinned exit tapes removed it). The control cell
reproduces to the digit, so the tables below stand on the same tape.

### Verdict matrices (pre-registered gates, nothing tuned)

Per dir. Format per cell × horizon: `retMean% / p5 / topShare / verdict`;
**P** = PASS, F = FAIL, `Tn` = INCONCLUSIVE-THIN with n graded entries (thin
rows carry no gates). `res(nat)` = native whole-burst resolution grading
(R1/R4 convention); `res` = delay-realistic resolution; every other column
is a horizon mark on the delay-realistic frame (R2's recipe). landed300%:
91.8–100.0% on every HOLD/INS cell (per-cell values in the log); OOS
(60-slug) 0–72.5% — the old thin-book regime, pre-stated.

**in-sample `[data, data/universe]` (reference): 9 PASS / 40 FAIL / 35 THIN**

| cell | res(nat) | res | t1h | t6h | t1d | t3d | t7d |
|---|---|---|---|---|---|---|---|
| ≥$10k [0.15,0.35) | +98.8/0.228/0.588/**P** | +99.0/0.246/0.592/**P** | +6.3/0.041/0.277/**P** | +11.3/0.038/0.332/**P** | +23.3/0.064/0.557/**P** | +27.4/0.089/0.469/**P** | +51.0/0.106/0.617/F |
| ≥$10k [0.35,0.55) | +19.2/0.097/0.241/**P** | +19.0/0.096/0.249/**P** | +3.5/0.004/0.502/**P** | +7.7/−0.001/0.559/F | +8.0/0.000/0.582/F | +6.9/−0.023/0.678/F | +6.9/−0.046/0.690/F |
| ≥$10k [0.55,0.85) | −20.6/−0.343/–/F | −21.1/−0.343/–/F | −0.9/−0.020/–/F | −2.4/−0.041/–/F | −5.2/−0.104/–/F | −6.1/−0.110/–/F | −10.2/−0.179/–/F |
| ≥$10k [0.85,0.98) | −9.0/−0.159/–/F | −9.6/−0.171/–/F | −1.1/−0.015/–/F | −1.5/−0.027/–/F | −2.8/−0.057/–/F | −5.1/−0.101/–/F | −8.0/−0.156/–/F |
| ≥$25k [0.15,0.35) | T112 … T108 (all seven) | | | | | | |
| ≥$25k [0.35,0.55) | T150 … T147 (all seven) | | | | | | |
| ≥$25k [0.55,0.85) | −14.7/−0.334/–/F | −15.2/−0.341/–/F | +1.3/−0.004/0.623/F | 0.0/−0.029/21.563/F | −1.6/−0.088/–/F | −0.8/−0.083/–/F | −3.8/−0.138/–/F |
| ≥$25k [0.85,0.98) | −8.9/−0.135/–/F | −9.3/−0.140/–/F | −1.2/−0.016/–/F | −1.2/−0.022/–/F | −2.5/−0.048/–/F | −5.3/−0.093/–/F | −8.1/−0.133/–/F |
| ≥$50k [0.15,0.35) | T30 (all seven) | | | | | | |
| ≥$50k [0.35,0.55) | T52 … T50 (all seven) | | | | | | |
| ≥$50k [0.55,0.85) | T275 … T267 (all seven) | | | | | | |
| ≥$50k [0.85,0.98) | −10.1/−0.147/–/F | −10.4/−0.152/–/F | −1.0/−0.017/–/F | −0.9/−0.021/–/F | −2.3/−0.047/–/F | −5.2/−0.087/–/F | −8.5/−0.131/–/F |

All nine INS passes are longshot-band cells ([0.35,0.55) and below) — the
known in-sample price-axis inversion (R4), plus its t1h echoes. Every ≥0.55
cell in the in-sample home universe is negative at every horizon.

**oos `[data/oos]` (60-slug pull): 6 PASS / 2 FAIL / 76 THIN** — the pull is
too thin for this grid (76/84 rows frozen below MIN_CELL; the gradeable
population is the ≥$10k rows):

| cell | res(nat) | res | t1h | t6h | t1d | t3d | t7d |
|---|---|---|---|---|---|---|---|
| ≥$10k [0.15,0.35) | T8 | T3 | T3 | T3 | T3 | T3 | T3 |
| ≥$10k [0.35,0.55) | T14 | T8 | T8 | T8 | T8 | T8 | T8 |
| ≥$10k [0.55,0.85) | +12.9/−0.076/0.341/F | T26 | T26 | T26 | T26 | T26 | T26 |
| ≥$10k [0.85,0.98) | +6.0/0.037/0.148/**P** | +6.4/0.053/0.097/**P** | −1.3/−0.032/–/F | +1.9/0.005/0.321/**P** | +3.2/0.020/0.196/**P** | +4.1/0.030/0.150/**P** | +4.6/0.032/0.135/**P** |
| everything else | T0–T17 below MIN_CELL (all columns) | | | | | | |

The one OOS evaluable band, [0.85,0.98), is the same degenerate 100%-win
heavy-favorite fleet R4 flagged (dr res 66 entries / 32 events at landed
72.5%, winRate a flat 100.0%) — it passes res/t6h/t1d/t3d/t7d (fails t1h)
and tells a 2–4.6%-per-burst slow-drift story that the deciding dir
immediately reprices (below).

**oosExpansion `[data/oosExpansion]` (deciding dir): 9 PASS / 55 FAIL / 20 THIN**

| cell | res(nat) | res | t1h | t6h | t1d | t3d | t7d |
|---|---|---|---|---|---|---|---|
| ≥$10k [0.15,0.35) | −29.6/−0.567/–/F | −35.0/−0.629/–/F | +10.1/0.041/0.261/**P** | +9.0/0.008/0.349/**P** | +11.7/0.011/0.278/**P** | −1.6/−0.142/–/F | −15.2/−0.336/–/F |
| ≥$10k [0.35,0.55) | −6.9/−0.250/–/F | −5.5/−0.236/–/F | +0.7/−0.025/1.817/F | −2.8/−0.077/–/F | +5.4/0.006/0.350/**P** | +5.2/−0.037/0.808/F | −1.9/−0.092/–/F |
| ≥$10k [0.55,0.85) | +13.7/0.003/0.428/**P** | +14.3/0.010/0.431/**P** | −0.1/−0.008/–/F | **+0.2/−0.008/1.696/F** | −0.4/−0.035/–/F | +2.9/−0.024/0.770/F | **+8.7/0.020/0.486/P** |
| ≥$10k [0.85,0.98) | +0.7/−0.038/0.842/F | +0.1/−0.042/8.604/F | −1.4/−0.019/–/F | −1.6/−0.026/–/F | −1.7/−0.037/–/F | −1.2/−0.037/–/F | −1.2/−0.042/–/F |
| ≥$25k [0.15,0.35) | −48.9/−0.743/–/F | T72 | T72 | T72 | T72 | T72 | T72 |
| ≥$25k [0.35,0.55) | −5.1/−0.343/–/F | −1.3/−0.317/–/F | +1.7/−0.023/0.802/F | −1.5/−0.075/–/F | +8.0/−0.003/0.335/F | +5.4/−0.041/0.477/F | +1.9/−0.120/1.958/F |
| ≥$25k [0.55,0.85) | +12.4/−0.038/0.502/F | +14.1/−0.014/0.469/F | +0.1/−0.010/9.898/F | +1.2/−0.002/0.625/F | −0.2/−0.038/–/F | +3.0/−0.033/0.752/F | **+10.0/0.023/0.480/P** |
| ≥$25k [0.85,0.98) | −0.6/−0.067/–/F | −1.4/−0.072/–/F | −1.5/−0.021/–/F | −1.8/−0.032/–/F | −2.0/−0.042/–/F | −1.8/−0.048/–/F | −1.7/−0.049/–/F |
| ≥$50k [0.15,0.35) | T15 | T14 | T14 | T14 | T14 | T14 | T14 |
| ≥$50k [0.35,0.55) | T25 | T23 | T23 | T23 | T23 | T23 | T23 |
| ≥$50k [0.55,0.85) | +11.8/−0.070/0.523/F | +14.2/−0.018/0.481/F | 0.0/−0.012/45.871/F | +1.4/−0.004/0.512/F | +0.6/−0.041/1.172/F | +1.4/−0.068/1.625/F | **+10.7/0.015/0.493/P** |
| ≥$50k [0.85,0.98) | +0.2/−0.060/3.233/F | −0.6/−0.067/–/F | −0.8/−0.011/–/F | −0.7/−0.013/–/F | −0.9/−0.026/–/F | −0.9/−0.035/–/F | −1.0/−0.049/–/F |

### (b) Where the drift medians flip sign (entry-median ret, ×100, delay-real)

Full per-dir/era medians are printed in the log ("drift medians by dir/era";
medAll · h1-half · h2-half). The sign story:

- **T+1h is the slip floor everywhere that matters.** On the deciding dir
  every graded band's T+1h median is −0.995 (the exact round-trip −0.9950% =
  mark ≈ paid print; no drift), on both halves (h1/h2 identical). Same on INS
  for [0.55,0.98). The hypothesis's minutes→hours liftoff **does not exist on
  the fresh tape** — and INS's own longshot t1h "passes" ride medAll −0.995
  too (their p5>0 is single-event fat tails, win 43–48%).
- **[0.55,0.85) (mid band) flips positive with horizon, monotone**: HOLD
  medians −0.995 (t1h) → −0.93 (t6h) → +0.40 (t1d) → +5.41 (t3d) → +16.37
  (t7d); the h2-half (post-split era) leads, h1-half follows the same
  trajectory but ~6h–1d later. INS median speed to the same shape (t1d +1.39,
  t3d +5.79, t7d +10.89) BUT its event-floor stays negative (p5 −0.104/−0.179
  — the in-sample mid-band home for the known nesting). OOS (26 entries,
  14 events, landed 60.5%) prints mid band positive from t1d (+14.0 median)
  — THIN, so descriptive only.
- **[0.15,0.35)/[0.35,0.55) (longshot bands)**: medians negative at every
  graded HOLD horizon/era except knife-half-positive oddities (t1h h1 +0.69)
  whose res side is −35%/−5.5% mean, p5 −0.63/−0.24 — the falsified longshot
  copy family, re-confirmed at every horizon; the only positive-median
  longshot cells are the INS h1-era (pre-2025-06) cells R4 already
  tombstoned.
- **[0.85,0.98) (heavy favorites)**: res medians positive ~+3.5–4.7 on all
  three dirs and both halves (the mechanical 98–99% win at +1–2%), short
  marks at the slip floor, t1d–t7d medians +0.1→+2.9 — a real but tiny
  post-burst-affirmation drift that P(>0) 0.535 (event-weighted, 8.604
  topShare) cannot support as a gate-passing line.

### (c) The composed gate census

Pre-registered composed rule: **PASS on BOTH OOS dirs separately**, same
(usd, band, horizon), plus the delay-realistic resolution floor (dr-res
p5 > 0 both dirs).

- Single-dir PASSing cells on the deciding dir: ≥$10k/$25k/$50k [0.55,0.85)
  at **res** (10k only: +0.010) and at **T+7d** (+0.020/+0.023/+0.015, win
  77.6–81.4%, topShare 0.48–0.49); ≥$10k [0.15,0.35) at t1h/t6h/t1d and
  ≥$10k [0.35,0.55) at t1d — every one of these longshot knife-passes has
  medAll −0.995, win 40–50%, and dr-res p5 −0.63/−0.24 → killed by the
  delay-realistic floor.
- On OOS the only PASSing cells are ≥$10k [0.85,0.98) (res/t6h/t1d/t3d/t7d)
  — a 100%-win 32-event fleet that HOLD kills (res P(>0) 0.535, topShare
  8.6).
- **Live-lane candidates after composition: none.** The mid-band [0.55,0.85)
  T+7d (and res) passes exist ONLY on the deciding dir: OOS cannot grade it
  (26 entries / 14 events landed in [0.55,0.85), landed300 60.5% — the
  60-slug pull grounds it), so the both-dirs requirement fails
  INCON-THIN, not by contradiction.

### (d) BOTTOM LINE

**R11's family-1 recommendation does NOT stand as a live-lane candidate under
the pre-registered gates: none — no (burstUsd, price band, horizon) triple
passes both OOS dirs.** The claim as stated — favorite/mid band bursts
drift UP over the first minutes→hours — is refuted on the deciding tape:
at T+1h/T+6h EVERY graded band's entry-median sits exactly at the
−0.995% round-trip slip floor (no drift beyond costs), 11/12 graded HOLD
cells p5 < 0, and the two t1h/t6h knife-passes it does print are the
falsified longshot bands' fat-tail artifacts that lose −35%/−5.5% at
resolution.

Where the tape DOES drift up (description, not a candidate line): the mid
band **[0.55,0.85) at T+1d → T+7d** — entry-median +0.4% → +5.4% → +16.4% on
the holdout, in BOTH halves, at all three burst stakes (p5 +0.015…+0.023,
P(>0) 0.97–0.99 at T+7d), with the heavy-favorite rung's smaller analog
(medians +1.2–2.9% by T+7d, P(>0) gate-killed). That is a days-scale
convergence tail on already-traded books, not the minutes-scale follow-through
the control cell's rate (+1.1% at 90.9% win over months-to-resolution)
suggested — and it cannot be composed into a live lane today because the
60-slug OOS pull grades it INCON-THIN (14 events after the 300s landing
window). The honest paper-lane record for whatever run picks this up next:
**paper-gate `≥$10k+ bursts in [0.55,0.85), T+7d mark exit** stands as the
only cell family alive anywhere on the surface (3/3 stakes PASS the deciding
dir), requiring an OOS pull with ≥20 gradeable mid-band burst events to clear
the both-dirs composition — until then family-1 remains short-horizon-dead,
long-horizon-inconclusive-sparse.
