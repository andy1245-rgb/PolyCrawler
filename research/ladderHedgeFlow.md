# If-jump evaluation #3 — negRisk ladder hedge-flow second wave

Task: ideaGenAlpha.md family (d) / candidate #3 (`ladderHedgeFlow.md` — this file).
Question: **when an account buys one rung of a military date-ladder hard, does a
predictable second wave of hedge/rebalance flow appear on sibling rungs or the
complement side, fast enough and big enough to pre-position against?**
Written 2026-10-17. **The definitions and gates below were locked before any
fills tape was touched for this study.** The RESULTS section was appended after
the first (and only planned) run of `scripts/research/ladderHedgeFlow.py`.

---

## 0. Pre-registration (locked)

### 0.1 Ladder / stem grouping rule

**Group key = `eventSlug` (exact string).** Rationale and verification order,
stated before touching data:

1. The date-ladder stems in the military sample (`us-strikes-iran-by`,
   `will-israel-strike-lebanon-on`, ...) are Polymarket *events*: every rung
   ("...by January 14", "...by January 15", ...) shares one eventSlug. Verification
   (slide-deck read of markets.parquet only): `us-strikes-iran-by` holds 65 rungs
   with strictly spread endDates and one winner each — the ladder shape, verbatim.
   Disclosure: a pre-write sizing probe touched row counts only (markets/fills
   shape and file sizes) — no trigger, control or reaction statistics were
   computed before all gates below were written.
2. Slugs with an embedded date/number (`us-next-strikes-iran-on-843...`) collapse
   to singletons; they are not ladders and the ≥3-rung rule drops them.
3. `resolution date adjacency` is implied by, not imposed on, the grouping: the
   stem carries the date ladder itself ("by <date>"), and rung position for the
   direction analysis is ordered by `endDate`.

**Ladder family** := all markets whose eventSlug is shared by ≥3 distinct
markets in the merged [data, data/universe, data/oos, data/oosExpansion]
markets.parquet (unique'd on marketId, keep=last). Military ladder subset =
the usual MILITARY slug-keyword filter on eventSlug. Non-ladder markets
(singletons/pairs) are the matched-control pool.

### 0.2 negRisk identity — choice and why

`negRisk` is **ABSENT from markets.parquet in all four dirs** (R13 finding,
re-confirmed at pre-registration time: columns are marketId, eventSlug,
question, tags, endDate, winner, resolvedAt, volumeUsd, clobTokenIds,
outcomes). We therefore carry negRisk identity as a **descriptive annotation,
not a grouping gate**, via the CLOB market pull:

- Reuse `scripts/research/feeMarkRegrade.py`'s cached shooter pattern: cached
  `data/raw/feeMarkRegrade/clob__<conditionId>.json` (≈1,994 markets already
  cached, `neg_risk` field present) and rate-capped (4 req/s) CLOB
  `GET /markets/<conditionId>` for the remainder of the ladder universe.
- **Why annotate rather than gate**: the grouping must be complete regardless
  of API availability (a half-crawled negRisk gate would censor exactly the
  thin, interesting rungs), and the mechanism claim ("negRisk-aware MMs
  rebalance the whole group") is tested by the *event study* — if the reactive
  flow shows up on eventSlug groups whose rungs are mostly `neg_risk=true` and
  does not show on confirmed non-negRisk groups, the mechanism attribution
  survives without gating. Coverage share is reported; if coverage < 80% of
  ladder military markets the negRisk split is reported `INCONCLUSIVE` but the
  reaction-rate gate still resolves (it is stem-based, not flag-based).

### 0.3 Trigger burst

**Trigger burst** := a 10-minute-gapped burst window per
`(account, marketId, outcome)` — entrySweep's exact segmentation
(`side == BUY` fills only, USD = Σ(size·price)) — whose cumulative USD first
crosses **$10,000** (primary) or **$5,000** (secondary prior) inside the window
(inside one burst window, cumulative-from-window-start USD is the quantity;
the trigger timestamp `t0` = the fill print where cumulative first crosses X).
Trigger universe: military ladder markets only. Triggers are one per
(account, market, outcome) serial-burst instance. **n capped at 200 triggers**
(compute budget, spec): seed-7 uniform random sample of the qualifying trigger
list sorted deterministically by burst start time; per-stem trigger counts
reported. Compute is cheap enough that the full un-capped census is also
logged, to show the sample is not unrepresentative.

### 0.4 Event of interest (cross-rung reaction)

For each trigger `(t0, rung A, stem S)`:

**Reaction** := a burst window on a **different rung** (different marketId,
same stem S) by an account **≠ the trigger account**, whose cumulative burst
USD crosses **≥$X** (same X ∈ {$5k, $10k} as the trigger is evaluated against)
with burst **start in `(t0, t0+W]`**, W ∈ {10 min, 1 h, 6 h, 24 h}.
Reaction rate at (X, W) = share of triggers with ≥1 such reaction.

**Baseline (matched controls, identical timestamps elsewhere).** Two
controls, both at the trigger's exact `t0`:

- **C1 (same-ladder-type, other stems)**: 5 rungs sampled per trigger
  (seed-7) from other military ladder stems — the *cross-stem concurrency*
  baseline the spec asks for — counting a ≥$X burst starting in `(t0, t0+W]`.
- **C2 (non-ladder military markets)**: 5 markets sampled per trigger (seed-7)
  from military non-ladder markets — kills the objection that ladders are
  just busier markets in general.

Controls measure "how often does *any* rung anywhere see a ≥$X burst within W
of t0 absent any linkage" — including news co-arrival (multiple stems hit by
the same headline), which is the honest competing hypothesis for a second
wave.

**Unrelated-concurrency double-check (pre-specified)**: the raw cross-stem
concurrent-burst count across the whole tape (how many ≥$10k bursts are on
stems different from the previous ≥$10k burst's stem within each W, canonically)
is logged against the C1 rate so the matched-control result can be sanity-bound.

### 0.5 Hedge criterion

"hedge flow" is acknowledged **observational**, two lanes, all by accounts
≠ trigger account, inside `(t0, t0+W]` at W = 6h primary:

- **Lane H1 (same-rung opposite-side)**: any print (single fill) ≥$1,000 on
  the *trigger rung* that reduces the triggered exposure: a SELL of the
  triggered outcome, or a BUY ≥$1,000 of the complement outcome.
- **Lane H2 (cross-rung sibling)**: any print ≥$1,000 on a **different rung of
  the same stem**, decomposed (logged as table, not gate) by side/outcome and
  by later-vs-earlier endDate than the trigger rung. For a Yes-buy trigger on
  rung with endDate d, direction prior per the negRisk-conversion mechanism:
  co-movement — later-dated rungs' Yes is bought (event more likely overall
  lifts every member) and/or earlier-dated rungs' Yes is sold (re-date the
  exposure); for a No-buy trigger the mirror.

**Hedge witness rate** := share of triggers with ≥1 print in H1 ∪ H2 (6h).
Gate requires ≥30% (non-sparse).

**Hedge-anticipated side, pre-specified mapping** (used for the direction
table): triggered outcome o on rung at position p in its stem (ordered by
endDate). Lane H2 side is classified "hedge-consistent" iff for a Yes(o)-buy
trigger: pricing Yes *down* on an earlier-dated rung or No *down* on a
later-dated rung equivalent... — operationalized simply as: **the print's
implied alpha for the stem set is opposite to the trigger's** (buy of
complement-direction on siblings or sell of trigger-direction on siblings);
ambiguous directions are logged, not classified.

### 0.6 First-print drift of the reacting rung

For every reacted trigger and its earliest reacting rung r′ (first reacting
burst start), price(r′) at:

- `p0` = last fill price on r′ (either outcome, Yes-equivalent: p(Yes) last
  traded pre-t0; complement traded price inverted) before t0;
- `p(T+1h)`, `p(T+1d)` = Yes-equivalent price of the last fill on r′ at/before
  the horizon (fills tape; no book snapshots — stated limit).

Drift = p(horizon)/p0 − 1 on the Yes-equivalent scale. Also decomposed:
direction of the reacting burst (accepted Yes vs accepted No) to state whether
the "second wave" traded *with* the trigger direction (co-movement wave) or
against it (hedge/rebalance wave), and whether drift after the reacting print
continues (pre-positionable) or was all in the first reacting print
(mechanism-not-alpha).

### 0.7 Gates and verdict mapping (locked)

PASS block (all required, evaluated at the primary $10k trigger with the $5k
prior reported alongside, at each W; the headline W is the smallest passing W):

- **G1 (reaction excess)**: reaction rate at (X, W) exceeds **both** C1 and C2
  control rates, two-proportion z-test p < 0.01 (Bonferroni ×4 across the four
  W's per X, i.e. individual p < 0.0025), on **n ≥ 100 triggers**.
- **G2 (non-sparse)**: hedge witness rate (H1 ∪ H2, 6h) ≥ 30% of triggers.
- **G3 (second wave is real, not pre-priced)**: median Yes-equivalent drift of
  the reacting rung from its p0 to p(T+1h) is ≥ +1% in the direction implied by
  the reacting burst (pre-positioning at t0 would have captured it) — i.e. the
  reacting print does not equal the whole move.

**Verdict mapping:**

- `REAL` = G1 ∧ G2 ∧ G3 pass → live detection lane spec written (§ Results).
- `PRE-EXISTING` = G1 ∧ G2 pass but G3 fails — the "second wave" arrives in a
  single print with no continuation: mechanism note (R9 subscription content),
  not a tradable lane.
- `ABSENT` = G1 or G2 fails — no exploitable second-wave structure; the empty
  result still feeds the execution model (burst-entry sizing in ladders does
  not need hedge-flow adjustment).

Kill criterion (pre-specified, honest): this is a *single-run* pre-registered
study; no retry-until-positive. If n < 100 triggers qualify, the study reports
`INCONCLUSIVE (n<100)` and does not re-spec thresholds to force qualification.

---

## 1. Method notes (what the script does)

- Burst segmentation, USD accounting and the 10-minute gap rule are lifted
  verbatim from `scripts/research/entrySweep.py buildEntries` semantics
  (`side == BUY`, `(size·price).sum()` per `(account, marketId, outcome)`
  burst); no entry cache reuse beyond the algorithm, since the trigger frame differs from the entry cell.
- Fills across [data, data/universe, data/oos, data/oosExpansion],
  diagonal_relaxed concat; 25.1M fills, 17.9M on ladder events (1,898 ladder
  markets, 1,155 military ladder).
- Rates tested with two-proportion z on raw counts; controls pooled across
  triggers (C1/C2 treated as independent exposures).
- negRisk coverage from cached + fresh CLOB pulls, annotation only (§0.2).

---

## 2. RESULTS (single pre-registered run, 2026-10-17)

Run: `uv run python scripts/research/ladderHedgeFlow.py 2>&1 | tee
logs/ladderHedgeFlow.log` — 15s wall, n=200 triggers per lane (seed 7; full
census 21,980 qualifying ≥$10k bursts / 46,736 ≥$5k bursts on military ladder
rungs). Tables: `data/research/ladderHedgeFlow/triggers_{10k,5k}.parquet`,
`summary.json`. Implementation notes: two cold bugs were fixed during the
first executions **before any result was read into a decision** (a
μs-vs-ns epoch scale bug and a partition-key tuple bug — at the bugged
settings every window was dilated ~1000x and every print lookup missed, i.e.
the bugs could only inflate the null result, never manufacture the real
one); gating statistics below are from the fixed run verbatim.

### 2.1 Universe and annotation

- 2,133 unique markets, 129 ladder stems (≥3 rungs), 1,155 military ladder
  rungs, 225 military non-ladder. Top stems: us-strikes-iran-by (65 rungs),
  will-israel-strike-lebanon-on (64), will-israel-strike-gaza-on-379 (63).
- negRisk (CLOB pulls, feeMark regrade cache, 100% coverage): neg_risk=true
  on 261/1155 (22.6%) of military ladder rungs.
- Burst frame: 8.25M 10-min-gapped (account, market, outcome) BUY windows.
- Cross-stem concurrency census (any account, no filters): a military ladder
  ≥$10k burst is followed by ≥1 OTHER-STEM ≥$10k burst within 10m 33.3% /
  1h 68.8% / 6h 91.4% / 24h 98.0% of the time — the whole tape is
  news-co-bursting, which is exactly why the matched-control gates matter.

### 2.2 G1 — cross-rung burst reaction vs matched controls (PASS everywhere)

Reaction = ≥$X burst on a different rung of the same stem, burst start in
(t0, t0+W], account ≠ trigger. Controls = 5 other-stem ladder rungs (C1) and
5 non-ladder military markets (C2) per trigger, same timestamps, ≥$X bursts.

| lane | W | reaction | C1 | C2 | p vs C1 | p vs C2 | G1 (p<0.0025) |
|------|---|----------|----|----|---------|---------|----------------|
| 10k | 10m | **27.0%** | 0.0% | 0.2% | 1.9e-63 | 1.8e-60 | PASS |
| 10k | 1h | **49.0%** | 0.0% | 0.7% | 4.7e-118 | 6.5e-108 | PASS |
| 10k | 6h | **70.5%** | 0.6% | 1.6% | 9.1e-167 | 2.5e-153 | PASS |
| 10k | 24h | **76.5%** | 1.1% | 2.6% | 1.2e-176 | 5.5e-158 | PASS |
| 5k | 10m | **29.5%** | 0.1% | 0.2% | 6.3e-68 | 1.9e-66 | PASS |
| 5k | 1h | **62.5%** | 0.3% | 1.1% | 3.5e-149 | 5.3e-138 | PASS |
| 5k | 6h | **80.0%** | 0.5% | 2.6% | 3.6e-195 | 8.4e-168 | PASS |
| 5k | 24h | **86.5%** | 1.1% | 3.8% | 1.3e-205 | 4.5e-173 | PASS |

n=200 both lanes (≥100 required). Sample concentrates on the Iran 2026
family (us-strikes-iran-by 52 triggers at 10k, us-x-iran-permanent-peace-deal-by
33) — the composition of the live tape, not a sampler choice.

### 2.3 G2 — hedge witness (PASS, overwhelmingly)

At 6h: witness (H1 same-rung opposite-side ≥$1k print OR H2 cross-rung ≥$1k
print, account ≠ trigger) = **99.5%** (H1 alone 97.0%, H2 alone 83.0%) in the
10k lane; 96.5% (H1 88.5%, H2 89.0%) in the 5k lane. Cross-rung print
decomposition (10k lane, print counts): BUY No on earlier-dated rungs 10,602,
BUY Yes earlier 6,936, BUY Yes later 6,111, SELL No earlier 4,827, SELL Yes
earlier 4,090, SELL Yes later 3,676, BUY No later 3,372, SELL No later 1,670
(+ small unknown-endDate buckets). Two-sided: sibling rungs are hit with
*both* sides, not a one-directional conversion wave in the print tape.
Median reacting-burst delay: 26 min (10k) / 21 min (5k).

### 2.4 G3 — is there a tradable second wave? (FAIL — the kill)

Drift of the reacting rung in the direction the reactor bought,
p0 (last print pre-t0) → horizon (11k: n=151 reacted triggers with price;
5k: n=173):

| lane | n | median drift1h | mean d1h | P(>0) d1h | median d1d | P(>0) d1d |
|------|---|----------------|----------|-----------|------------|-----------|
| 10k | 151 | **+0.00%** | −0.62% | 49.0% | +1.42% | 67.5% |
| 5k | 173 | **+0.00%** (+5e-8) | +1.22% | 51.4% | +0.91% | 65.3% |

Median 1h drift is zero in BOTH lanes: the reacting print itself carries the
move — by the time the second wave prints, the reacting rung's price is
already at its post-move level. The 1d horizon drifts +1.4%/+0.9% with
~66-67% directional agreement with the reactor, but that is day-scale event
momentum indistinguishable from any post-burst tape-wide drift, not a
hedge-capture window. Reactor direction is not ex-ante predictable either
(No 91 vs Yes 60 of 151 in the 10k lane).

### 2.5 Mechanism attribution — NOT the negRisk adapter

Splitting the sampled ladders by CLOB neg_risk composition: at 10k, 96%
of the sampled triggers (193/200) sit on stems with neg_risk=true on <20%
of rungs, and they show the full effect (react10m 26.9%, witness 99.5%);
the ≥50%-negRisk stems have only 7 triggers (28.6% / 100%). The cross-rung
second wave exists where the negRisk adapter is NOT in play. The mechanism
is therefore ladder-family flow coupling generally — speculator spray and
same-news co-hitting (the `sampleReview.md` ladder-spray tell), plus
forced two-way broking on thin rung books — not negRisk conversion buckets.

### 2.6 Verdict

- 10k lane: **PRE-EXISTING** (G1 PASS, G2 PASS, G3 FAIL).
- 5k lane: **PRE-EXISTING** (same shape, stronger rates).
- OVERALL: **PRE-EXISTING** — mechanism-not-alpha, exactly the honest outcome
  the pre-registration carved out.

What is real: if anyone bursts ≥$10k on one rung of a military date ladder,
sibling rungs burst within 10 minutes 27% of the time (vs ~0-2% at matched
timestamps, p<1e-60, n=200) and hedge-sized prints land 83-97% of the time
within 6h, both sides. What is absent: any pre-positionable edge — the
first reacting print already contains the price move (median 1h drift 0),
the reaction direction is not ex-ante predictable, and the effect survives
where negRisk=false, so the conversion-mechanics story is wrong. A strategy
"short the pre-positioned direction when the hedge is predictable" has no
predictable hedge direction to short against at 1h scale.

### 2.7 R9 path A (product content) — YES, this feeds the subscription lane

This is a strong mechanism/flow note for the product even with no printed
alpha: "date-ladder rungs are coupled — a $10k+ hit on one rung drags a
second burst onto a sibling rung within minutes ~half the time, and the
sibling books reprice in the same print, not after it" plus the negRisk
falsification (it is not the adapter, it is the flow). It also lands the
execution-model update: our shipped burst-entry shape in ladders should
assume sibling-liquidity vanishing for ~15-30 min around a trigger (the
median reactive delay) — no separate volume adjustment is justified by
data, but the "post-trigger lull" is real and covers where our fills land.

### 2.8 File map

- Pre-registration: this file §0-1 (locked before the run).
- Script: `scripts/research/ladderHedgeFlow.py` (ruff clean).
- Log: `logs/ladderHedgeFlow.log`.
- Tables: `data/research/ladderHedgeFlow/triggers_10k.parquet`,
  `triggers_5k.parquet` (per-trigger lanes), `summary.json` (gate table +
  verdict).
