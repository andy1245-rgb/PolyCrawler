# Methodology attack: adversarial audit of the research practice (2026-10-16)

Scope: the **measurement machinery** (how verdicts are produced), not the strategies.
Every claim below was confirmed by reading code (file:line) or by a cheap local count
CHECK; suspicions that could not be confirmed by reading are marked honestly.
Each item carries the exact check that kills or confirms it. Feed the verdict
designs for the next round from this list.

Grading: **HIGH** = could flip a verdict · **MED** = could move p5 or the headline ·
**LOW** = cosmetic.

Note on the task brief: I could not find any `sotorch` reference in the tree
(grep over `*.py`, `*.md` = 0 hits). The "prefix/asset" parity issue it points at
is real and is covered in A1/A2/A12 — if sotorch lives elsewhere, the audit skipped
it. Everything else in the brief was traced.

---

## A1. Burst semantics: THREE different burst definitions across the stack (HIGH)

Evidence:
- `scripts/research/entrySweep.py:107-114` — research bursts are **gap-chained**:
  a burst splits only when a leg is >10 min after the *previous* leg, so a
  dribble of legs every 9 minutes forms one "burst" of arbitrary length; the
  entry is the whole window (usd = Σ legs, line 111) at `ts = first leg` (line 111).
- `src/polycrawler/strategy.py:102-110` (`observeBuy`) — engine bursts are
  **start-anchored**: any leg after `start + 10min` starts a new burst, so a
  long dribble *splits*, and each legal burst is ≤10 min of span.
- `scripts/liveWatcher.py:304` — watcher bursts are start-anchored like the
  engine (`ts - bursts["start"] > BURST_WINDOW_SEC` → reset).

Consequences stacked on top:
1. The whole-burst cell **selects the entry on the burst's final composition**:
   `price = usd/shares` over the *final* window (`entrySweep.py:111-114`) is the
   price/`maxPrice` gate (`filterCell`, line 160-166). A burst whose early legs
   crossed ≥$5k at ≤0.35 but whose later high-priced legs pushed the average
   above the cap is **silently excluded** — the cell selects on future
   information (intra-burst path) a实时 trigger could not know. Conversely the
   trigger `ts` is the *first* leg's timestamp while `usd` includes legs that
   hadn't happened yet: at trigger time the gate (`≥$5k in a ≥10-min-anchored
   window`) was not yet satisfied under gap-chained semantics … but WAS
   satisfied eventually under window semantics — the two definitions disagree
   about whether the trigger is even legal, and `filterCell` never reconciles.
2. `scripts/research/engineParity.py:126,139-140` compounds this: its
   `prefixPool` re-derives `marketsSoFar` over a **marketId-sorted** frame
   (`.sort(["account","marketId","outcome","ts"])`, line 126) while the research
   side uses `ts`-sort (`engineParity.py:99`, `entrySweep.py:118`). `marketsSoFar`
   for a row = distinct-market firsts *in sort order*: in marketId order, a
   market whose first trade is later in time but alphabetically earlier inflates
   the count anachronistically. The parity tool's own residual buckets
   (`noLegalPrefix n=1`, part of `notExecutedLegalPrefix n=24` in
   `data/parity/engineResearchParity.json`) are therefore not classification-
   trustworthy.
3. `fillPrice` (`entrySweep.py:132-138`) is the next BUY print within 300s —
   which can be **the cluster's own subsequent legs** (the burst's later fills
   are normal BUY prints in the same (market, outcome)). `retReal` for
   whole-burst entries is thus sometimes priced off the insider's own later
   order flow, i.e. our "realistic fill" partially assumes we bought inside
   the insider's burst path.

Why it could flip a verdict: the +105%/+119% in-sample headline counts entries
under gap-chained whole-burst semantics that the engine (leakage-reduced
prefix semantics) does **not** reproduce; the OOS verdicts re-used the same
machinery, so both in-sample edge and OOS falsification are graded on a
definition the live rule does not implement (see A5).

CHECK (cheap, kills/confirms):
- Residual-count reconciliation: recompute `prefixPool` with `ts`-sort and
  compare the legal-prefix set against the marketId-sorted one
  (`scripts/research/engineParity.py` as a module, 2 min runtime) — any
  divergence means the published drift buckets were misclassified.
- Semantics reconciliation: on `data/entrySweep/entries_v2_df8efad228.parquet`,
  re-run `filterCell` for the shipped cell with a start-anchored burst split
  (re-derive bursts from fills with `strategy.observeBuy` semantics), and diff
  n/ret/p5 vs the gap-chained cell (rebuild only this one cell, ~10 min).

## A2. Whole-burst cell counts entries a live copy cannot take (MED, measured)

Evidence: `data/parity/engineResearchParity.json` — overlap 402/427,
`notExecutedLegalPrefix` 24 (5.6%: legal prefix existed, delayed fill never
landed at the gates), `noLegalPrefix` 1, `enginePrefixDrift` 5. The research
cell grading counts all 427; the engine counts what replay says is legal.

Why it matters: ~5.6% of the +105% cell are entries whose delayed copy never
opened — status.md itself says execution-side losses are under-counted. On a
thin-margin cell this is the difference between +105% and +~95%; below p5 it
moves the floor. For verdict designs: every whole-burst ret and p5 carries an
upper bound of ~+5–10pp on executability.

CHECK: run `uv run python scripts/research/engineParity.py` (current tape,
~10 min) and require `notExecutedLegalPrefix / n` to be reported next to every
shipped-cell headline in status.md.

## A3. Event-level bootstrap pseudo-independence: date-ladder rungs (HIGH for ranking)

Evidence:
- `entrySweep.py:181-186` — `evaluate()` resamples **eventSlug** units.
- Universe check (run 2026-10-16): `data/universe/markets.parquet` has 857
  markets across **81 eventSlugs**, with `israel-strikes-iran-by-*` alone = 5
  distinct slugs; every ladder rung is its own eventSlug. `research/eventUniverse.md`
  (§ "not 72 independent shocks") already declared the rungs one process.
- `research/episodeResample.md` (unit problem + headline): the shipped cell's
  event-level P(>0) 0.99 rests partly on ladder rungs, and **100.6% of the
  cell's PnL is one episode** (iran-Feb cluster) at K*=34; ex-top the cell is
  P(>0) 0.10–0.28, ret −0.27…−0.47.
- The episode graph machinery (`scripts/research/episodeTransport.py`) exists
  behind `--episodes` but status.md §9.2 states regrouping was **NOT** run on
  either OOS pull ("not trivially reproducing from main's docs — skipped").
  `episodeTransport.py:95-97` pins K*=34 from the in-sample tape when the OOS
  tape has no Iran-Feb reference, so an OOS episode gate would use an
  in-sample-derived K silently.

Why it could flip a verdict: the floor-ranked cell selection that produced the
$10k/≤0.35 candidate was made under pseudo-independent event units; the
in-sample p5 +0.39..+0.57 that "did not transport" was itself inflated by
rung-level independence. The honest unit is the episode; the in-sample verdicts
citing event-level p5/P(>0) floors are over-stated until regrouped.

CHECK (~15 min): `uv run python scripts/research/entrySweep.py --episodes` on
the in-sample dirs with `configs/sweeps/militaryEntryGrid.yaml`, plus
`uv run python scripts/research/oosTransport.py --episodes --data-dir
data/oosExpansion` — read the `episodes/epP/epVerdict` columns of the top rows
only. Also log the `gate` string in `printUnits` output each time: any OOS run
that pins K* (gate="pinned…") must not be cited as a data-derived episode result.

## A4. Freshness gates (`ageDays`, `marketsSoFar`) are defined on the FETCH-SCOPE tape (HIGH, measured)

Evidence:
- `entrySweep.py:99-106` — `firstSeen` = min ts per account over the **fetched
  dirs only**; `marketsSoFar` = distinct markets *in the fill tape* only
  (line 118-122). Research never looks outside the fetched market set.
- Measured (2026-10-16, cheap count over the cached entry tapes): of
  shipped-cell-like entries (usd≥5000, price≤0.35, age≤5d, mkts≤3),
  **49.0%** in-sample, **40.6%** on the expansion pull, **72.7%** on the 60-slug
  pull begin at the account's *first trade in the fetched tape* — i.e. for
  that fraction of the graded population, "fresh" is **unidentifiable**
  (the account's entire observable life = this burst; any pre-history on
  non-fetched markets is invisible).
- The scopes differ across samples: in-sample dirs span an 81-event
  mixed-category tape (`data` + `data/universe`), while every OOS dir is a
  **military-only** slug set (`configs/oosFetch.yaml`, `configs/oosExpansionFetch.yaml`).
  "Age ≤5d, ≤3 markets" therefore means different populations in-sample
  (filters against speculators' sports spray, partially) and OOS (admits any
  account that simply never traded a fetched ladder before). The 9.2
  observation "big OOS bursts sit on day-0/1 accounts" is at least partly this
  artifact.
- Direction is pernicious both ways: in-sample the gate is *stricter* than the
  label suggests (it occasionally sees the sports spray), OOS it is *looser*
  than in-sample, so the transport compares two rule definitions, not one rule
  on two eras. Neither direction alone rescues the OOS FAIL (the whole grid is
  negative, and the delay-realistic numbers agree), but verdicts phrased as
  "the rule does not transport" are contaminated by "the rule redefinition".

CHECK (kills/confirms, ~5 min): pick 50 accounts from the OOS-expansion
cache's shipped-cell over the `atAccFirst` fraction (probe script A4 above),
call Data API `/activity?user=` once each (50 requests, <1 min) and compute
true first-trade age and true markets-traded. If most `atAccFirst` accounts
are genuinely day-0 on Polymarket, the artifact is small; if their true ages
are weeks+, the freshness gate means different things per tape, and every
cross-tape design must re-derive age from an out-of-tape source (or per-market
fetch supersets) before comparing p5s.

## A5. LIVE/RESEARCH rule drift — the paper gate is not the graded cell (HIGH)

Evidence, line by line (`scripts/liveWatcher.py` vs the shipped cell
$5k/≤0.35/age≤5/≤3mkts — `configs/militaryBacktest.yaml`, `oosTransport.py:55-60`):

| rule element | research graded cell | live watcher | verdict |
|---|---|---|---|
| burst window | gap-chained, unbounded span (`entrySweep.py:107`) | start-anchored 600s (`:41, :304`) | MISMATCH (same class as A1) |
| ≥$5k gate | whole window aggregate ≥5000 (`entrySweep.py:111, filterCell :160`) | RUNNING prefix ≥5000 (`:312`) | engine-style — closer to `strategy.py:235-242` than to the graded cell |
| price cap | final burst avg ≤0.35 | running avg ≤0.35 `:313` | matches number (0.35), not the aggregate |
| age | first trade over full fetched tape (`entrySweep.py:99-122`) | firstTs = first **observed** fill `:288` | MISMATCH, see (a) |
| marketsSeen | distinct markets over full fetched tape incl. non-fetched-body (81-event scope in-sample) | distinct **watched-market BUY legs only** (`:294-296`) | MISMATCH, see (b) |
| fee filter | **none** (fees never modeled — A8) | skips `feesEnabled` markets (`:316`) | asymmetric |
| event scope | 15-keyword MILITARY (`researchData.py:26-33`) | 24-keyword MILITARY (`:51-55`: adds syria/yemen/invade/nuclear/airspace/blockade/withdraw/ceasefire/war) | MISMATCH — live samples an event universe the verdicts never graded |
| docstring | shipped rule | "≤3 days old … ≤0.50" (`:4-5`) | stale doc, contradicts its own constants |

Specific admission risks:
(a) `firstTs = ts` on first push-tape observation (`:288`): any account whose
pre-history is outside the watched set is age **zero** at its first watched buy.
The `/activity` rescue (`:252-279`) only runs for accounts first seen in
**backfill** (`:292` — `if backfill: acct["backfill"] = True`; rescue called
only when `acct.get("backfill")` at `:315-318`), and even then checks only a
5-day pre-bet window (`:266`) — an account whose other-market activity was 6+ days
before the burst passes as "fresh". Both paths admit a
dormant-then-reawakened account the research gate would have age-gated away.
Also: could it admit an account whose buys were on OTHER markets within 5d but
whose first *watched military* trade is now? No — the rescue queries
`/activity` across all markets (`:263-266`), so 5-day-old cross-market activity
does disqualify; but only when `backfill` was set. Push-tape-observed
accounts get **no rescue path at all**.
(b) `nMarkets` counts only the watcher's observed BUY legs on open watched
markets — a live rule strictly looser than research's "markets ever traded";
a 40-market fresh-looking account with one prior watched-market leg passes ≤3.

Why it could flip a verdict: the money gate ("live paper trades are the deciding
evidence", status.md §9.2) compares the paper sample against a backtest
expectation computed on a different rule: different burst semantics, wider
event set, weaker age/markets gates, fee exclusion. Any live↔backtest
discrepancy is jointly explainable by rule drift rather than transport failure —
that ambiguity is exactly what the paper-gate design exists to exclude.

CHECK (~2 h, mostly build-free): a **rule-replay equivalence tester**:
(1) hard-fail test on constants — script asserts `liveWatcher` MILITARY ==
`researchData.MILITARY` and docstring ages == constants (currently fails; write
it, minute); (2) implementation-level: re-simulate `data/live/signals.csv+
state.json` ages/markets/bursts against the graded-cell semantics offline —
for each alert look up the account's full `/activity` first-trade age and
markets count, and re-derive the burst under gap-chained window semantics;
report n-eligible/n-excluded per gate divergence (~1 h crawl at 1 req/s).
Until this runs, the paper PnL curve and the backtest verdict are not
comparable numbers.

## A6. Price-tape construction details (MED)

Evidence:
- Trigger "price" and the same-second collapse: `entrySweep.py:128-138` +
  `oosTransport.py:108-117` — the tape is `unique(subset=["ts","marketId","outcome"],
  keep="last")` AFTER computing nextPrice: same-second DIFFERENT-price BUY
  prints (multi-buyer prints are common on bursts) collapse to one row whose
  price/successor depend on raw parquet order (`fetch.py:519` sorts by
  `ts, txHash` — no price order), and the "next print ≤300s" fill is the first
  print at ts'>ts in that collapsed stream — honest as to timing, blind to
  price spread within the second.
- BUY-only tape (`entrySweep.py:124-127`) vs engine tape, which is **all fills
  incl. SELL prints plus the 1−p complement trick** (`priceMove.py:178-210`,
  `buildPriceTape` seeds the complement outcome) — the two systems' delayed
  prices can disagree around spread events (engine may price off a stale SELL
  print ≤6h old — `priceMove.py:17` `staleWindow=6h` — through
  `priceAt(... tolerance=stale, strategy="backward")`, line 236-259).
  In thin post-burst books a ≤6h-old pre-burst print can be materially
  lower than the current book — engine `entryPrice` succeeds at a price the
  book no longer offers.
- No size awareness: `fillPrice`/`nextPrice` is a price, never a size; the
  delay-realistic variant (`oosTransport.py:120-124`) charges +50bps on a print
  whose size may be $20. The 9.2 executability claim (landed300) validates
  *that a print existed within 300s*, not that copy-size liquidity existed there.
- Unresolved suspicion, not confirmed in code: cross-side double counting
  between v1 `/trades` rows (`fetch.py:270-277`, `takerOnly=false` fetches both
  maker+taker rows; `fillDedupeKeys` `fetch.py:53` includes side/size/price so
  BUY vs SELL legs of one tx can't collide) — I could not construct a row set
  that double-counts a BUY burst, and the on-chain rebuild orderBurstOnchain
  already re-verified BUY legs against `(txHash, wallet, shares, usd)+ fills`
  (status §7) — but the negative has never been tested on the persisted table.

CHECK (cheap): (1) same-second dispersion count on the in-sample fills
 tapes: per (marketId,outcome,ts) BUY prints, share of groups with
 maxPrice−minPrice > 0.02 (~20 min, one scan_project agg); if >1% of burst
 triggers, the keep="last" convention needs a documented average (or a seed)
 instead of parquet-order luck. (2) dedupe audit: count `txHash` rows per
 (account, side) >1 with equal (size, price) — exact-duplicate check on
 `data/universe/fills.parquet` (~5 min).

## A7. Split/resolution integrity (MED; one leak found, one verified-clean)

Evidence:
- Winner/resolvedAt provenance: `fetch.py:128-131` — `winner` from the Gamma
  snapshot where exactly one outcome price == 1.0 at fetch time; `resolvedAt`
  = `umaEndDate`/`closedTime` *only if winner parsed*, else None. A market with
  a winner, but a missing/0.5-both snapshot, drops from the ret null filter —
  conservative, fine. Universe-wide: 7/857 winner-null, 7/857 resolvedAt-null
  (run 2026-10-16) — negligible in-sample. OOS expansion: 49 unresolved drop
  by ret-null design (status §9.2).
- The rule engines carry **no sibling-market, no cluster, no funding feature**
  — `takeEntry` (`strategy.py:111+`) consumes only account tape aggregates;
  the event-key `eventKey`/`maxEntriesPerEvent` uses the same market sibling
  awareness as `recordCopy` (`strategy.py:161-164`), not outcome information,
  so **no sibling-resolution lookahead exists in either research or engine
  path** for the burst tape family. (A cluster-aware variant of this leak — copying
  through the sibling from a co-traded two-market date-ladder cluster that resolves
  half its dates early — does exist conceptually, but only in *discovery-mode*
  cluster copying, which is exercised by backtest.py discovery mode, not by any
  military sweep cell; verdicts generated so far have no sibling feature.)
- Multi-outcome event events like "who-will-enter-iran-by-june-30" have rungs
  as SEPARATE markets within one eventSlug in some fetches and as separate
  eventSlugs in others (see A3), but the entry semantics never reads another
  market's winner — HOLD-to-resolution only.
- Guard checked-and-clean: markets-vs-fills `marketId` overlap between `data/`
  and `data/universe` = **0** (markets and fills, run 2026-10-16); cross-dir
  double-counting (no `.unique(fillDedupeKeys)` in entrySweep/militaryCategory,
  unlike `backtest.loadMarketFills`) is moot today — but nothing structurally
  prevents a future same-slug fetch landing in two dirs, which would silently
  double-count bursts (concat `entrySweep.py:109-110` has no dedupe).

CHECK (cheap, reusable guard; ~1 min): add an overlap assertion in
`researchData.militaryMarketsFrame` — assert the markets concat has zero
duplicate marketId after `unique(keep="last")`, else warn loudly. Can be a
print in the next run, no code change required to run now: `pl.concat(...).group_by("marketId").len().filter(len>1)` per dir-set
(mil frame + oos dirs separately) — I ran the data/universe case, negative.

## A8. Fees and collateral realism: no fee term anywhere in the graded returns (MED)

Evidence: `grep feesEnabled` hits `src/polycrawler/fetch.py` (not persisted) and
`liveWatcher.py:316` only. The `markets.parquet` schema
(`fetch.py:122-165`) has no `feesEnabled` column; the burst ret formulas
(`militaryCategory.py:57-59`, `entrySweep.py:120-124,148-151`,
`oosTransport.py:120-124`) carry no fee term. So the +71%→+82%→+105%→+119%
chain never netted taker fees; per status §7, ~20% of live coverage carries
10%-base taker fees, and the largely overlapping military fetches are
fee-marked silently in the ret.
Quantified roughly: 10% of winnings on ~20% feeed coverage × in-sample
winRate ~35% × mean win ret ≈ …0.2·(0.9/price − 1/price)·0.35 ≈ 3.5% absolute —
on a +105% ret headline, small but honest real; on a ±5% verdict ret it flips
sign — **today only OOS verdicts (deep negatives) are immune to this.**
Also asymmetric: the live watcher EXCLUDES fee-markets (`:316`), the graded
cells include them — the paper-gate population ≠ graded population (A5 row 6).

CHECK (~30 min total): batch `gamma /markets?condition_ids=` crawl over
militaryMarketsFrame marketIds per dir-set (~1,000+~1,000 ids, ≤100/call,
~2 min), cache feesEnabled, then regrade the shipped cell and the OOS expansion
grid from their entries caches with per-winner fee `ret_adj = 0.9/fillPrice − 1`
for feeed markets. Expectation: in-sample headline −2 to −5pp; OOS verdicts
unchanged. Either way, this becomes the honest direction — status.md should
declare agreement (ret gross of fee).

## A9. Universe selection survivorship — inclusion floors on both OOS pulls (MED-HIGH)

Evidence:
- In-sample universe is volume-curated: `research/eventUniverse.md` § Method —
  $1M event floor, `order=volume desc`, paged until a page's smallest < $1M,
  plus named exclusions; `configs/militaryUniverse.yaml` adds 9 hand-picked
  military sibling events (gun-metal era); the dirs also selectively include
  `data/` (Iran-ladder + Venezuela insider cases, hand-picked).
- OOS pull-1 (60 slugs) is a hand list (`configs/oosFetch.yaml`) that leans
  Iran-war-screen heavy.
- OOS pull-2 (expansion) comes from a Gamma tag crawl **filtered by
  `volume ≥ $20k`, order=volume desc**, plus ≤5-per-stem diversity cap and
  per-family quotas (`configs/oosExpansionFetch.yaml:3-9` docstring).

Consequence: burst size and market size are endogenous — a ≥$5k burst that
failed to attract copy (stayed small) is precisely absent where the market
never got big; the sampled universe over-represents markets where copy or
market-makers made the book thick **before or via** the burst. The OOS pulls
inherit the same bias relative to the "random military burst" population, and
direction of the residual is unknowable from inside the sample. It cannot
flip the OOS verdict (the ≤0.35 grid was negative wherever books were
thin *or* thick), but the "edge is event-specific to the Iran-war-screen
tape" inference is built on a volume-curated prior of what an OOS military
market era looks like.

CHECK (~2-3 days mostly fetch budget, not compute): build a
**small-book complement**: all closed military-keyword events with
$1k ≤ volume < $20k (the excluded underside), sample 30 slugs uniform across
stack-time, fetch into `data/oosSmall` and run the 480-cell grid + candidate
neighborhood. If the small-book grid is even *more* negative, survivorship is
confirmed as NOT the driver of the OOS failure; if it materializes
qualitatively the same as big books, the FAIL conclusion is roughly intact
against the selection argument either way; if it diverges in shape (highest
ret in small books), the Iran-era realtapes were the wrong transport target —
write-up then says where the burst edge actually lives (the parameter, not
the era).

## A10. In-sample verdicts are grid-searched on the same tape they are graded on (MED)

Evidence: `configs/militaryBacktest.yaml` — `splitDate: 2023-10-01` = tape start
("validation window: the full accrued universe"); the 480-cell grid
(`GRID_AXES`, `entrySweep.py:55-60`; + 36-cell sweep in
`research/militaryCategory.md`) is ranked and the shipped point picked on the
same ret/p5/P(>0) values that are then published as the cell's grade. The
half-split at 2025-06-01 is the only internal holdout, and only via
h1/h2 means at entry time (`entrySweep.py:197-198`) — not at episode level.
The pre-registered OOS gate did its job (FAIL), so nothing shipped is broken;
but status.md's doomed candidates for "pending more OOS" ($10k/≤0.35 p5
+0.39..+0.57) exist only under the graded-on-fitted-data caveat. This is why
the floor-ranked *p5* over the grid should never again be reported as a
candidate's expected quality — only as a relative ranking to be re-derived OOS.

CHECK (~10 min, reuse caches): LOO(per-top-episode) on the in-sample shipped
cell — drop the whole iran-Feb episode (the K*=34 group from
`episodeResample`), recompute ret/h1/h2; both halves go negative (this is the
episodeResample table already published). Also add a printed note in the sweep
output that p5 over a 480-cell grid is selection-biased; no new analysis
needed beyond the existing episode table.

## A11. Bootstrap mechanics (LOW, but one named bias)

Evidence:
- `entrySweep.py:178` — `MIN_CELL=20` counts **entries**, while status §9's
  transport gate and the oosTransport table read it as an event-count floor.
  A cell can have 20 entries on 4 events and still emit a p5 from a
  4-unit bootstrap — the p5 is meaningless at n_events<5 regardless of n.
  (`oosTransport` returned after "20 events" for the track, but the 480-cell
  grid reuses the same 20-entry floor — gradeable-cell threshold confused.)
- `rng = random.Random(7)` (line 237) is consumed sequentially across cells:
  each cell's bootstrap vector depends on how many cells preceded it in the
  grid — p5 digits change if a cell set changes (documented inside `evaluate`
  as a fix; the left-over coupling is benign but worth one sentence in any
  verdict that quotes the 3rd digit).
- `p5` is the discrete order statistic (index 50/1000, not interpolated) —
  ±0.004 quantization; fine, cosmetic.
- h1/h2 are means over entries split at 2025-06-01 (entry-time), not
  per-event — one episode's PnL splits across halves, so "both halves
  positive" inside one episode is not two independent confirmations.

CHECK (~2 min): rerun `evaluate()` on the shipped cell filtered to events≥20
(episodes if available) vs events≥4 (current grid-gradeable floor) and tabulate
the p5 both ways once; then pin the gradeable-cells statement in status.md on
the events≥20 definition.

## A12. engineParity inter-bucket classification (LOW)

Covered in A1 item 3: `prefixPool`'s `marketsSoFar` anachronism
(`engineParity.py:126` vs `:99`) plus `raw`-warm-up differences mean the
`noLegalPrefix=1` count and the `enginePrefixDrift=5` count could be swapped
or inflated — the parity verdicts quoted in status §9.1 ("cross-clip engine
again reproduces the research cell on the current tape") are direction-safe
(overlap 94% dominates) but the per-bucket numbers are not classification-proof.

CHECK: same as A1's first check (ts-sort prefixPool rebuild).

## A13. Watcher tape integrity — sub-$5k legs and dedup bounds (LOW-MED)

Evidence: sub-$5k fills only reach the watcher burst accumulator via the push
tape (`:218` comment + `:215` `filter_amount=5000` poll). Any socket gap missed
by the ≥$5k rescue (which only catches ≥$5k rows) leaves bursts
under-counted: both false-negatives (a burst that would have crossed $5k) and
false avg prices. The dedupe deque `SEEN` has a 50k-entry bound (`:165-176`);
with long-running state the FIFO eviction is memory-safe, but a 50k-row
cross-flow ordering with the 120s polls can re-admit duplicate fills if the
same (wallet,txHash,side,size,price,ts,market) is re-pushed after >50k
distinct rows elapsed — unverified, but the fillKey is exact so duplicates
would be rare to non-existent.

CHECK: count alerts in `data/live/signals.csv` whose `burstUsd` is
within 5% of $5,000 (threshold-border) and then recompute their burst from
the `/v2/trades` tape by hand — 20 signals, ~1 min. If none, this stays a
theoretical LOW.

## A14. `retReal` fallback and `won`-style null semantics (LOW, declared)

Evidence: entries with no next print within 300s keep their own trigger price
as `fillPrice` (`entrySweep.py:134-137` "quiet market ≈ no impact") — declared
in militaryCategory.md, honest, but it blends executable and non-executable
units in one mean; `oosTransport` fixes it by dropping (`landed300`) and
re-grading — a *selection on future liquidity* in the other direction
(the non-landers do not get a zero, they exit the sample; if non-landers
correlate with books dying, the delay-realistic ret is biased UP).
The in-sample cell's `retReal` is published with the optimistic fallback in
place; the OOS transport publishes the dropped-variant — two slightly different
estimators across the two halves of the same verdict framework.

CHECK (kills/confirms, variant of the A3 episodes run, ~10 min): recompute the
in-sample shipped cell with the landed300 drop + fixed sizing assessment as in
`oosTransport`, per published numbers; put both estimators side by side in
status.md §3.4. (Expected effect: in-sample retReal moves down modestly —
landed300 in-sample≈94% per `engineParity` — no verdict flips expected.)

---

## Checked-and-killed suspicions (no verdict impact, recorded)

1. Cross-dir burst double counting: `data/` ∩ `data/universe` on marketId =
   0 (markets *and* fills — run 2026-10-16). No valid concern today;
   structural guard recommended (A7 check).
2. Sibling-resolution lookahead in the graded cells: no sibling/funding
   feature anywhere in `takeEntry`/`planBuy`/`selectRuleAccounts`
   (`strategy.py`) — the graded rule cannot see sibling markets. The
   cluster-aware version of the leak applies only to discovery-mode cluster
   copying.
3. Winner/resolvedAt nulls negligible (7/857 universe markets).

## Top-3 "run now" (severity × cost)

| # | Check | Item | Severity | Runtime |
|---|---|---|---|---|
| 1 | A4 true-age probe: `/activity` on 50 `atAccFirst` OOS burst accounts | A4 | HIGH | ~5 min |
| 2 | A3 `--episodes` regrade of the floor-ranked in-sampleTop3 + the two OOS pulls | A3 (+A14) | HIGH | ~15-30 min |
| 3 | A8 fee-mark crawl + fee-net regrade of the shipped cell & OOS expansion grid | A8 | MED (headline,verdict-direction) | ~30-40 min |

Next two after these (cheaper than the above but needing their results first):
A5 rule-replay equivalence tester (the paper gate's caveat; ~2 h, blocks the
next paper-gate reading), and A9 small-book complement fetch (~2-3 days
fetch, design-informed by 1-3).

## Honest uncertainty

- **A2** direction of the 24 `notExecutedLegalPrefix` entries' PnL is unknown to
  me without running the trade-level join (check costs ~10 min and I did not
  run it); the swing size estimate (+5-10pp of headline) is illustrative, not
  measured.
- **A6/others**: no confirmed double-count construct in the v1 trades fetch;
  suspicion recorded because the on-chain rebuild verified only a sample
  era (to mid-2025), not the persisted table.
- **A9** small-book complement is the only check that could still surface an
  OOS shape change; everything else in the OOS FAIL direction is robust to
  the graded flaws (episodes can't turn −0.87 into a PASS; fee-netting can only
  make negatives worse; the freshness redefinition affects population definition,
  not sign).
- The `sotorch` item from the task brief could not be located in the
  repository; the prefix/asset parity seams it gestures at are covered in
  A1/A2/A12.
