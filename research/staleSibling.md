# Stale-sibling residual sweep on the ladder tapes (pre-registered)

Script: `scripts/research/staleSiblingSweep.py`. Companion to
`research/ideaGenAlpha.md` §3(a)/§3(i) and idea #5 (expect-kill probe).

**Pre-registration written 2026-10-17, BEFORE the script was written and
BEFORE any sweep ran.** Nothing below was tuned on observed outputs; the only
data touches before this run were structural queries (schemas, slug-phrasing
census, one causality sanity check) listed in §7.

---

## 1. Question (restated from ideaGenAlpha #5)

When one rung of a date-ladder stem resolves (YES or NO), the scoreboard
event implies — by ladder arithmetic — what the other rungs of the same stem
must be worth. Do the sibling rungs keep trading at mechanically impossible
prices (mismatch > threshold) for a long-enough, liquid-enough window that a
taker entering only after **our stack's 300–600 s resolution delay** could
capture profit net of fees? Expected answer per the idea list is **NO-GO**
(external evidence: negRisk arb persistence median ~1 min, ~2.7 s collapse
for internet-visible mismatches, vs. our ≥300 s delay). The measured
decay-curve/half-life table is the deliverable either way; it also feeds the
R9 product-content note (§9).

## 2. Data scope (all-reuse; no src edits)

- Markets: `data/markets.parquet`, `data/universe/markets.parquet`,
  `data/oos/markets.parquet`, `data/oosExpansion/markets.parquet`,
  concatenated and deduped on `marketId` keeping the dedupe-priority row with
  a non-null `winner` (dir order: data, data/universe, data/oos,
  data/oosExpansion — first non-null winner wins). Only markets with
  `winner ∈ {Yes, No}` and non-null `resolvedAt` are eligible as triggers.
- Fills tape: same four dirs' `fills.parquet`, selected to the marketId set
  of the merged markets, deduped on
  (txHash, marketId, outcome, side, size, price, ts) — the fetch dedupe keys
  minus `account` (account is not used by this analysis).
- No network, no chain calls, no new dependencies, no `src/` edits.

## 3. Stem grouping rule (independent of any other project's file)

A **stem** is derived from the normalized `question` text, not the slug:

- Normalize: lowercase, collapse internal whitespace. An acronym `(et)`/
  `(ET)` timezone note is stripped before pattern matching (kept only for the
  checklist honesty below — `ET` markings do NOT change rung-date parsing).
- **Rung date**: parsed from the trailing date clause of the question:
  - month name from the fixed list (january…december) + day number, with an
    optional trailing 4-digit year and an optional `(ET)` suffix;
  - patterns accepted: `... by <Month> <D>[, <Yy>?]...` (class N) and
    `... on <Month> <D>[, <year>?]...` (classes E/I);
  - explicit year in the question is authoritative; otherwise the rung
    date's year is chosen from {resolvedAt year, resolvedAt year − 1}: the
    candidate that minimizes |resolvedAt − rungDate| subject to
    rungDate ≤ resolvedAt + 1 day; ties → earlier candidate;
  - rungs whose question month/day order differs (e.g. "ordinals") that the
    regex cannot parse are counted per class as unparsed and dropped from
    the implication census (reported in the census table).
- **Stem key** = question text with the trailing date phrase and the
  preceding connector (`by`/`on`, plus surrounding punctuation and optional
  ET note) removed, whitespace-collapsed. Rungs of the same stem may live in
  different `eventSlug`s (Polymarket re-windows these families with
  `-928`/`-522`/`-379`-style slug suffixes) — that is exactly the "derived
  ladders" case; they are siblings across slugs of one stem but keep their
  own resolution clocks.
- **Stem class** (a priori, from the connector word, before any data):
  - **Class N (nested, "by <Month> <D>")**: at most one rung is resolved
    independently per date, and the underlying question is cumulative
    ("X ends by date D"). Implication is order-nested (§4).
  - **Class E (exclusive "next"/"first", question contains the word
    next or first before the `on <Month> <D>` clause)**: at most one rung in
    the underlying family can ever resolve Yes (the *next*/first occurrence
    happens once). Implication is mutual exclusion (§4).
  - **Class I (independent "on <Month> <D>", no next/first token)**: rungs
    are per-day independent events (e.g. "Will Israel strike Lebanon on
    November 28?"). Empirically these families routinely resolve multiple
    rungs Yes (census on this tape confirms), so a YES/NO on one rung
    implies NOTHING about the siblings by ladder arithmetic. Class I is
    reported in the census but carries no residuals.

## 4. Residual definition (implied arithmetic, pre-registered)

For a trigger rung g with winner w and resolvedAt T:

- **Class N (stem gate: nesting monotonicity)** — a stem's implication rules
  apply only if the stem passes the empirical gate: among rungs of the stem
  belonging to a single,
  fully-resolved eventSlug (all rungs carry a winner), the winner string as a
  function of rungDate is monotone (Yes always below No in rungDate order:
  rungDate_1 < rungDate_2 ⇒ winner_1=Yes ⇒ winner_2=Yes, and
  winner_2=No ⇒ winner_1=No). A stem that passes for ANY fully resolved slug
  is gated-in for that slug; implications are nevertheless computed only
  within gated stems. Implications:
  - w=Yes on rungDate d ⇒ every sibling rung of the same stem with
    rungDate ≥ d and (own resolvedAt > T or unresolved) has **implied Yes
    price 1.00**.
  - w=No on rungDate d ⇒ every sibling rung with rungDate ≤ d and
    (own resolvedAt > T or unresolved) has **implied Yes price 0.00**.
- **Class E (stem gate: per-slug exclusivity + cross-slug liveness)** —
  implications apply only if the trigger's own eventSlug is empirically
  exclusive: among its fully resolved rungs, at most one is Yes, and it has
  ≥ 3 rungs. Implications:
  - w=Yes ⇒ every sibling rung of the same eventSlug (rungDate ≠ d) and
    additionally same-stem different-slug rungs with rungDate > d **whose
    market printed at least one trade BEFORE T** (liveness evidence — the
    derived window existed when the trigger resolved, so its rung was
    actually sellable/buyable in the same market the family used),
    with (own resolvedAt > T or unresolved), has **implied Yes price 0.00**.
  - w=No ⇒ no implication (a single No carry leaves the next-occurrence
    date undetermined). Class-E No-resolutions are counted as triggers but
    generate zero sibling cells.
- **Sibling cell** = (triggerId, siblingMarketId, implied Yes price).
  Cells with implied 0 are `implied0`; the mismatch direction is
  *sellable-Yes* (a taker could sell/have sold the sibling's Yes).
  Cells with implied 1 are `implied1`; the mismatch direction is
  *buyable-Yes* (a taker could buy/have bought the sibling's Yes below
  redemption).
- **Phantom** = a sibling cell whose implication was falsified by arithmetic
  itself: implied0 cell where the sibling later recorded winner=Yes, or
  implied1 cell where the sibling later recorded winner=No. Phantom cells
  are excluded from tradability numerators and phantom density is reported
  (per ideaGenAlpha: phantom-density > 50% → paper-trail note only).

## 5. Tape canonicalization and casualty definition (pre-registered)

Per (marketId, txHash) trade group (all rows of one tx share one ts), the
canonical **print** of the Yes-side trade price is:

- `pYes` = size-weighted mean of `price` over Yes rows in the tx (both BUY
  and SELL rows carry the trade's Yes-price; bounds sanity-filter to
  (0.01, 0.99] before weighting);
- `sizeShares` = (Σ BUY-Yes sizes + Σ SELL-Yes sizes) / 2 — a trade always
  records both sides, halving avoids double-counting caused by the mirrored
  No-side rows and any account self-crossing;
- `usd` = `pYes × sizeShares`;
- prints malformed by the above rules (no Yes rows; or pYes outside
  0.02–0.98) are dropped rather than repaired.

**Depth proxy disclosure (cleared here, per task brief):** the tape carries
no order-book depth. The depth proxy is printed trade volume at stale-price
levels inside the stale window — i.e., the next-K-prints idea collapses to
"all prints within the window", so the proxy is *realized flow at the stale
price*, not resting book depth. Consequences, stated up front: (i) it is an
optimistic depth read (the price levels were available to takers at print
time — the prints themselves are direct evidence someone traded there), and
(ii) it is also a pessimistic availability read (resting quotes larger than
print sizes never show). The GO/kill thresholds are set against the
realized-volume number for that reason.

**Stale threshold (frozen):** a print inside a sibling cell's measurement
slice [T, T + 6 h] is *stale* iff its mismatch vs the implied price exceeds
**0.02 absolute in the exploitable direction**:

- `implied0`: mismatch_i = pYes_i (> 0.02 ⇒ someone bought Yes at ≥ 0.02 in
  a market that must be worth 0; the taker counterpart who sold captured
  ~pYes per share net of 50 bps);
- `implied1`: mismatch_i = 1 − pYes_i (< 0.98, i.e. believed certain to pay
  $1 still trades under; a taker buying captures 1 − pYes − 0.005 per
  share).

A sibling cell is **STALE** iff it contains a stale print at time t1 and
another stale print at t2 with t2 − t1 ≥ 60 s. A cell with exactly one
stale print is reported separately (single-print cells cannot establish a
60-s window and are NOT counted as stale in the headline statistic);
cells with t1 ≥ T + 60 s are double-cased because the first stale print
itself already sits in the ≥60 s post-resolution band (reported in the
bands table, excluded from the ≥60 s headline numerator).

## 6. Tradability + kill criteria (frozen)

Per STALE cell and per delay window W ∈ {300 s, 600 s},

- `depthUsd[W]` = Σ usd over stale prints with ts ≤ T + W;
- `netUsd[W]` = Σ (mismatch_i − feeShare) × sizeShares_i where feeShare =
  0.005 × notional (50 bps taker fee, ideaGenAlpha convention) — summed over
  stale prints inside W, characterized as $ a taker who cut the queue at
  those printed levels would have netted;
- a cell is **capturable at W** iff depthUsd[W] ≥ **$1,000** and
  netUsd[W] > 0 (the $100 secondary from ideaGenAlpha §3(a) is reported as a
  secondary row, clearly marked).

Deadline **DECISION RULE (frozen before the run):**

- **GO** requires ALL of: (1) ≥ 2% of eligible stem-gated trigger-sibling
  cells are STALE non-phantom, AND (2) ≥ 1% of stem-gated resolution
  *trigger events* have ≥ 1 capturable-at-600s cell; AND (3) the set of
  capturable events satisfies the ideaGenAlpha transport gate idiom: n ≥ 20
  events AND per-event median netUsd > 0 AND P(>0) ≥ 85% at the CELL level
  (event-level bootstrap over capturable cells, seed 7, 2000 draws).
- otherwise **NO-GO** for the strategy lane; the decay-curve table is still
  reported (§8) for R9 product content.
- phantom-density > 50% of stale cells ⇒ NO-GO with a paper-trail note only
  (per ideaGenAlpha #5's kill), independent of the other clauses.

**Censoring note (honest):** a sibling with zero prints in [T, T+6 h] cannot
reveal whether it was stale (silence = corrected-and-untraded OR still stale
with no traders — indistinguishable on this tape). Absent-print cells are
counted as `censored` (not stale) in the headline; the censor rate is
reported so the reader can bound the residual.

**Runtime cap (pre-registered):** the sweep must complete in < 30 min
wall-clock. Hard deadline 25 min script-internal: any stage exceeding its
budget (load 10 min, implications 5 min, window walks 8 min, reporting
2 min) stops that stage and produces partial tables flagged `TRUNCATED`.

## 7. Pre-regression sanity checks (run structurally, before §8 was computed)

- Slug/phrasing census performed: 2,074 resolved markets, 1,240 `by`-clause,
  1,193 `on`-clause, 118 next/first-on (class E) — matches the manual review
  of the top ladder families. Nothing else was computed.

## 8. Results

<filled by scripts/research/staleSiblingSweep.py runs>

**Amendment (flagged 2026-10-17, before interpreting any stale stats):** run 1 exposed S5's tape prefilter (canonical pYes restricted to 0.02-0.98) as a defect: correctly-priced prints outside that band were dropped, which collapsed the observable definition and left 97%+ of cells falsely censored. The prefilter is widened to the full (0,1) band; stale detection, thresholds, and censoring semantics are UNCHANGED (a print counts as stale only on mismatch > 0.02 exactly as pre-registered; runs 1's verdict was NO-GO under the stricter filter, and the widened filter can only add counted prints in both directions — no GO direction is favored).

### Census
| class | rungs parsed | stems | stems passing gate | trigger events |
|---|---:|---:|---:|---:|
| E | 110 | 4 | 4 | 110 |
| N | 697 | 129 | 44 | 392 |

### Cell outcomes (pre-registered S5 definitions)
| class | cells | censored | observable | stale | stale% obs | 1-print | 1-print>=T+60 | phantom% | triggers w/ cells | gated triggers |
| E | 6 | 1 | 5 | 0 | 0.00 | 0 | 0 | 0.0 | 1 | 110 |
| N | 376 | 208 | 168 | 1 | 0.60 | 0 | 0 | 0.0 | 78 | 392 |

### Class E decay

| persistence window tau | fraction of stale cells still stale at tau |
|---:|---:|
| 1 min | 0.0% |
| 5 min | 0.0% |
| 10 min | 0.0% |
| 30 min | 0.0% |
| 60 min | 0.0% |
| 360 min | 0.0% |

| band since resolution | stale cells w/ stale print | stale $ volume | median mismatch |
|---|---:|---:|---:|
| [0,1] min | 0 | $0 | nan |
| [1,5] min | 0 | $0 | nan |
| [5,10] min | 0 | $0 | nan |
| [10,30] min | 0 | $0 | nan |
| [30,60] min | 0 | $0 | nan |
| [60,360] min | 0 | $0 | nan |

- delay window 300s over non-phantom cells: stale depth $0, net $0, cells net>0 0/0
- delay window 600s over non-phantom cells: stale depth $0, net $0, cells net>0 0/0
- capturable@600s depth>=1000: 0 cells over 0 events, total net $0
- capturable@600s depth>=100: 0 cells over 0 events, total net $0

**Class E: stale 0.00% (need >=2%) | capturable@$1k events 0 (0.00% of 110 gated triggers, need >=1%) | P(>0) 0% (need >=85%) | phantom 0.0% => NO-GO**

No >60-s residual reached the stale bar in this class: sibling rungs trade only inside their own resolution batch, and every print found between trigger resolution and sibling resolution was already within 0.02 of the implied price.

### Class N decay

| persistence window tau | fraction of stale cells still stale at tau |
|---:|---:|
| 1 min | 100.0% |
| 5 min | 0.0% |
| 10 min | 0.0% |
| 30 min | 0.0% |
| 60 min | 0.0% |
| 360 min | 0.0% |

Stale window duration (min): p10 2.4, p50 2.4, p90 2.4, max 2.4; median max mismatch 0.028

| band since resolution | stale cells w/ stale print | stale $ volume | median mismatch |
|---|---:|---:|---:|
| [0,1] min | 1 | $4 | 0.020 |
| [1,5] min | 1 | $0 | 0.028 |
| [5,10] min | 0 | $0 | nan |
| [10,30] min | 0 | $0 | nan |
| [30,60] min | 0 | $0 | nan |
| [60,360] min | 0 | $0 | nan |

- delay window 300s over non-phantom cells: stale depth $4, net $4, cells net>0 1/1
- delay window 600s over non-phantom cells: stale depth $4, net $4, cells net>0 1/1
- capturable@600s depth>=1000: 0 cells over 0 events, total net $0
- capturable@600s depth>=100: 0 cells over 0 events, total net $0

**Class N: stale 0.60% (need >=2%) | capturable@$1k events 0 (0.00% of 392 gated triggers, need >=1%) | P(>0) 0% (need >=85%) | phantom 0.0% => NO-GO**

Reading: the class's longest >60-s stale window is the 'implied0' cell from trigger 'US x Iran diplomatic meeting by June 16, 2026?' (No at 06-17 06:17Z) against still-unresolved sibling 'US x Iran diplomatic meeting by June 15, 2026?': prints at mismatch 0.020-0.028 for 144 s carrying $4 notional ($4 net of 50 bps) -- a second-class residual exists but is 3-4 orders of magnitude below the $1k tradability gate, and it dies long before our 300-s floor.

### Product-content note (feeds R9)

Mechanically stale-ladder mismatches on these tapes are a live-monitorable, retail-visible phenomenon, not a strategy lane for our delay profile: they appear at rung resolutions and decay on the order of minutes (see the survival tables in S8), so the right product use is a R9 watch-feed stale-window counter -- surfacing currently-stale sibling prints and their measured decay in real time as engagement content -- rather than an auto-trader, since our 300-600s delay sits the wrong side of the measured half-life.
