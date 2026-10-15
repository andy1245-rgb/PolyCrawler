# Episode-level resampling: re-baselining the burst-entry cells honestly

Scripts: `scripts/research/episodeResample.py` (entrySweep internals reused by
importlib-by-path). Data: `data/` + `data/universe/` — exactly the dirs the
entrySweep sweeps (`researchData.RESEARCH_FETCH` → `researchDataDirs()`),
via its own cached burst-entry tape (`entries_v2_df8efad228.parquet`) and
entrySweep's own `filterCell` + `evaluate`. The keyword generalization the
non-military control needs lives in **`researchData.militaryMarketsFrame(dirs,
keywords)`** (merge decision: one owner — the parametrized filter was pushed
into researchData instead of staying as a copy inside entrySweep; the cache
fingerprint carries the keyword digest so the two universes cannot collide).
Cache note: after the merge the fingerprint recipe (main's stat-per-file
digest + the branch's keywords digest) reproduces the branch's digest byte
for byte, so the cache name is unchanged — the run below loaded the existing
tape, no rebuild.

## The unit problem

`entrySweep.evaluate` resamples **event slugs** with replacement. On dated
ladders ("israel-strikes-iran-by-january-9 / -16 / -31 / february-28 /
march-31-2026", "khamenei-out-…-by-february-28 / march-31", "us-strikes-iran-by
(-october-3)") the rungs are rungs of **one process**, not independent
markets. Counting rungs as independent wins is a consistent-unit error; the
shipped military cell ($5k / ≤0.35 / ≤5d / ≤3mkts) scores event-level
P(>0) 0.99 (p5 +0.27) partly on those rungs while the process is one bet.

## Headline first: concentration

**No episode-level edge survives removing the iran-Feb process cluster.** In
the shipped cell, the episode that owns the whole +1.17 is the iran-Feb
process cluster's episode: it holds **+50,721 of the cell's +50,400 total
PnL (100.6%) at the K=20 anchor** (99.4% at K=12, 101.3% at the shipped gate
K*=34 — i.e. MORE than all of the PnL; the other episodes net LOSE). Ex-top
(removing that one episode) the shipped cell is **P(>0) 0.10–0.28 with ret
−0.27…−0.47 at every ≥3-partitioned K in the window (12–34)**; the only
positive ex-top point (K=12, ret +0.93, P 0.75) rests on the 3 leftover
entries (+280 PnL total across 3 trades) — a thin sample, not an edge. The
review preview quoted "~105% of PnL in one K=20 episode"; measured on this
run: 100.6%. Same statement either way: the category-level edge IS one
process's PnL.

## Method

Run: `uv run python scripts/research/episodeResample.py [--k K*] [--refresh]
[--bands] [--sensitivity] [--md] [--out research/episodeResample.md]`.

- **Unit definition (data-derived).** Two military slugs are the same
  **episode** when they share ≥K distinct accounts that each put a **≥$5k
  burst** (whole burst aggregate, same burst entries the sweep builds) in
  **both** slugs. Union-find over slug nodes with those shared-account
  edges gives episode labels. Manual fixes live in
  `configs/episodeOverrides.yaml` (`merge:` force-groups, `exclude:` severed
  pairs) — empty by default, documented there.
- **The gate is data-derived.** The fine sensitivity grid (step 2 across
  1–40 plus 50/100 — the previous 9-point grid skipped 11–19 and 21–49,
  where verdicts flip) is printed on every run, and
  `--k` defaults to **K\* := the largest K in the grid that keeps the
  iran-Feb reference set at ≤2 episode groups** (no splinter). On the
  current tape **K\* = 34** (the first splinter, 3 groups, is at K=36). The
  earlier preview checked only through 30 — 32 and 34 also hold, which the
  finer grid found. An explicit `--k<int>` overrides the gate.
- **Ground-truth reference set — honest build recipe.** The iran-Feb-2026
  reference = slugs containing the substring "iran" (lowercased) that held a
  ≥$5k burst signal inside calendar Feb-2026. That IS a name-match + 
  calendar window rule — kept deliberately as a cheap reproducible probe of
  the ladder process; the per-slug check must not be conflated with the
  unit definition, which remains account-overlap. Current membership (10
  slugs): us-strikes-iran-by, us-next-strikes-iran-on-843,
  us-x-iran-ceasefire-by, usisrael-strikes-iran-by, the february-28,
  january-31-2026(-418) and march-31 israel-strikes-iran rungs, the two
  khamenei-out rungs, will-the-iranian-regime-fall-by-march-31.
- **Resampling.** Per cell: per-episode aggregate pnl (sum retReal·100) and
  cap (entries·100) exactly as `entrySweep.evaluate` defines them, then
  **episodes** resampled with replacement, B=10000, rng `random.Random(7)`
  (entrySweep's discipline), same ratio estimator (Σpnl / Σcap). `ret`
  (mean retReal) is identical at both levels by construction — the point
  estimate doesn't change; the resampling changes what "P(>0)" means.
- **Bands, not points.** Episode-level P(>0) is published as a BAND across
  the GT-admissible K window (K range up to and including K\*), per cell —
  a single-point headline was the artifact of the coarse grid. Ex-top
  episode (drop the largest-pnl episode and recompute) is published for
  every row (own `Random(7)` stream per call, so numbers are
  order-independent).
- Event-level numbers come **straight from entrySweep's** `filterCell` +
  `evaluate` (B=1000, same code path), both columns of identical entry
  construction and return semantics.

## Episode table — labels are positional; cite slugs

`episodeLabels` names groups `ep1, ep2, …` **positionally in the
deterministic group order**. The order depends on K and group size, so
"ep1" points at a different episode if K changes: **do not cite bare epN
without the slug list.** Always re-derive the table from the printed
episode output (`episodeTable` lists the member slugs per row). For the
record at the old anchors:

**K=5 (over-merged mega-episode; for the record):**

| episode | member slugs (fragment) | slugs | ≥$5k signals | span |
|---|---|---:|---:|---|
| ep1 | the whole military universe minus one slug — every iran/israel/ukraine/russia/maduro/venezuela/hezbollah/houthi/taiwan/Pakistan ladder rung | 45 of 46 | 38,275 | 2024-09-20 → 2026-08-19 |
| ep2 | us-operation-to-capture-maduro-in-2025 | 1 | 1 | 2025-12-26 |

**K*=34 (shipped gate):** 22 episodes in the graph, 11 of them hold the
shipped cell's 431 signals; the edge-carrying episode (`ep1` at K*=34,
confirmed by slug list: houthi-strike-on-israel-by-august-31,
israel-strike-on-iranian-nuclear-facility-in-2024,
israel-strikes-iran-by-february-28-2026, the khamenei-out rungs,
israel-x-hamas-ceasefire-before-august, maduro-out-in-2025, … 25 slugs
total) holds 36,060 of the graph's ≥$5k signals (the initial run of the
K=5-era doc quoted 38,275 for the same episode pre-splinter: the number
moved WITH the label — exactly why the slug list, not epN, is the key).

The account-overlap graph **over-merges**, not splinters: 1,615 of 4,908
≥$5k-burst accounts trade ≥2 military slugs and 9 accounts trade ≥20, so
low K welds everything into one episode. The ground truth check PASSES at
the gate: the iran-Feb reference set occupies **2 episode groups at K*=34**
(one merged cluster + one splintered rung) — inside the ≤2 bar, first
violated at K=36.

### K sensitivity, fine grid (measured on `entries_v2_df8efad228`, 2026-10-15)

| K | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 14 | 16 | 18 | 20 | 22 | 24 | 26 | 28 | 30 | 32 | **34** | 36 | 38 | 40 | 50 | 100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| episodes | 1 | 2 | 2 | 2 | 2 | 2 | 4 | 5 | 8 | 10 | 11 | 11 | 12 | 15 | 16 | 18 | 20 | 21 | 21 | **22** | 25 | 26 | 26 | 30 | 36 |
| largest | 46 | 45 | 45 | 45 | 45 | 45 | 43 | 42 | 39 | 37 | 36 | 36 | 35 | 32 | 31 | 29 | 27 | 26 | 26 | **25** | 22 | 20 | 20 | 17 | 11 |
| iran-Feb groups | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 2 | 2 | 2 | 2 | 2 | 2 | **2** | **3** | 3 | 3 | 3 | 5 |

The old published table's gap (11–19, 21–49) is where the verdict-relevant
moves live: the iran-Feb reference holds 1 group through K=18 (matching the
old 9-point grid), 2 groups through K=34 — the old "only K≤20" claim was
wrong — and 3 groups from K=36 (not at 50, as the old grid implied).

## Cells — both levels, at the K*=34 gate (B=10000 episodes / B=1000 events, seed 7)

| cell | n | events | ret | ep | P(>0) event | p5 event | P(>0) episode | p5 episode | p95 episode | ex-top episode | ex-top ret | ex-top P | ex-top p5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| shipped $5k/≤0.35/≤5d/≤3mkts | 431 | 29 | +1.17 | 11 | +0.99 | +0.27 | +0.70 | −0.68 | +1.22 | iran-Feb cluster ep (+51054) | −0.34 | +0.16 | −0.83 |
| candidate $10k/≤0.35/≤5d/≤3mkts | 160 | 20 | +1.85 | 5 | +0.99 | +0.78 | +0.79 | −1.00 | +1.91 | iran-Feb cluster ep (+29610) | −0.03 | +0.39 | −1.00 |
| shipped cell, age ≤1d | 348 | 27 | +1.30 | 11 | +0.99 | +0.37 | +0.74 | −0.61 | +1.35 | iran-Feb cluster ep (+45556) | −0.22 | +0.27 | −0.80 |
| shipped cell, age 2-5d | 83 | 15 | +0.63 | 3 | +0.78 | −0.74 | +0.71 | −1.00 | +0.68 | largest-pnl episode (+5498; slugs in run output) | −1.00 | +0.00 | −1.00 |
| non-military control $5k/≤0.35/≤5d/≤3mkts | 303 | 28 | +0.28 | 16 | +0.68 | −0.55 | +0.83 | −0.91 | +0.79 | will-biden-drop-out-of-presidential-race ep (+7244) | +0.05 | +0.58 | −1.00 |

Labels quoted here carry their slug content, not just the positional epN,
because `episodeLabels` numbers are positional (see below). The control
ex-top slug was probed from the run (label ep33 in the control's own
graph; CITE THE SLUGS, not epN).

## Band tables — the FULL admissible K window, not a point

### Shipped cell P(>0) band across K ≤ K*=34

| K | episodes(cell) | P(>0) episode | p5 episode | ex-top ret | ex-top P |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1.00 | +1.17 | — | 1.00 |
| 2 | 1 | 1.00 | +1.17 | — | 1.00 |
| 4 | 1 | 1.00 | +1.17 | — | 1.00 |
| 6 | 1 | 1.00 | +1.17 | — | 1.00 |
| 8 | 1 | 1.00 | +1.17 | — | 1.00 |
| 10 | 1 | 1.00 | +1.17 | — | 1.00 |
| 12 | 3 | 0.96 | +0.45 | +0.93 | 0.75 |
| 14 | 5 | 0.78 | −1.00 | −0.27 | 0.28 |
| 16 | 6 | 0.75 | −1.00 | −0.36 | 0.25 |
| 18 | 6 | 0.75 | −1.00 | −0.36 | 0.25 |
| 20 | 6 | 0.75 | −1.00 | −0.36 | 0.25 |
| 22 | 7 | 0.73 | −1.00 | −0.42 | 0.22 |
| 24 | 8 | 0.71 | −1.00 | −0.47 | 0.18 |
| 26 | 9 | 0.71 | −0.75 | −0.34 | 0.19 |
| 28 | 9 | 0.71 | −0.75 | −0.34 | 0.19 |
| 30 | 10 | 0.68 | −0.81 | −0.45 | 0.10 |
| 32 | 10 | 0.68 | −0.81 | −0.45 | 0.10 |
| 34 (K*) | 11 | 0.70 | −0.68 | −0.34 | 0.16 |

READ: the band's top end (P 1.00 for K ≤10) is the single mega-episode's
degenerate verdict "is the one big episode positive" — it carries no
distribution meaning. From K=12 (first ≥3-partition) on, episode-level
P(>0) walks 0.96 → 0.68–0.70 — **not one non-degenerate K point clears the
falsification bar (P ≥ 0.80)**. The K=12 ex-top positive (ret +0.93, P 0.75)
rests on the 3 leftover entries (+280 PnL: one 2-entry episode at +380 and
one −100); by K=14 the 8 leftovers net −220 and every following row is
negative. The shipped verdict cannot flip positive at any detail level in
the window.

### $10k candidate P(>0) band across K ≤ K*=34

| K | episodes(cell) | P(>0) episode | p5 episode | ex-top ret | ex-top P |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1.00 | +1.85 | — | 1.00 |
| 2–10 | 1 | 1.00 | +1.85 | — | 1.00 |
| 12 | 2 | 1.00 | +1.85 | +1.90 | 1.00 |
| 14 | 3 | 0.96 | +0.45 | +0.93 | 0.74 |
| 16 | 4 | 0.94 | −1.00 | +0.45 | 0.71 |
| 18 | 4 | 0.94 | −1.00 | +0.45 | 0.71 |
| 20 | 4 | 0.94 | −1.00 | +0.45 | 0.71 |
| 22 | 4 | 0.94 | −1.00 | +0.45 | 0.70 |
| 24 | 4 | 0.94 | −1.00 | +0.45 | 0.70 |
| 26 | 5 | 0.79 | −1.00 | −0.03 | 0.39 |
| 28 | 5 | 0.79 | −1.00 | −0.03 | 0.39 |
| 30 | 5 | 0.79 | −1.00 | −0.03 | 0.39 |
| 32 | 5 | 0.79 | −1.00 | −0.03 | 0.39 |
| 34 (K*) | 5 | 0.79 | −1.00 | −0.03 | 0.39 |

(Identical adjacent rows collapsed at K=2–10; the full per-K table prints
with `--bands`.) The candidate holds the ≥0.80 bar through K≤24
(0.94–1.00) and **loses it at K ≥26 (0.79, p5 −1.00, ex-top P 0.39)** — a
verdict-flipping internal boundary inside the 21–49 span exactly the old
grid skipped. Its P(>0) band [0.79, 1.00] is wider than the shipped cell's
[0.68, 0.96]; same critical caveat: its p5 is −1.00 at every
non-degenerate K.

## Reading, integrated with the band tables

- **Ret is unit-invariant; everything else moves.** The shipped cell's ret
  is +1.17 at every level and every K — ret is unchanged by the unit
  question. Every P claim IS a function of K (and of the unit): it must be
  quoted with its K. Event-level P 0.99 vs episode-level band 0.68–0.96:
  the event-level number was reading rung-level luck.
- **The iran-Feb process cluster IS the category edge.** Concentration
  stat up front (100.6% of the shipped cell's PnL in one K=20 episode):
  **no episode-level edge survives removing the iran-Feb cluster.**
- **The band (not the point) is the verdict.** The single-point headline
  cells previously published (0.75 at K=20 shipped, 0.94 at 20 for $10k)
  were selected implicitly by the coarse grid; the full window moves the
  shipped verdict between 0.68 and 0.96, the $10k's between 0.79 and 1.00 —
  and specifically marks **where the flips happen (K=12–14 shipped, K=24–26
  for the $10k)**.
- **Falsification bar (episode-level P(>0) ≥ 0.80) verdict:** the shipped
  cell FAILS at every non-degenerate K ≥14 in the window. The $10k
  candidate PASSES K ≤24 and FAILS at 26–34; at the shipped gate K*=34 it
  reads P 0.79 < 0.80, so under the data-derived default it FAILS too —
  the old "the candidate clears it" statement rested on a single K=20
  read and does not survive the band.
- **Age split:** the 2–5d bucket is a different process mix (3 episodes at
  K*=34, P 0.71) while ≤1d remains the same concentrated cluster shape as
  the full cell (11 episodes, P 0.74, ex-top 0.27).
- **Event-level digits got fixed and republished.** The deterministic-sort
  fix (below) changed the event-level digits by the drift magnitude
  measured before the fix: shipped P 0.98→0.99, p5 +0.32→+0.27 — inside
  the ~±0.04–0.08 p5 spread row-order was causing. Every event digit in
  THIS table is now exactly reproducible.

## Lessons

1. **Consistent-unit principle**: dated rungs of one ladder = ONE sample, by
   data-derivation (account overlap), not by name-guessing. Any bootstrap
   claim must state its unit; event- vs unit-level P(>0) can differ by 0.29
   on this tape (event 0.99 vs band floor 0.68–0.70 at the non-degenerate
   K detail).
2. **Any extension claim must now clear the episode-level band, not a
   point**: run `--bands`, quote P(>0) across K ≤ K* from the fine grid,
   with the ground-truth check passing (K* is printed and data-derived),
   and with ex-top-episode stats — the shipped cell does not survive ex-top
   at ANY partitioning K in the window. Over-merge swings both ways; the
   world is bridged by professional multi-market accounts (9 accounts
   trade ≥20 military slugs).
3. **Concentration from the account side**: 1,615/4,908 ≥$5k-burst accounts
   trade ≥2 military slugs; the military "category" edge and the
   multi-slug professional population are the same population. Treat
   category-level claims as process-level claims first — and state the
   share of PnL in the single process (100.6% K=20 measured).

## Caveats

- The K gate is **data-derived by default now**: `--k` unset means K*
  (largest K in the fine grid keeping the iran-Feb reference ≤2 groups;
  currently 34). The 1–10 end of the band is degenerate-over-merge
  (single episode) — published as such; the interpretable band starts at
  the first ≥3 partition (K=12).
- `episodeTable`/`episodeLabels` labels (`ep1…epN`) are POSITIONAL: the
  number repoints when K changes. Key every citation on the member-slug
  list (the table's `slugs` column or the sensitivity row), never on epN.
- Event-level P/p5 come from entrySweep's evaluate, which previously
  indexed RNG over un-sorted `group_by` row order — measured drift was
  ~±0.04–0.08 on p5 across runs, NOT the ~±0.01 an earlier version of this
  doc claimed. Fixed in this branch (sorted on `eventSlug` before RNG), so
  both levels are now strictly deterministic; episode-level always was.
- Fills keep arriving; these numbers re-baseline the shipped cell as of
  the `entries_v2_df8efad228` cache built from `[data, data/universe]` on
  2026-10-15 (cell n=431 vs the review's 434 — drift, same shape), and
  should be re-run after tape growth.
- No band- or gate-machinery was wired into `entrySweep` / `oosTransport`
  policy code in this pass: this doc + the episodeResample defaults are
  the whole change. (researchData received the keyword param only because
  the merge reconciliation needed one owner for the keyword filter;
  integration of the gate lands post-merge.)
- Hindsight detection on the fill tape as before (ages are lower bounds,
  order-book sizing not modeled).
