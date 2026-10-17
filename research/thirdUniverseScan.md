# Third-universe scan: non-military insider-evidence categories

Data-driven population count for ideasResearch §4 candidates **before any
strategy work**: how big is the resolved-market burst population in each
category, how deep are the books, how much of it is fee-exposed. Companion
script `scripts/research/thirdUniverseScan.py`; raw JSON under
`data/raw/thirdUniverse/<tag>/`.

## Pre-registered readout (written before the scan ran)

Categories: `earnings`, `merger`, `acquisition`, `fda`, plus the cheap
third probe `sp-500`. Burst semantics copied from
`scripts/research/entrySweep.py:107-108` (entrySweep exposes no burst-length
constant): BUY fills grouped per (account, marketId, outcome); a gap of
**>10 min (burstSec = 600s)** starts a new burst; burst USD = Σ size×price
over the burst's fills. Fills read from data-api `/trades` with
`takerOnly=false&side=BUY` — the same legs the shipped fetch pipeline keeps.
Trades pulled for a **top-60-by-market-volume resolved sample per category**
(not the full universe — that's the expensive pulls this scan avoids), so
per-category burst counts are estimates from the biggest books, not census.

Verdict thresholds (fixed before data collection; each category stands alone):

| Verdict | Condition |
|---|---|
| **GO** | projected ≥$5k-burst events ≥ 150 **and** fee-market share < 50% **and** ≥ 20% of sampled markets have a ≥$5k burst **and** ≥ 150 distinct ≥$5k bursts projected over the ≥$20k resolved universe |
| **PARTIAL** | projected ≥$5k-burst events 40–150, or fee share 50–70% — only a combined multi-category universe is plausibly big enough |
| **NO-GO** | projected < 40 events-with-bursts, or fee share ≥ 70% (fee cost at low-price entries eats the edge per ideasResearch §4) |

Projection (stated assumption, same arithmetic for every category): burst
adoption rate `a` = sampled markets (top-60 by volume) with ≥1 ≥$5k burst ÷ 60.
Projected events-with-bursts = `a ×` (total ≥$20k resolved markets in the
crawled universe). The sample is deliberately the highest-volume slice, so it
**over-weights** burst likelihood — treat projections as optimistic bounds and
the raw sampled counts as the floor.

## Method (as executed — one API discovery forced a design change)

Gamma API notes verified live on the first crawl attempt:

- offset pagination on `/events` walls at ~5,000 rows (`offset too large, use
  /events/keyset`);
- **`/events/keyset` ignores a `cursor` query param entirely** — passing the
  opaque `next_cursor` as `cursor` returned the identical head page forever
  (15k+ duplicate pages before the id-regression guard caught it). The real
  parameter is **`after_cursor`** (gamma OpenAPI: "Opaque keyset pagination
  cursor from a previous response"). After the fix every page advances and
  the chain exhausts normally;
- `limit` is clamped to 100;
- `volume_min` filters server-side on keyset, so the ≥$20k slice is a
  complete pull, not a sample;
- `include_markets=false` strips markets from event rows (~7.5KB → ~0.3KB
  per event), used for the full-tag census; resolution and per-market
  `feesEnabled` come from the full-markets floor slice.

So each tag got two cached keyset walks (`data/raw/thirdUniverse/<tag>/`):

1. **census** — every closed event still attached to the tag, slim rows
   (id/closed/closedTime/volume/dates). Cross-checked against the old
   offset endpoint (`closed=true&tag_slug=…&offset`), exact match on all
   five tags.
2. **floor slice** — `closed=true&volume_min=20000`, full markets; filtered
   to resolved events (all markets closed with a 0/1 outcome), yielding
   market rows + fees + conditionIds (cached `<tag>/markets.json`).

Burst estimate (phase 3): top-60-by-volume resolved markets per category,
full BUY-fill tape via data-api `/trades` (`takerOnly=false`, both CLOB
legs — shipped-fetch behaviour), grouped into entrySweep-style bursts
(BURST_SEC = 600s, semantics copied from `entrySweep.py:107-108` since
entrySweep exposes no constant). Per market: ≥$5k/$10k/$50k burst counts,
single-fill ≥$5k wallets, wallets with any ≥$5k burst, prints/hour over the
market span, prints inside a ≥$5k burst.

Projection assumption (pre-registered above, repeated here because it
shapes every number below): adoption rate a = markets-with-≥$5k-burst ÷ 60
applied to the ≥$20k resolved market count. The sample is the highest-volume
slice, so a is optimistic; treat projections as upper bounds and the raw
sampled counts as the floor.

## Results

### Corpus (keyset census cross-validated against the offset endpoint)

| tag | closed ev | closed ev ≥$20k | floor-slice ev | resolved ev | resolved p50/p90/max vol | mkts | ≥$500k | ≥$100k | ≥$20k | fee % | date range (ev endDate) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| earnings | 1,377 | 242 | 242 | 242 | 32.7k / 98.8k / 995k | 246 | 3 | 23 | 243 | 10.6 | 2024-01-19 → 2026-08-26 |
| merger | 5 | 2 | 2 | 2 | 53.8k / 53.8k / 53.8k | 2 | 0 | 0 | 2 | 0.0 | 2024-10-31 → 2026-03-31 |
| acquisition | 2 | 0 | 0 | 0 | — | 0 | 0 | 0 | 0 | 0.0 | — → — |
| fda | 34 | 4 | 4 | 4 | 46.1k / 49.6k / 49.6k | 36 | 0 | 0 | 3 | **97.2** | 2025-04-29 → 2026-12-31 |
| sp-500 | 297 | 192 | 192 | 191 | 104k / 324k / 1.10M | 323 | 3 | 94 | 231 | 47.1 | 2025-12-04 → 2026-10-15 |

### Burst estimate (top-60-by-volume resolved markets per category)

| tag | mkts | fills | bursts ≥$5k | ≥$10k | ≥$50k | 1-fill ≥$5k wallets | wallets w/ ≥$5k burst | mkts w/ ≥$5k burst | prints/mkt-hr | med prints in ≥$5k burst |
|---|---|---|---|---|---|---|---|---|---|---|
| earnings | 60 | 89,532 | 171 | 104 | 23 | 74 | 103 | 41 | 6.0 | 3 |
| merger | 2 | 1,864 | 0 | 0 | 0 | 0 | 0 | 0 | 0.8 | 0 |
| acquisition | 0 | — | — | — | — | — | — | — | — | — |
| fda | 36 | 4,405 | 1 | 1 | 0 | 0 | 1 | 1 | 8.5 | 0 |
| sp-500 | 60 | 139,154 | 390 | 138 | 3 | 156 | 290 | 59 | 59.8 | 8 |

Wallet counts are summed per market row, so multi-market wallets are
multi-counted — the burst/wallet columns are per-market activity volume,
not a category census of wallets.

### Task-3 answers, per question

**≥$5k burst population on resolved markets.** Earnings and sp-500 are the
only live ones. Within the top-60 samples alone (floors, before any
projection): earnings 171 ≥$5k bursts across 41 markets / 103
(wallet,market) slots; sp-500 390 ≥$5k bursts across 59 markets / 290
(wallet,market) slots. Projected to each category's ≥$20k resolved market
universe (a × N): earnings 41/60 × 243 ≈ **166 events**, sp-500 59/60 × 231
≈ **227 events**. Size-tiering: in both categories ≥$10k bursts are ~60% of
≥$5k; ≥$50k exists only in earnings (23 sampled; sp-500 has 3).

**Book depth (fill-tape density).** Earnings books are thin: 6.0 prints
per market-hour, and a ≥$5k burst clips a median of **3 prints** — burst
windows are 1–3 prints of size, i.e. single-tick entries dominate and a
resting-limit copy would often be filled behind the mover. sp-500 is
materially deeper (59.8 prints/mkt-hr, median 8 prints inside a ≥$5k
burst), close to what the burst-entry engine assumes.

**Fee exposure.** Pre-registered economics caveat confirmed quantitatively:
fda markets are fee-ridden at **97.2%** of the resolved slice, sp-500 at
**47.1%** (4-5% taker economics — at p≈0.10 an entry pays ~3.6% of stake,
per ideasResearch §4), earnings at **10.6%**, merger 0% (sample of 2).

**Resolved-market coverage / representativeness.** The census is complete
over everything still attached to each tag (offset cross-check exact), and
the floor ≈$20k slices are almost fully resolved (earnings 242/242,
sp-500 191/192, fda 4/4). Robustness limit: tag listings prune archived
events, so the census sees the current tag population — earnings reaches
back only to 2024-01-19, meaning dead-weekly-churn before that date is
invisible to any gamma tag crawl (that is a data-availability wall, not a
hole in this scan). Earnings churn weekly and the captured slice spans
~2.5 years of that churn — a representative resolved slice. The task
brief's "tag id 1013" lore: 1,013 closed earnings events were visible when
§4 was written; the number has since grown to 1,377 (settled rounds added).

## Verdicts (filled against the pre-registered table, no criterion re-derivation)

| category | projected ≥$5k-burst events | fee share | adoption | verdict | why |
|---|---|---|---|---|---|
| **earnings** | 166 (a=0.683 × 243) | 10.6% | 68% | **GO** | ≥150 events, fee share ≪ 50%, ≥20% adoption; raw sampled floor already ≥150 bursts. Book depth is the binding risk (median 3 prints in a ≥$5k burst, 6 prints/mkt-hr) — a universe build needs the maker-entry/limit arm from ideasResearch §6, not taker copies. |
| **sp-500** | 227 (a=0.983 × 231) | 47.1% | 98% | **GO, fee-thin** | Population comfortably clears every line, but the 47.1% fee share sits 2.9 points under the 50% line — one classification change flips it to fee-majority. Treat as GO only with fee-aware execution or a volume-tier fee check, else downgrade to PARTIAL. |
| **fda** | ~0 | 97.2% | 3% | **NO-GO** | Double-dead: near-zero burst population AND fee share ≥70% (fee cost at low-price entries eats the edge). Evidence thesis (clinical-trial insiders) can't be tested on a resolved Polymarket book worth the name. |
| **merger** | 0 | 0% | 0% | **NO-GO** | The tag has 5 closed events in total. Zero ≥$5k bursts across both ≥$20k events. Category doesn't exist as a listing; M&A action lives under loose slugs, not this tag. |
| **acquisition** | 0 | 0% | 0/0 | **NO-GO** | 2 closed events, none ≥$20k, no floor slice. Dead tag. |

Combined GO universe (earnings + sp-500) projects to ~393 ≥$5k-burst
events against the 150 total-event line — a combined multi-category
universe is buildable, with sp-500's fee share as the open execution
question.

### What would change these verdicts

- sp-500 fee share measured on the schedule actually charged
  (`feeType`/volume-tier taker rates, per ideasResearch §6), not the binary
  `feesEnabled` flag used here — if fee-bearing volumes are overwhelmingly
  the biggest books, effective exposure is higher than 47.1% of markets;
- earnings book depth improving materially (prints/hour rising) would
  soften the maker-arm requirement;
- sp-500's date range ends 2026-10-15 (still resolving weeklies) — the
  resolved slice will grow each week; re-run cheaply from cache and the
  population floor can only rise.
