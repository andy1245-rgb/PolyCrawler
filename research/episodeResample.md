# Episode-level resampling: re-baselining the burst-entry cells honestly

Scripts: `scripts/research/episodeResample.py` (+ a small keyword
generalization in `scripts/research/entrySweep.py` so the sweep cache can
hold a second, non-military complement frame). Data: `data/` +
`data/universe/` — exactly the dirs entrySweep sweeps (`entrySweep.RESEARCH_FETCH`
→ `dirsFromConfig`), via its own cached burst-entry tape
(`entries_v2_df8efad228.parquet`) and its own `filterCell`/`evaluate`.

## The unit problem

`entrySweep.evaluate` resamples **event slugs** with replacement. On dated
ladders ("israel-strikes-iran-by-january-9 / -16 / -31 / february-28 /
march-31-2026", "khamenei-out-…-by-february-28 / march-31", "us-strikes-iran-by
(-october-3)") the rungs are rungs of **one process**, not independent
markets. Counting rungs as independent wins is a consistent-unit error; the
shipped military cell ($5k / ≤0.35 / ≤5d / ≤3mkts) scores event-level
P(>0) 0.98 (p5 +0.27) partly on those rungs while the process is one bet.

## Method

Run: `uv run python scripts/research/episodeResample.py [--k 5] [--refresh]
[--sensitivity] [--md]`.

- **Unit definition (data-derived, not name-matching).** Two military slugs
  are the same **episode** when they share ≥K distinct accounts that each
  put a **≥$5k burst** (whole burst aggregate, same burst entries the sweep
  builds) in **both** slugs. Union-find over slug nodes with those
  shared-account edges gives episode labels. Manual fixes live in
  `configs/episodeOverrides.yaml` (`merge:` force-groups, `exclude:` severed
  pairs) — empty by default, documented there.
- **Resampling.** Per cell: per-episode aggregate pnl (sum retReal·100) and
  cap (entries·100) exactly as `entrySweep.evaluate` defines them, then
  **episodes** resampled with replacement, B=10000, rng `random.Random(7)`
  (entrySweep's discipline), same ratio estimator (Σpnl / Σcap). `ret`
  (mean retReal) is identical at both levels by construction — the point
  estimate doesn't change; the resampling changes what "P(>0)" means.
- **Ex-top-episode** is published for every cell: drop the largest-pnl
  episode, recompute ret / P(>0) / p5 on the remainder
  (own `Random(7)` stream per call, so every number is order-independent).
- Event-level numbers come **straight from entrySweep's** `filterCell` +
  `evaluate` (B=1000, same code path), so both columns of the tables below
  use identical entry construction and return semantics.
- Cache note: `entrySweep.dataFingerprint` now includes the event-keyword
  tuple (it previously keyed only on the data dirs), since a second frame
  (the non-military complement, cache suffix `_nonmil`) shares the dir
  fingerprint; without this the two universes would collide in the cache.

## Episode table (K=5 default, ≥$5k bursts, [data, data/universe])

| episode | slugs | ≥$5k signals | span |
|---|---|---:|---|
| ep1 | **45 of 46 military slugs** — the whole universe: every iran/israel/ukraine/russia/maduro/venezuela/hezbollah/houthi/taiwan/Pakistan slug | 38,275 | 2024-09-20 → 2026-08-19 |
| ep2 | us-operation-to-capture-maduro-in-2025 | 1 | 2025-12-26 |

The account-overlap graph **over-merges**, not splinters: 1,615 of 4,908
≥$5k-burst accounts trade ≥2 military slugs and 9 accounts trade ≥20, so
K=5 welds everything into one episode. The ground truth check nevertheless
passes: the iran-Feb-2026 reference set (10 slugs with iran signals in
Feb-2026, re-derived from the tape — us-strikes-iran-by, the february-28,
january-9/16/31 and march-31 israel-strikes-iran rungs, the two khamenei
rungs, usisrael-strikes-iran-by, will-the-iranian-regime-fall-by-march-31)
sits in **1 episode group at K=5** — far from the ≥3 splinter failure bar.
Honesty note on the reference set itself: it is **substring match**
("iran" in the lowercased slug) **plus a calendar gate** (≥$5k burst signal
in Feb-2026) — deliberately a name+calendar probe, not the account-overlap
unit definition; the episode units stay data-derived and this set only
checks that the graph does not splinter the ladder.

### K sensitivity

| K | 1 | 2 | 3 | 5 | 8 | 10 | 20 | 50 | 100 |
|---|---|---|---|---|---|---|---|---|---|
| episodes | 1 | 2 | 2 | 2 | 4 | 5 | **12** | 30 | 36 |
| largest | 46 | 45 | 45 | 45 | 43 | 42 | 35 | 17 | 11 |
| iran-Feb groups | 1 | 1 | 1 | 1 | 1 | 1 | **2** | 3 | 5 |

Only at K≥50 does the iran-Feb ladder splinter (3 groups) past the bar, and
by then the split has destroyed the professional multi-market bridging that
the tape plainly shows (organic, not an artifact: the bridges are real money
in real envelopes on rungs of several processes). The reported gate is
therefore run at **both** ends and labeled:

- **K=5 (mandated default)**: 1 operative episode → episode-level P(>0)
  degenerates to "is the one mega-episode positive" (1.00 / 1.00 in the
  table; ex-top columns degenerate to the same number). Honest label: the
  gate as-spec'd is vacuous on this tape; it still passes the
  ground-truth sanity (no splinter).
- **K=20 (documented sensitivity gate)**: 12 episodes, iran-Feb ladder in 2
  groups — the tightest granularity that still does not splinter the
  ground truth. This is the interpretable column.

## Cells, both levels, side by side (B=10000 episodes / B=1000 events, seed 7)

K=20 gate:

| cell | n | events | ret | ep | P(>0) event | p5 event | P(>0) episode | p5 episode | p95 episode | ex-top episode | ex-top ret | ex-top P | ex-top p5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| shipped $5k/≤0.35/≤5d/≤3mkts | 431 | 29 | +1.17 | 6 | 0.98 | +0.32 | **0.75** | −1.00 | +1.20 | ep1 (+50721) | **−0.36** | **0.25** | −1.00 |
| candidate $10k/≤0.35/≤5d/≤3mkts | 160 | 20 | +1.85 | 4 | 0.99 | +0.78 | **0.94** | −1.00 | +1.89 | ep1 (+29410) | +0.45 | 0.71 | −1.00 |
| shipped cell, age ≤1d | 348 | 27 | +1.30 | 6 | 0.98 | +0.39 | **0.75** | −1.00 | +1.34 | ep1 (+45523) | **−0.36** | **0.25** | −1.00 |
| shipped cell, age 2-5d | 83 | 15 | +0.63 | 1 | 0.79 | −0.67 | 1.00 | +0.63 | +0.63 | ep1 (+5198) | — | 1.00 | +0.63 |
| non-military control $5k/≤0.35/≤5d/≤3mkts | 303 | 28 | +0.28 | 8 | 0.70 | −0.55 | 0.89 | −0.70 | +1.56 | ep24 (+7244) | +0.05 | 0.65 | −1.00 |

K=5 default (for the record; single mega-episode → degenerate episode col):

| cell | n | ret | P(>0) event | P(>0) episode | ex-top |
|---|---:|---:|---:|---:|---|
| shipped $5k/≤0.35/≤5d/≤3mkts | 431 | +1.17 | 0.98 | 1.00 | degenerate (single episode) |
| candidate $10k/≤0.35/≤5d/≤3mkts | 160 | +1.85 | 0.99 | 1.00 | degenerate |
| shipped cell, age ≤1d | 348 | +1.30 | 0.98 | 1.00 | degenerate |
| shipped cell, age 2-5d | 83 | +0.63 | 0.76 | 1.00 | degenerate |
| non-military control | 303 | +0.28 | 0.70 | 0.68 | ex-top ret −1.00, P 0.00 (4 eps) |

(All 431 shipped-cell signals fall in the single K=5 mega-episode; even at
K=20, 422/431 do — the edge of the shipped cell beyond the mega-episode is
9 signals at ±$100. The episode-level verdict *is* the mega-episode's
verdict, which is exactly the finding.)

## Reading

- **The event-level numbers are real; the unit inflation is too.** The
  shipped cell's +117% mean is intact at both levels (same entries). What
  moves is the distributional claim: cell P(>0) drops 0.98 → 0.75 and the
  per-draw floor goes from **+0.32 to −1.00** (p5) — i.e. no margin on the
  floor once ladder rungs are treated as one bet.
- **Ex-top-episode kills the headline**: remove the biggest-pnl episode
  (the iran process cluster) and the shipped cell is **ret −0.36, P 0.25,
  p5 −1.00**. The entire +117% is one process's PnL (+50.7 of +50.4k total).
  This is the operational version of the old "H1+H2 both positive mitigates
  but does not remove concentration" caveat, sharpened.
- **Age split confirms where the episodes live**: the age 2-5d bucket is a
  different process mix (1 episode, P 0.76-1.00) while ≤1d is the same
  concentrated mega-episode as the full cell. The 0-1d signals are the
  fresh-entree core of the same single process, so split-tolerance is an
  illusion of the K=5 gate.
- **The $10k candidate is the strongest cell at honest units too**
  (P(episode) 0.94, ex-top ret +0.45, n=160/thin) but its p5 is still −1.00.
- **The repo's falsification bar — episode-level P(>0) ≥ 0.80 — is FAILED
  by the shipped cell** (0.75 at the only interpretable gate, degenerate
  and uninterpretable at the mandated K=5). The $10k candidate clears it
  (0.94) but concentration risk is not resolved by the resize alone.
- The non-military control is NOT concentrated: 8 episodes, and
  episode-level P (0.89) does not collapse the way the military cell does,
  while its event-level P (0.70) already tells you it has no edge — unit
  inflation is a property of the military universe's shared professional
  speculators, which is why resampling granularity matters only where the
  edge is claimed.

## Lessons

1. **Consistent-unit principle**: dated rungs of one ladder = ONE sample, by
   data-derivation (account overlap), not by name-guessing. Any bootstrap
   claim must state its unit; event- vs unit-level P(>0) can differ by 0.23
   on the same tape.
2. **Any extension claim must now clear episode-level gates** — and they
   must be run at a documented K with the ground-truth check passing
   (`episodeResample.groundTruthCheck`: the iran-Feb-2026 reference set must
   occupy <3 episode groups; on this tape that holds well past the old
   K≤20 claim — the data-derived gate K* is the largest K in the fine
   sensitivity grid that still qualifies, printed by the script), including
   ex-top-episode stats: over-merge swings both ways and the world is
   bridged by professional multi-market accounts (9 accounts trade ≥20
   military slugs).
3. **Concentration from the account side**: 1,615/4,908 ≥$5k-burst accounts
   trade ≥2 military slugs; the military "category" edge and the
   multi-slug professional population are the same population. Treat
   category-level claims as process-level claims first.

## Caveats

- The K=5 gate is as-spec'd default; its over-merge (1 mega-episode) makes
  episode-level stats degenerate on this tape, published as such. The
  interpretable gate is K=20 with 12 episodes; any future K should be
  re-justified against the printed sensitivity table and ground truth.
- Episode-level and event-level point estimates are identical; only the
  distributional claims (P, p5, p95, ex-top) are resamplings of the unit.
- Event-level P/p5 come from entrySweep's own evaluator: its polars
  `group_by` row order feeds RNG indexing (`rng.randrange` over the event
  list), so event-level digits used to drift with row order — **measured
  ~±0.04–0.08 on p5 across runs** (an earlier version of this paragraph
  said ~±0.01: wrong; the episode-level column was never affected). Fixed
  here: `evaluate` now sorts the event table on a stable key (`eventSlug`)
  before the RNG consumes it, so **both levels are deterministic** and the
  published digits are reproducible to the last digit.
- Fills keep arriving; these numbers re-baseline the shipped cell as of the
  `entries_v2_df8efad228` cache built from `[data, data/universe]` on
  2026-10-15 (cell n=431 vs the review's 434 — drift, same shape), and
  should be re-run after tape growth.
- Hindsight detection on the fill tape as before (ages are lower bounds,
  order-book sizing not modeled).
