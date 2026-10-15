# ops-extension FIRST LOOK (post-run, commit 3)

Pre-registration committed first (`294da07`), grounding second (`c096176`),
this first look third — the gate contract "`PnL analysis NEVER precedes the
committed keyword/config`" is honored. Evaluator:
`scripts/research/opsExtensionEval.py` (imports `entrySweep` internals via
importlib; NO copied cell logic; the only patches are the entry-build slug
table broadened to shipped ∪ extension and a cache-dir redirect out of the
read-only data tree). Data: full tape at `[data, data/universe]`,
2,461,639 entries built the same way the shipped sweep builds them.

## Metric definition (per pre-registration, incremental-only)

Every cell below is the **DELTA sample set**: entries matching an extension
keyword minus entries matched by the shipped 15. Sample accounting:
extension-matched 122,832 entries — of that, DELTA = 8,726 entries, all on
1 event / 1 episode (`us-anti-cartel-ground-operation-in-mexico-by-...`);
shipped-matched on the broadened build: 2,452,913 entries over the same
46 shipped events (behavior preservation check).

Cell shapes are the shipped grid's pre-registered corner
(`configs/sweeps/militaryEntryGrid.yaml` axes, live-rule shape 5000/0.35/5/3
and the §9 p5-floor 10000/0.35/5/3), fixed before the run.

## First-look table — DELTA cells (n below MIN_CELL(20) = null metrics by design, disclosed not pruned)

| minUsd | maxPrice | ageDays | mktsSoFar | n | ret | P(>0) | p5 | h1 | h2 | events | ep n | ep ret | ep P(>0) | ep p5 | ep h1 | ep h2 | LOEO ret | stressed ret | stressed P(>0) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 0.35 | 5 | 3 | 33 | **−1.000** | 0.000 | −1.000 | null* | −1.000 | 1 | 33 | −1.000 | 0.000 | −1.000 | null* | −1.000 | −1.000 | 0.000 |
| 1000 | 0.35 | 5 | 3 | 12† | null | null | null | — | — | — | 12† | null | null | null | — | — | — | null | null |
| 5000 | 0.35 | 5 | 3 | 0 | — | — | — | — | — | 0 | — | — | — | — | — | — | — | — | — |
| 10000 | 0.35 | 5 | 3 | 0 | — | — | — | — | — | 0 | — | — | — | — | — | — | — | — | — |

\* h1 (pre-2025-06-01 half) is null because the single episode's fills sit
entirely after the half split — nothing before it, nothing to report.
† n=12 < MIN_CELL(20): `entrySweep.evaluate` returns null metrics here
by design; shown for disclosure.

Per-episode disclosure (every episode, pass or fail): exactly one —
`us-anti-cartel-ground-operation-in-mexico`: n=33, ret −1.000,
P(>0) 0.000, p5 −1.000.

## Gate scorecard (pre-registered §3, no re-parameterization)

| gate | requirement | observed | verdict |
|---|---|---|---|
| G1 incremental breadth | ≥5 NEW events | 1 NEW event (grounding, c096176) | **FAIL** |
| G2 episode-level | ≥5 new episodes with P(>0) ≥ 0.90 (and ≥0.83 threshold reported) | 1 new episode, P(>0) 0.000 | **FAIL** |
| G3 ex-top-episode | leave-one-episode-out of largest group > 0 | leaves the empty set (only 1 episode) → unmeasurable | **FAIL** |
| G4 fee/slippage stress | mean delta ret > 0 at +10% one-way haircut | −1.000 | **FAIL** |
| G5 behavior preservation | shipped 15 matched set unchanged | 46 events / 2,452,913 entries on the broadened build, additivity asserted at grounding | PASS |

Verdict: **the pre-registered extension dies at its own gates — no
incremental surface on the fetched tape, and the one episode it does
surface is a 100% loss episode at every pre-registered cell.**

## DISCLOSED GAP (restated in every report, per pre-registration)

Per-category taker fee + 10% slippage stress: `fills.parquet` has **no fee
column**, and the shipped slippage model is a flat 50bps. Real per-category
fees cannot be reconstructed from the local tape, so G4's stress is a
one-way +10% (1000bps) haircut recomputation — here it changes nothing
because every delta outcome is already a full −100% loss.

## What this does and does not say

- It does NOT say the state-use-of-force mechanism memo is wrong: it says
  the fetched 94-event tape has no incremental surface for structural
  verbs beyond the shipped 15 (the invasion/capture/attack families on
  tape are already inside `russia`/`venezuela`/`taiwan`/`lebanon` …
  entity substrings), and the one genuinely unmatched ladder
  (Mexico cartel ground operation) resolved No.
- Anything else here would require the memo's pre-announced route: a PURE
  OOS fetch of never-fetched coup / martial-law / invasion-proposition
  ladders, with the shipped cells declared frozen BEFORE the run (the
  pre-registration's gates and this tuple, unchanged — no retuning).
- No ranking, no winners, no config change to the shipped filter. First
  look only; all tried cells disclosed including failures.
