# Episode-level regrouping wired into the transport evaluation (the §9.2 limitation, closed)

Scripts: `scripts/research/episodeTransport.py` (additive module: tape-level
episode graph + K* gate + verdict composition), wired behind a `--episodes`
flag (default OFF) into `entrySweep.runSweep` (eval path) and
`oosTransport.main` (candidate neighborhood). Everything reuses the absorbed
feature/episodeScope machinery — `scripts/research/episodeResample.py` by
importlib-by-path: `sharedAccountEdges`, `episodeGroups`, `episodeStats`
(Σpnl/Σcap ratio estimator, `Random(7)` discipline), the fine K-sensitivity
grid, `dataDerivedK`, and the iran-Feb-2026 ground-truth reference rule.
See `research/episodeResample.md` for the unit definition (two slugs are one
EPISODE when they share ≥K distinct accounts holding ≥$5k bursts in both)
and the band publication; this note only records how the gate COMPOSES with
the per-event transport verdict and what the regrade found.

## How the episode unit is built for a transport run

`buildUnits(entries)` runs ONCE per tape (the account-overlap graph is a
property of the tape, not of one cell):

- universe = every ≥$5k burst entry on the tape (no price/age/markets
  gating — the unit rule is the episodeResample doc's, EPISODE_MIN_USD=5000);
- the fine sensitivity grid (step-2 1..40 + 50/100) is walked and
  **K\* := the largest K that keeps the iran-Feb-2026 reference at ≤2
  episode groups on THIS tape**;
- when the reference is absent on the tape, or splinters at every grid K,
  the gate PINS at the in-sample K\*=34 and the printout says
  `pinned (...)` — the gate is then policy-anchored, and the number is
  published either way, never silently chosen;
- `episodeOverrides.yaml` merge/exclude still honored (empty by default).

On the oosExpansion tape (`entries_v2_5a57e33ce8`, 3,599,688 entries /
34,924 ≥$5k bursts / 191 slugs): **K\* = 28, data-derived** (14 iran-Feb
reference slugs → 2 groups, PASS). The holdout graph is far less
ladder-welded than the in-sample tape (49 groups at K=5, largest 143, vs 2
groups on `[data, data/universe]`) — future OOS pulls derive their own gate.

## How the K* gate composes per-event and per-episode verdicts

Per cell (the same `filterCell` gates as the shipped sweep):

1. **Per-event gate (shipped, unchanged)**: `entrySweep.evaluate` bootstrap,
   floor ranking still `runSweep`'s (p5, ret). PASS iff p5 > 0 AND P(>0) ≥
   0.85 (the pre-registered security bar from status.md §9.2, the two
   clauses a sweep row carries; the delay-realistic and top-event-share
   clauses still live in oosTransport, which adds its dr clause on top).
2. **Episode gate (new)**: `episodeResample.episodeStats` over the cell with
   the tape labels — episodes resampled with replacement, B=1000 (same B as
   the per-event bootstrap in this path; the research script keeps B=10000
   for its published tables), seed 7, fresh per call so digits are
   order-independent and reproducible. Verdict at the gate point K\*:
   - PASS iff P(>0) ≥ **0.80** (the doc's falsification bar) with **≥3
     episodes** in the cell;
   - DEGENERATE otherwise at fewer than 3 episodes (the over-merge band's
     single-mega-episode read "is the one big episode positive"; published
     as such, never grants PASS);
   - FAIL otherwise.
3. **Composed verdict**: PASS only if BOTH gates say PASS. The episode gate
   can only ever ADD a FAIL — pooling correlated dated-ladder rungs into
   single resample units INFLATES what the stability check demands, so a
   per-event FAIL can never be rescued by regrouping (and the composition
   is needed the other way too: a tape where a big-positive rung absorbs a
   small negative one can read epP = 1.0 at K\* while the per-event floor
   is broken — the welded-pool test in `tests/test_episode_transport.py`
   demonstrates exactly that and why both gates are ANDed).

Report side-by-side (per ranked cell): the per-event `p5`/`P(>0)` columns
unchanged, plus `episodes`, `epP`, `epP5`, `epP95`, ex-top-episode
(`exTopP`/`exTopRet`/`exTopP5`), `kStar`, `epVerdict`, `verdict`. `ret` is
unit-invariant at both levels (episodeResample lesson 1). `runSweep`'s
column set and sort are untouched; with the flag off the CLI reproduces
the shipped behavior byte-for-byte — the diffs to `entrySweep.py` /
`oosTransport.py` are entirely additive.

## Validation — the already-graded §9.2 OOS cell re-graded under the episode view

The flagship failure cell, `--data-dir data/oosExpansion`, cache
`entries_v2_5a57e33ce8.parquet` (untouched on disk), $10k / ≤0.35 / ≤5d /
≤3mkts, fresh-seed `Random(7)` replay through the wired path:

- per-event (graded reference §9.2: p5 −0.875, P(>0) 0.0%, ret −0.727,
  delay-realistic −0.812 → FAIL): replay p5 −0.879, P(>0) 0.0, ret −0.727,
  167 entries / 34 events → FAIL. (The −0.004 p5 delta is the graded run's
  sequential-rng state vs the fresh seed; ret/h1/h2 are exact.)
- per-episode at the data-derived K\*=28: 13 episodes, episode p5 −0.867,
  P(>0) 0.217 < 0.80, ex-top ret −0.778, ex-top P 0.153 → FAIL. The scene
  the §9.2 caveat predicted: regrouping the 34 rung events into 13
  processes does not conjure stability — the composed verdict stays FAIL.
- whole `--episodes` runs, end to end through both wired CLIs:
  `entrySweep --grid configs/sweeps/oosExpansionEntryGrid.yaml --episodes`
  → 480 cells, 466 FAIL / 14 INCON, zero PASS; `oosTransport --episodes`
  → 48 candidate cells, all FAIL. Neither flips anything upward; caches
  and `oosTransportCells.parquet` left untouched on disk.

Tests: `tests/test_episode_transport.py` (12 pytest cases, all on synthetic
frames): regrouping through `attach` (welded rungs → one episode, shipped
sort and columns untouched, flag-off identical), the K* gate verdict flip
on K (epP 1.0 at K=5 welded pool → FAIL at K=100 with the negative rung
splintered out, converging digit-for-digit onto the per-event bootstrap),
the 0.80-bar and ≤2-groups ground truth, derived-vs-pinned K\* builds, the
degenerate over-merge guard, and the composition rules. `uv run pytest` is
green (150 passed); `ruff check` clean on every touched file.
