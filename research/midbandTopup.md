# Mid-band top-up: a fresh military cohort big enough to grade R16's [0.55,0.85) cell

**Pre-registration (written BEFORE any fresh crawl/fill pull — cohort rule,
cell family, horizons, gates and the compose rule below are all fixed before
the first fresh fetch). Results are appended at the end in a clearly
separated section; the full verdict publishes whenever the fetch completes,
and the composition rule below makes the readout mechanical either way.**
Script: `scripts/research/midbandTopup.py`. Log: `logs/midbandTopup.log`.
Roster config: `configs/midbandTopup.yaml`. Detached fetch log:
`logs/fetchMidTopup.log`.

## Position in the program (why this run exists)

R16 (`research/burstContinuation.md`, round-2 burst-continuation grading)
found on the deciding dir `data/oosExpansion` (200-slug holdout):

- Mid-band **[0.55,0.85)** ≥$10k bursts hold a delay-realistic entry-median
  drift that rises with horizon: **−0.995% (T+1h slip floor) → +0.4% (T+1d)
  → +5.4% (T+3d) → +16.4% (T+7d)**, positive in BOTH halves of the
  2025-06-01 split; the graded gates **PASS at resolution (dr p5 +0.010) and
  at T+7d (p5 +0.015…+0.023, P(>0) 0.97–0.99) for ALL THREE stakes
  (≥$10k/≥$25k/≥$50k)** on that dir.
- But the run could not COMPOSE: the other OOS dir (`data/oos`, 60 slugs)
  grades the mid-band cell **INCON-THIN** (26 entries / 14 events after the
  300s landing window). The both-dirs composed rule therefore produced
  "no live-lane candidate", purely for thinness.

**This run exists to un-thin that second sibling.** It fetches a FRESH event
cohort whose mid-band family census reaches n ≥ 20 gradeable events, then
grades the exact pre-registered cell family on it, and composes with R16's
HOLD verdict per the rule below.

## Selection-honesty constraint (pre-registered before crawling)

The event cohort must be selected WITHOUT looking at burst fill content —
no fills/trades inspection of candidate events before the roster is frozen.
Only gamma event metadata is allowed at selection time: closed flag,
resolved status, volume, slug/tag/title. Consequence: the roster is a
declared-filter crawl, not a burst-population sample; any post-hoc claim
that the cohort was "burst-selected" is invalid, and the family census
(grades per event) is the correct weighting for this run.

## Cohort rule (CHOSEN: option a — military-extension)

**Pre-registered choice: option (a).** Crawl gamma `closed=true` events via
the keyset endpoint through military-adjacent tag slugs, keep the SHIPPED
15-keyword military tuple (`researchData.MILITARY` — `scripts/research/
researchData.py`) as the slug filter, **resolved only** (all markets closed
with a 0/1 winner, `thirdUniverseScan.eventResolved` recipe), volume
≥ **$100k**, excluding every slug present in `data/`, `data/universe`,
`data/oos`, `data/oosExpansion` and every existing roster config
(`oosFetch.yaml`, `oosExpansionFetch.yaml`, `militaryUniverse.yaml`,
`eventUniverse.yaml`), rendered into a roster of **~150 slugs** with a
**≤5-per-stem** diversity cap (stem rule pre-registered below), mirroring
the shipped `oosExpansionFetch.yaml` schema
(`splitDate: 2026-01-01`, `fetch.dataDir: data/midTopup`).

**Why (a), not (b):**

- R16's composition rule is a **two-sibling family test**: the fresh dir
  must be a gradeable SIBLING of the same military framing, or the compose
  gate loses its meaning. Option (b) (all-category volume crawl) grades the
  lane-3 whole-tape framing instead — a different claim — and would leave
  R16's family verdict unresolved forever.
- (a) reuses the CURRENT military keyword tuple and the same row of
  machinery (entrySweep keywords param), so the graded family is verbatim
  comparable to R16 and to §9's four runs.
- Gamma keyset pagination (the `after_cursor` param + id-regression guard)
  is already implemented and verified in `scripts/research/thirdUniverseScan.py`;
  this run imports those pieces instead of re-crawling agencies.

**Stem rule (deterministic, pre-registered):** `stem(slug)` = the slug with
the FIRST `-(by|on|before|in|through|during|next|this)-…` tail removed, then
trailing numeric qualifiers (`-\d+(-\d+)*$`) repeatedly stripped; per-stem
roster cap = 5 events. Over-clustering is acceptable (a tighter stem only
raises the cap), under-clustering is not corrected after the fact.

**Roster scope (measured before the fetch — the scale reality-check):**

- Population calibration (from EXISTING dirs, no fresh data): `data/oosExpansion`
  (200 slugs, $20k floor) carries **59** mid-band family events
  (≥$10k ╳ [0.55,0.85) ╳ fresh ≤5d ≤3 markets) at 0.30 events/slug; the
  graded family (all three stakes, ablation windows) peaks at 62 events.
  n ≥ 20 gradeable events needs on the order of **70–90 slugs** at the same
  event-yield rate; **~150 slugs with the stricter $100k liquid-volume flag
  gives margin** while staying inside the fetch budget.
- Fetch-time estimate (measured, not guessed): the oosExpansion fill pull
  wrote its full trades cache (10.66M fills over 962 markets) in a ~0.6h
  span; 200 slugs ≈ 11GB raw fills at the $20k floor ⇒ ~56MB/slug average.
  A 150-slug roster at a $100k floor ⇒ ~6–9M fills expected ≈ 2–5h
  background at the measured rate — comfortably inside the ~6–8h budget
  cap. (R6's trades-census walks — 147MB across 5×60 markets — completed in
  ~95s once censuses were cached, per `research/thirdUniverseScan.md`: the
  census is cheap; the fill pull is the whole cost.)
- **Fetch budget cap:** if the measured pull exceeds the estimate by ≥2×
  (log-observed row rate extrapolation at the halfway mark), the fetch is
  allowed to continue detached to completion — grading proceeds on the
  partial cache under the partial clause below. No scope expansion mid-run.

**Starved-cohort fallback (pre-registered):** if the ≥$100k pool yields
fewer than 80 fresh resolved military slugs, the roster drops to the
remaining largest-volume events at a **$30k** floor (same keyword/exclusion
rules, documented in the results appendix) rather than silently shrinking
the cohort.

## Graded cell family (verbatim from R16's pre-registration, narrow-cast)

- **Burst stakes:** `usd ≥ 10k` / `≥ 25k` / `≥ 50k` (burst-window USD, cache
  `usd` column; no upper bound).
- **Price band:** `[0.55, 0.85)`, half-open lower/upper, on the cached
  burst entry `price` (the tape-joined opening print of the burst window —
  the same column every sibling run used).
- **Base conditioning (fresh ≤5d ≤3 markets):** `ageDays ≤ 5` AND
  `marketsSoFar ≤ 3` (mini-gate mirrored from `oosTransport.filterCellMinAge`
  with minAge=0).
- **Age-band ablation (pre-registered, the R4-found age-gate flip):**
  `0–1d` (`ageDays ≤ 1`, markets ≤ 3) vs `2–5d` (`1 < ageDays ≤ 5`,
  markets ≤ 3) — graded beside the all-window row; the ablation never makes
  a live-lane claim on its own.
- **Machinery: import, never fork** — `entrySweep.loadEntries` (per-dir
  fingerprinted caches), `entrySweep.filterCell`, `entrySweep.evaluate`
  (1000-draw per-event pnl/cap bootstrap, 2025-06-01 half split, MIN_CELL
  floor, ONE `random.Random(7)` per dir, fixed usd→window cell order),
  `oosTransport.addLanded` / `delayRealReturn` / `SLIP` for the
  delay-realistic entry, `horizonExits.exitTape` / `markHorizon` / 
  `horizonEval` for the exit-tape/marking recipe. Nothing re-implemented,
  nothing tuned.

## Horizons (fixed BEFORE grading)

Same conventions as R16: **resolution** graded native (whole-burst cache
`retReal`) AND **delay-realistic** (`oosTransport.delayRealReturn`'s
`retReal50`: cost = next BUY print within 300s after the trigger + 50bps,
no-landed entries dropped, `landed300%` per cell) — plus **T+1d / T+3d /
T+7d marks** on the delay-realistic frame via the `horizonExits` recipe
(pinned exit tape, first print at/after target, 50bps sell-side slippage,
resolution precedence). R16's T+1h/T+6h marks are NOT re-graded: R16
already established they sit at the −0.995% slip floor for this cell
(zero drift exists at minutes), and this run exists for the days-scale
horizons; keeping them out removes two thin-event burners.

## Gates (mechanical verdicts, nothing tuned)

Per cell ╳ age window ╳ horizon on the fresh dir:

- **MIN_CELL = 20** graded entries AND ≥ 20 distinct events → below that:
  **INCONCLUSIVE-THIN** (no verdict, no bootstrap consumed).
- **PASS iff:** n ≥ 20 AND events ≥ 20 AND bootstrap **p5 > 0** AND
  **P(>0) ≥ 85%** AND **top-event pnl share < 60%**.
- **else FAIL** (true if a gate is falsified, THIN if n/events < 20).
- Each horizon's PASS rides on that horizon's return column aliased through
  `entrySweep.evaluate` verbatim (same seeding/order as R16 → digits
  comparable across the two runs).
- Drift medians (entry-median ret, delay-real, all·h1·h2) and per-event
  median ret are reported per cell as description, following R16's block.

## COMPOSE rule (verbatim from R16, the decision rule for the lane)

**This run composes with R16's HOLD (`data/oosExpansion`) cell verdict ONLY
if the fresh pointer ALSO passes** — the both-dirs rule needs two gradeable
SIBLINGS. Concretely, per (burstUsd stake ╳ horizon) pair:

- If R16's HOLD verdict on the SAME (usd, horizon) cell is PASS **AND** the
  fresh dir's verdict on the same cell is PASS (with both delay-realistic
  resolution p5 > 0), the pair is a **live-lane candidate**, and the paper
  gate upgrades to a fully-composed trans-transport statement.
- If the fresh dir is INCON-THIN on a cell (the cache is incomplete at
  grading time), the cell verdict stays **INCON-THIN** — the composition is
  re-run mechanically when the pull completes; nothing is faked.
- If the fresh dir FAILs a R16-HOLD-PASSing cell, the composed lane DIES for
  that stake/horizon (a real falsification of trans-transport, not thinness).
- R16's HOLD PASSES are pre-known: res at ≥$10k; **T+7d at all three stakes
  (+0.020/+0.023/+0.015, P(>0) 0.97–0.99)**. T+1d/T+3d passed the median
  story but FAILed the full gate on HOLD (t3d P(>0) 0.770) — the fresh dir
  re-tests those horizons on the same family.

## Lane-3 tie-in (pre-registered readout shape)

Lane 3 (`research/paperLanes.md`) reads ≥$10k bursts in the **0.55–0.90**
band on liquid live markets with **T+3d/T+7d mark closes**, and will be
read at T+3d/T+7d closes when n ≥ 20 closes accrue (2026-10-17: 3 alerts on
day one, all in 0.55–0.85, budget capped). At the end, this run prints one
explicit reconciliation sentence comparing (i) the fresh grade, (ii)
R16's HOLD cell, and (iii) lane-3's live band buckets readout expectations:
whether the [0.55,0.85) sub-band evidence (both this run and R16) keeps
lane-3's 0.55–0.85 slice expectations at T+3d/T+7d drift-positive, and
whether the [0.85,0.90) slice (covered here only via R16's gate-killed
[0.85,0.98) heavy-favorite rung) stays expectation-neutral (lane-3's
readout is then a diagnostic, not a continuation vote).

## Housekeeping constraints (fixed)

- `uv run pytest` green (175+ expected), `ruff check` clean on the new
  files; **no commits**; **no `src/` edits**; no `data/live` touches (the
  live watcher keeps running); **memory ≤ 4GB** during every grading step
  (scan/stream, no full-tape materialization beyond the new dir alone);
  Gamma crawl pace ≤ **4 req/s** via the repo `HttpSession` pacing adapter.
- Dirs are never mixed: fresh grading only ever reads `[data/midTopup]`
  ALONE; R16's reference dirs are read without re-fingerprinting by their
  existing caches only, never merged into the fresh cache.

---

## Tag list (frozen NOW, before the first crawl call): 26 military-adjacent
## tag slugs, taken from the tag set observed on the oosExpansion roster's
## own gamma event caches (the §9.1 roster's tags, data/oosExpansion/raw):

> geopolitics, middle-east, israel, iran, gaza, ukraine, russia,
> venezuela, foreign-policy, diplomacy-ceasefire, lebanon, syria,
> hezbollah, yemen, israel-x-iran, khamenei, ukraine-peace-deal,
> military-strikes, india-pakistan, hamas, peace-deal, war, strike,
> military-action, nato, taiwan

Crawl = one `closed=true` `volume_min=100000` keyset walk per tag (≤60
pages of 100 each, ≤4 req/s via the HttpSession adapter, page caches under
`data/raw/thirdUniverse/<tag>/`), events dedup'd by id across tags.


### Run 1 — detached fetch launched; partial grading pass (PARTIAL cache, mid-pull)

- Discovery ran in 17.5s (`logs/midbandTopupRoster.log`): 1493 closed events
  ≥$100k across the 26 pre-registered tags → 1450 resolved-only → 962
  military-tuple → 674 NOT carried by any existing dir/config (288 excluded:
  13+81+60+200 dir slugs + 60/200/9/72 config slugs) → **150-slug roster
  (101 stems), configs/midbandTopup.yaml**, total gamma volume $512M.
  No fill/price/burst content was read at selection time (gamma metadata
  only) — the selection-honesty constraint holds.
- Detached fetch: `nohup uv run pc2 fetch --config configs/midbandTopup.yaml
  >> logs/fetchMidTopup.log 2>&1`, launched 16:20 EDT. Raw schema verified on
  the first landings: 150/150 event JSONs (`slug__*.json`) and trades caches
  carry the same keys/structure as data/oosExpansion's fetch (event keys +
  market closed/outcomes; trades keyed by conditionId).
- Cache mechanics before any grading (Gate 2): the fresh pull's mid-band
  ≥$10k cell census on the PARTIAL cache reached 17 events / 35 entries
  (native) and 14 events / 26 entries (delay-realistic) — every family cell
  INCON-THIN at MIN_CELL=20 **so no verdict, no bootstrap consumed**;
  (`logs/midbandTopup.log`, Run 1 tables; full grid deferred to the final
  run). Entries cache rebuilt per partial fingerprint
  (`entries_v2_d10fc9a173.parquet` — fingerprints move while the fetch
  writes more raw caches; the final grading rebuilds once on the
  fingerprint-stable `data/midTopup` dir).
- **Spot-check (R16's hand recipe) on the mid-band entry
  "iran-military-response-by-august-12" / 2024-08-12 19:38:07:**
  hand burst usd = 12944.52 = cache; hand own-burst avg price 0.82; delayed
  fill 0.82 = cache nextPrice. One caveat found and documented (same in
  every sibling dir): the shipped entries-cache tape join is UNPINNED on
  same-second account collisions — at that exact (market, outcome, ts)
  three accounts print (0.82 own / 0.18 Yes-side / 0.84 other), and the
  keep-last pick can serve another account's print as the cached `price`
  column (R2's documented tie noise; family-verbatim, kept as shipped —
  the own-account aggregation and the delay fill are exact).
- Anchor sanity (description, ≥$10k ANY price/age on the partial dir):
  n=1956, retReal +2.6%, winRate 94.6% — the control-cell pattern is
  present on the fresh military tape (same shape as R16's anchors).
- RAW CACHE MUTATION CAVEAT (Run-1 lesson, worth keeping): the live fetch
  rewrites a market's trades cache while walking; a partial build read
  mid-rewrite once, and a rebuilt fingerprint produced a spot-check sample
  from the pre-rewrite row set (illustrated the tie artifact cleanly, and
  re-verified clean on the rebuilt cache). The grading run's build is
  consistent within itself; the final grade must (and will) run on the
  fingerprint-stable completed dir, never mid-rewrite.

**Run-1 composed verdict: all 12 (usd × horizon) compose rows BLOCKED by
fresh THIN — exactly the mechanical no-verdict state the compose rule
prescribes; the reconciliation sentence printed is the PRELIMINARY one.**

## Results (appended after the runs — clearly separated from the pre-registration)

### Run 2 — fresh fetch COMPLETE; final grading on the finished dir (mechanical verdicts)

- Fetch landed ~17:25 EDT (≈65 min, background): **1075 markets / 150
  events, 6,756,830 fills, 244,341 accounts, tape 2024-07-31 → 2026-09-30**
  — inside the pre-registered estimate (6–9M fills, fits the budget with
  room). All 150 roster events resolved (every one of the 1075
  markets carries a winner (resolved-only cohort held up end-to-end)).
  `logs/fetchMidTopup.log`; dir built to `data/midTopup` (never mixed with
  any other dir).
- Entries cache: fingerprint-stable build `entries_v2_3f66d77042.parquet`
  (2,133,004 burst entries) on `[data/midTopup]` ALONE; landed300 overall
  **61.56%** (liquid at burst time, comparable to oosExpansion's 68.8%,
  far above data/oos's 49.8%).
- Spot-check (same entry as Run 1): hand burst usd 12944.52 = cache; own
  burst avg 0.82; delayed fill 0.82 exact. The cached `price` column again
  shows the R2 same-second tape-tie artifact (keep-last among same-second
  prints 0.82/0.84 — family-verbatim as graded in every sibling).
- Anchor (desc, ≥$10k ANY price/age): n=3188, retReal +1.82%, winRate
  93.6% — control-cell tape confirmed; delay-real n=2474, mean +0.84%.

**Graded grid (n / events / retMean / win% / p5 / P(>0) / topShare /
landed% / verdict — dr frame, fresh<=5d baseline row):**

| stake | res | t1d | t3d | t7d |
|---|---|---|---|---|
| ≥$10k | 66/34, −0.030, 69.7%, −0.223, 0.416, –/73.3%, **FAIL** | 66/34, −0.186, 42.4%, −0.331, 0.010, **FAIL** | 66/34, −0.211, 53.0%, −0.358, 0.013, **FAIL** | 66/34, −0.111, 62.1%, −0.281, 0.161, **FAIL** |
| ≥$25k | 16/12 — INCON-THIN ×7 (all horizons/convs) | | | |
| ≥$50k | 2/2 — INCON-THIN ×7 | | | |

- Age ablation (≥$10k): **0–1d is worse, not better** (res dr p5 −0.301,
  P(>0) 0.231; t7d p5 −0.355, P(>0) 0.070) — R4's age-gate flip re-observed;
  **2–5d has positive medians (+20.4% at t7d, +19.7%/+21.3% h1/h2) but n=12
  entries / 8 events → INCON-THIN**, ungradable at MIN_CELL=20. Native res:
  ≥$10k 90/39, +0.082, 76.7%, p5 −0.071, P(>0) 0.835, topShare 0.332 — FAIL
  (P(>0) 0.835 just misses the 85% bar; delay-realistic kills it
  outright).
- **Drift-medians story (delay-real, ≥$10k):** medAll +22.8% (res) ·
  −1.5% (t1d) · +0.7% (t3d) · **+12.8% (t7d)** with both halves positive
  (h1 +14.7%, h2 +6.0%) — the *median* drift-up tail of R16's claim IS
  present on the fresh cohort, but its MEAN is negative and the event-floor
  distribution (p5 −0.281, P(>0) 0.161) cannot carry a gate: exactly R16's
  honest alternative bucket "fat-tail artifact / no tradeable floor".

**COMPOSE verdict (the pre-registered rule, mechanical):**

- ≥$10k res: HOLD=PASS, fresh=**FAIL** → **COMPOSE DIES** (fresh
  falsifies the HOLD-PASSing cell).
- ≥$10k t7d: HOLD=PASS, fresh=**FAIL** → **COMPOSE DIES**.
- ≥$10k t1d/t3d: both dirs FAIL — corroboration of death, not a lane.
- ≥$25k/≥$50k: fresh INCON-THIN (and moot: R16 HOLD's dr-res p5 −0.014 /
  −0.018 pre-kills any non-$10k compose under the delay-realistic floor).
- **Composed live-lane candidates: NONE. R16's only surviving cell family
  (≥$10k+ bursts in [0.55,0.85), res + T+7d marks) DOES NOT survive a second
  gradeable military sibling — the trans-transport claim is falsified, not
  inconclusive.** The mid-band paper-gate from R16 is retired unless a NEW
  pre-registered proposal restarts the family (none is warranted by these
  digits); the 2–5d median-only hint is recorded as description, not a
  candidate.

**Lane-3 reconciliation sentence (the explicit tie-in):**

> The fresh mid-band [0.55,0.85) cell FAILs the graded gates for ≥$10k at
> res, t1d, t3d, t7d on the completed fresh cohort (worst: t1d, p5 −0.332,
> P(>0) 0.008), so the compose rule DIES the R16 live-lane family on the
> ≥$10k stake (its HOLD-PASSing cell is falsified, not re-thinned), while
> the ≥$25k/≥$50k rows are INCON-THIN but can never compose anyway (R16
> HOLD dr-res p5 < 0 pre-kills every non-$10k stake) — lane-3 readout
> expectation: the [0.55,0.85) slice of lane-3's 0.55–0.90 band downgrades
> to a DIAGNOSTIC-NEGATIVE trans-transport expectation (mean-side negative
> on the fresh cohort: the drift-median story was fat-tailed, not
> gate-gradeable), while the [0.85,0.90) slice stays expectation-neutral
> (riding R16's gate-killed [0.85,0.98) heavy-favorite rung, HOLD dr-res
> P(>0)=0.535, topShare 8.6) — lane-3 should therefore read the two bucket
> slices separately, with neither slice carrying a promotion signal from
> the offline family anymore.

Housekeeping at close: `uv run pytest` 195 passed + 1 environment-coupled
`tests/test_paperLanes.py::test_lane2_clone_writes_identical_shape`
failure that is NOT this run's: the test asserts the live repo has NO
`data/live/signalsLane2.csv`, and the RUNNING lane-2 watcher fired its
first real signal mid-session (16:46 EDT) creating that file — the suite
had passed 196/196 earlier this session (16:26) before the live signal
landed. `ruff check` clean on both new scripts; no commits, no `src/`
edits, no `data/live` touches; grading memory well inside 4 GB (2.1M-entry
entries cache, 3.4M-print exit tape); Gamma ≤4 req/s via the HttpSession
adapter (26-tag keyset walk, 17.5s). The expected-total estimate
double-checks: 6–9M fills predicted vs 6,756,830 actual (oosExpansion
scaled ~0.75×: 10.66M fills / 200 slugs × 150 slugs).
