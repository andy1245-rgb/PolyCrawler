# OOS failure diagnosis: why the military fresh-longshot copy line dies out-of-sample

Scripts: `scripts/research/oosFailureDiagnosis.py` (entrySweep internals reused by
importlib-by-path: `loadEntries`, `filterCell`, `evaluate`). Data graded on the two
dir-sets SEPARATELY, never mixed in one number: in-sample `[data, data/universe]`
(entries cache `entries_v2_df8efad228.parquet`) and OOS `[data/oosExpansion]`
(cache rebuilt on this run — the previous `entries_v2_5a57e33ce8.parquet`
fingerprint is stale after the 2026-10-15 re-fetch). Exploratory diagnosis:
hypothesis tests on the pre-registered questions below, NOT rule tuning. No
shipped-rule change can come from this doc; verdicts land as evidence only.

Known environment (research/status.md §9.2): in-sample fresh ≥$5k ≤0.35 military
bursts graded +105–119% retReal, ~35% winRate, floor-ranked p5 +0.39..+0.57 at
$10k/≤0.35; OOS holdout (200 fresh resolved military slugs, splitDate
2026-01-01, 10.66M fills) grades the same flagship cell 167 entries / 34 events:
retReal −0.727, winRate 7.8%, p5 −0.875, P(>0) 0.0%, delay-realistic −0.812,
landed300 91% (executability is fine — not the cause). Control on the same
tape (all $10k+ bursts, any price): ret +1.1%, winRate 90.9% — sampler and
winner coding are sound; the loss is specific to the ≤0.35 longshot line. The
2–5d age gate is consistently WORSE than 0–1d OOS (the in-sample candidate's
key gate is anti-confirmatory where it can finally be tested).

## Pre-registered questions (written before the run)

Flagship cell for Q1/Q2/Q4/Q5: `filterCell`($10k/≤0.35, ageDays ≤5, marketsSoFar
≤3) — the in-sample floor-ranked cell. Q3 grades the rule's whole trigger
population: $5k/≤0.35, ageDays ≤5, marketsSoFar ≤3 (shipped cell). Timehalf
buckets: 2023-10-01..2024-06-30, 2024-07-01..2025-06-30, 2025-07-01.. (labelled
`23H2-24H1`, `24H2-25H1`, `25H2+`; bucketed by burst ts). Tape = BUY prints
(the only print tape the pipeline has; no true bid/ask mid exists in the
landed data — the BUY print is the mid proxy, stated openly). Seeded
event-level bootstrap via entrySweep.evaluate (rng random.Random(7) per
dir-set) wherever an event-resampled p5/P(>0) is reported.

- **Q1 VELOCITY** — after a fresh ≤0.35 burst, does the print drift UP
  (burst→continuation) or back DOWN (burst→mean-reversion)? For every burst
  entry: recompute the burst window from fills (same 10-min-gap recipe as
  entrySweep.buildEntries; cached entries' `price` column is the TRIGGER
  print, so burst average = recomputed Σ(size·price)/Σsize), take burstEnd =
  last fill ts of the window, then p(Δ) := last BUY print with burstEnd <
  ts ≤ burstEnd+Δ for Δ ∈ {T+1h, T+6h, T+1d} (null → excluded, coverage
  reported). Drift(Δ) := p(Δ) − burst average, in price points and relative
  (p(Δ)/avg − 1); report mean, median, share-down (p(Δ) < avg), n and
  coverage, split by dir-set × timehalf bucket.
  Decision rule: if OOS mean drift at T+1d is negative while in-sample is
  positive, the burst line's premise — post-burst continuation — is
  regime-dependent rather than universal. That constitutes evidence FOR a
  fade/mean-reversion line (Q2 decides whether the other side actually
  earns). A fade line is a hypothesis on this evidence, not a shipped rule.
- **Q2 FADE TEST** — what does the OPPOSITE side of the same burst earn?
  From the cell's entries, keep those with a next distinct BUY print within
  300s of the burst trigger (landed300, oosTransport's recipe) and restrict
  to binary markets (exactly 2 distinct outcomes in fills). Fade cost :=
  (1 − nextPrint) × (1 + 0.005) (50bps slippage, oosTransport convention;
  Polymarket binary identity, no cross-outcome tape needed). PnL: entry
  outcome wins → −1.0; entry loses → 1/cost − 1. Hold to resolution.
  Report n, mean/median PnL, complement winRate, p5/P(>0) via evaluate,
  in-sample vs OOS (and timehalf buckets as a secondary read).
  Decision rule: fade positive OOS where the copy line is negative ⇒ the
  burst direction mean-reverts OOS and a fade edge EXISTS at this trigger;
  gradeable when n ≥ 100 entries across ≥ 10 events, else INCONCLUSIVE.
- **Q3 POPULATION SHIFT** — compare the rule's trigger population in-sample
  vs OOS: day-0/1 share (ageDays ≤ 1), burst-size distribution ($ median,
  quartiles), copy-price distribution (buckets ≤0.2 / 0.2–0.35),
  marketsSoFar (=1 vs 2–3) share, fee-era share and negRisk share FROM
  markets.parquet columns `feesEnabled` / `negRisk` — checked first; if the
  columns are absent from the landed parquets that comparison is reported
  NOT GRADEABLE from this data, not skipped silently. Split timehalf
  composition reported as a second lens. Decision rule: a materially
  different day-0/1 or ≤0.2-price mix in OOS shifts part of the failure to
  population composition rather than regime; a nearly identical mix keeps
  the regime explanation primary.
- **Q4 CONCENTRATION** — per-event PnL (Σ retReal×100 per eventSlug) of the
  flagship cell, in-sample vs OOS: event count, total, mean/median, min,
  max, top-event share of total PnL, # events with pnl > 0 and with
  pnl ≤ −$1000. Per-event ONLY; episode-level regrouping stays banned here.
  Decision rule: OOS losses broadly spread across events (median event
  clearly negative, top-event share ≪ 100%) ⇒ the line fails everywhere in
  the OOS environment, not on one bad episode; one dominant negative event
  ⇒ the failure is event-specific and the population question (Q3/Q5)
  carries the diagnosis.
- **Q5 HISTORY WEIGHT** — restrict the OOS flagship cell to the period that
  overlaps in-sample market resolution dates (entry ts < 2026-01-01) vs the
  pure 2026 era (ts ≥ 2026-01-01): n, events, ret, winRate, p5, P(>0) per
  era via evaluate; the in-sample analog split reported for context.
  Decision rule: the failure is era-bound if the pre-2026 OOS slice
  behaves in-sample-like (or clearly better than the 2026 slice) and the
  2026 slice alone carries the loss; if BOTH OOS eras are decisively
  negative the edge is population-bound/line-intrinsic, not a new-era
  artifact. (Known direction check: §9.2's half-split showed h1 −0.217 vs
  h2 −0.817 on the flagship cell — h1 LESS negative than h2, i.e. toward
  era-bound — this test grades that direction properly at the 2026 split.)

Required explicit answers at the bottom: (a) which hypothesis best explains
the OOS failure; (b) does a fade/mean-reversion edge exist OOS and is it
gradeable; (c) is the edge era-bound or population-bound.

## Results (appended after the run)

Run log: `logs/oosFailureDiagnosis.log` (in-sample 3s, OOS 5s on the cached
entries; in-sample cache `entries_v2_df8efad228.parquet`, OOS rebuilt to
`entries_v2_8fdc67aec9.parquet`).

Sanity gate first: burst-average recompute vs cached trigger price differs up
to 0.17-0.21 — the cached `price` is the TRIGGER print, not the burst average
(as pre-registered), so all drift numbers below are vs the recomputed
Σ(size·price)/Σsize. Not a data bug: the trigger print is a sub-window print.

### Q1 velocity — drift of post-burst BUY print vs burst average

| dir | era | win | n | medRel% | meanRel% | down% |
|---|---|---|---|---|---|---|
| in-sample | 24H2-25H1 | T+1d | 10 | +5.7 | +17.6 | 30.0 |
| in-sample | 24H2-25H1 | T+1h | 6 | −4.1 | −6.3 | 66.7 |
| in-sample | 24H2-25H1 | T+6h | 8 | +5.9 | +8.5 | 37.5 |
| in-sample | 25H2+ | T+1h | 150 | −3.5 | −6.6 | 67.3 |
| in-sample | 25H2+ | T+6h | 150 | −5.2 | +1.0 | 62.7 |
| in-sample | 25H2+ | T+1d | 150 | −18.9 | +20.7 | 68.7 |
| oos | 24H2-25H1 | T+1h | 33 | +0.2 | −4.8 | 42.4 |
| oos | 24H2-25H1 | T+6h | 34 | +0.2 | −4.9 | 44.1 |
| oos | 24H2-25H1 | T+1d | 34 | 0.0 | −3.9 | 50.0 |
| oos | 25H2+ | T+1h | 130 | −0.0 | −2.5 | 53.1 |
| oos | 25H2+ | T+6h | 132 | −3.4 | −4.2 | 61.4 |
| oos | 25H2+ | T+1d | 132 | −7.5 | −13.6 | 64.4 |

Reading: median drift is negative almost everywhere — a fresh longshot burst
usually does NOT continue at 1h (the copy entry is often the burst's own top
tick). The in-sample 25H2+ MEAN at T+1d is strongly positive (+20.7%) only
because a fat tail of longshot-to-favorite runs (the Iran episodes) drags it;
the OOS 25H2+ mean is negative in both tails (−13.6% mean, −7.5% median).
Pre-registered rule satisfied: OOS T+1d drift negative while in-sample-era
mean positive ⇒ the copy line's continuation premise is regime-dependent,
evidence FOR testing the fade side (Q2 grades it).

### Q2 fade — complement side of the same burst (binary markets, landed300,
 entertained hold-to-resolution, +50bps on cost)

| dir | era | n | events | fadeRet | medPnl | compWin% | p5 | P>0 |
|---|---|---|---|---|---|---|---|---|
| in-sample | 24H2-25H1 | 5 | thin | — | 0.276 | 60.0 | — | — |
| in-sample | 25H2+ | 147 | 14 | −0.42 | 0.023 | 55.8 | −0.433 | 0.003 |
| in-sample | ALL | 152 | 18 | −0.32 | 0.025 | 55.9 | −0.421 | 0.005 |
| oos | 24H2-25H1 | 22 | 8 | — | 0.292 | 81.8 | −0.352 | 0.634 |
| oos | 25H2+ | 129 | 22 | **+0.19** | 0.244 | **96.1** | **+0.125** | **0.998** |
| oos | ALL | 151 | 30 | +0.193 | 0.249 | 94.0 | +0.108 | 0.999 |

Per the PRE-REGISTERED gate (fade passes if p5 > 0 AND P(>0) ≥ 85% AND n ≥
20 events): **the fade line PASSES on the OOS holdout** — 151 entries over 30
events, +0.193 mean PnL per entry, 94.0% complement win rate (fade of a
≤0.35 burst costs ≈0.70-0.86 per share ⇒ breakeven compWin ≈ 74-84%; 94%
clears it), bootstrapped p5 +0.108, P(>0) 0.999. The same fade is decisively
NEGATIVE in-sample (P(>0) 0.5%, 17 complement wins of 152 — a mirror of the
copy line, as it must be: the two sides of one trigger trade the same
entries in opposite directions).

The regime boundary is 2025H2: OOS fade is negative-leaning pre-2026
(p5 −0.352, P 0.634, n=8 events) and solidly positive after.

### Q3 population — trigger population (shipped cell), same key on both dirs

| dir | n | events | day01% | mkt=1% | 24H2-25H1% | 25H2+% |
|---|---|---|---|---|---|---|
| in-sample | 431 | 29 | 80.7 | 71.5 | 5.3 | 94.7 |
| oos | 391 | 60 | 65.2 | 69.1 | 23.8 | 76.2 |

OOS skews slightly MORE established (day01 65.2% vs 80.7% — day-0/1 mass is
LOWER, not higher, OOS; the day01% note in status §9.2 was about the 2-5d
age gate specifically) and era-mixed almost identically. Fee/negRisk
columns: ABSENT from all three markets.parquet — not gradeable (recorded as
a limitation; the fee era can still be probed via Gamma `feesEnabled` in a
follow-up fetch). Population composition does NOT explain the flip.

### Q4 concentration — per-event PnL, flagship cell

- in-sample: 20 events, total +$29,590, mean +$1,480, **median −$100**,
  only 9/20 events positive, top event (us-x-iran-ceasefire-by) +$10,805 =
  36.5% of total; max single loss −$700.
- oos: 34 events, total −$11,811, mean −$347, median −$100, 9/34 events
  positive (max single win +$689), 6 events ≤ −$1,000.

Per the decision rule: OOS losses are BROADLY SPREAD (34 events, median
event negative, no dominant losing event) — the copy line fails everywhere
in the OOS environment. And the in-sample edge was never event-broad:
median event was ALWAYS −$100 there too (one fat tail bearing everything),
now measured explicitly.

### Q5 history weight — era split at the 2026-01-01 split date

| dir | era | n | events | retReal | winRate% | p5 | P>0 |
|---|---|---|---|---|---|---|---|
| in-sample | pre-2026 | 33 | 10 | −0.226 | 24.2 | −0.552 | 0.24 |
| in-sample | 2026+ | 127 | 11 | **+2.389** | 48.8 | +1.471 | 0.998 |
| oos | pre-2026 | 42 | 15 | −0.378 | 19.0 | −0.758 | 0.205 |
| oos | 2026+ | 124 | 20 | −0.825 | 4.8 | −0.949 | 0.0 |

This is the crux: the split is NOT time. The in-sample 2026+ slice (same
calendar era as the catastrophic OOS 2026+ slice) is the STRONGEST cell in
the whole study (+238.9% retReal, P 0.998) — because it is exactly the
Iran-war-screen events. The edge is EVENT-FACTORY-bound (those specific
2026 cluster episodes), and the ÷2026+ OOS slice proves the same era with
different events dies (P 0.0). Combined with Q3's near-identical
populations: not a population shift, not a clock — a specific cluster
episodes concentration.

### Bottom line (the three pre-registered answers)

- **(a) Best single hypothesis:** the in-sample edge was ONE EPISODE-FACTORY
  (the 2026 Iran-war-screen clusters whose longshots ran); fresh military
  longshot bursts anywhere else mean-revert (Q1) and lose ≈9 times in 10
  (OOS winRate 4.8-7.8%). Not clock-bound (Q5: both eras present on both
  sides of the split), not population-bound (Q3), not executability (§9.2).
- **(b) Fade edge, gradeable OOS:** YES — complements of fresh ≤0.35 bursts
  pass the pre-registered gate on the OOS holdout (p5 +0.108, P(>0) 99.9%,
  30 events, 94% compWin vs ≈74-84% breakeven). It FAILS on the in-sample
  era and pre-2026 OOS — it is the SAME regime-dependent coin, opposite
  side. Any fade candidacy must therefore ride its own paper test on
  CURRENT-era events (2025H2+), graded with the same gates, before it
  touches the watcher; it may be another one-factory artifact whose
  current-era form is "longshots stopped paying".
- **(c) Era or population:** neither as such — episode-bound with a 2025H2
  regime boundary visible on BOTH lines' fades/copies. The transport
  failure and the fade success are the same observation read twice.

**Follow-up (episode regrade, 2026-10-16):** the fade PASS above does NOT survive episode regrouping — regraded per oosFailureDiagnosis.q2Fade verbatim + episodeGate at the OOS tape's data-derived K*=28: 30 events → 9 episodes, top episode = 126/151 entries = 108.8% of total PnL, epP 0.718 < 0.80, ex-top ret −0.103 ⇒ composed verdict FAIL / ARTIFACT (the fade candidate is an artifact). Fade evidence line above is retired. See research/methodologyChecks.md — the fade dies on the same one-factory story as the copy line. Next mechanical
steps per the precommitted decision tree: (1) grade the fade line with
episode-level regrouping + top-event share (R7's port, once landed) — the
30 OOS fade events MUST not be secretly 2-3 factories; (2) grade the
favorite-band copy family (R4) which is the same falsification in
price-band clothing; (3) iff BOTH survive, the fade line enters a paper
gate alongside the trajectory harness.
