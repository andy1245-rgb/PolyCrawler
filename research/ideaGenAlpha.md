# Idea generation: candidate edge families our stack can falsify cheaply

**Written 2026-10-17. Web-research driven; no new code; status.md untouched.**
Companion doc to `status.md` §3.4/§9 (what survived OOS) and
`research/ideasResearch.md` (tape upgrades, done). Every family below carries:
external evidence with links, honest caveats, and a cheap falsification test the
stack could run this week — which data dir, script shape, cost, kill-criterion.

**Falsified lines the candidates must not overlap** (`status.md` §3, §9.2):

- copying flagged-insider / fresh-account **longshot burns** (≤0.35) on
  military events — dead on two OOS pulls (60-slug + 200-slug holdouts;
  0/464 gradeable OOS cells with p5 > 0);
- pre-news signals (n=16, −22% retReal, P(>0) 26% — `newsAnchor.md`);
- fresh-account copying universe-wide, ex-military (−9% to −45%);
- the ≤0.35 favorite–longshot entry filter itself (control evidence).

**Working constraint from the tapes:** post-news / post-burst flow is the
informative regime on Polymarket (OOS control cell: all $10k+ bursts, any
price/age — ret +1.1%, winRate 90.9%, n=16,896, `status.md` §9.2). Bursts are
real events on the tape even where the longshot *copy* of them is dead. Ideas
below are ranked for that regime.

---

## 0. How the ranking gate works

Ranking = **edge evidence × test cost × non-overlap with a falsified line.**
Evidence graded honestly: pre-registered empirical studies with n > 10⁴ take
precedence over vendor-blog numbers selling scanners; internal control cells on
our own tapes outrank any third party for OOS-dead/alive questions in military.

Cost conventions: a "test" is a research script reusing existing machinery
(`entrySweep` cache + `evaluate()` gates, `researchData` dir plumbing,
`funding.parquet`, Gamma/crawl ATSs similar to the oosExpansion crawl). Hours
are wall-clock single-machine. Kill criteria are stated up front in the
`oosTransport` gate idiom (PASS iff n ≥ 20 events AND p5 > 0 AND P(>0) ≥ 85%
AND top-event share < 60%, both time halves — or a family-specific abridged
gate when a different statistic decides).

---

## 1. Source log (what was actually read, 2026-10-17)

Primary source reads (fetched full-text via curl/web-fetch and read):

- **Saguillo, Ghafouri, Kiffer, Suarez-Tangil — "Unravelling the Probabilistic
  Forest: Arbitrage in Prediction Markets", arXiv:2508.03474 (Aug 5 2025).**
  https://arxiv.org/abs/2508.03474 (HTML read). On-chain bid data, Apr 2024 →
  Apr 2025. Two arb types: *Market Rebalancing* (intra) and *Combinatorial*
  (inter, dependent markets incl. negRisk). Abstract: **$40M realized arb
  profit** extracted in the measurement window; heuristic reduction +
  LLM-assisted dependency inference. Read via HTML: L1-dependency reduction
  (timeliness, topical similarity via embeddings, LLM logical-dependency
  prompts), non-atomic (execution-risk) arb framing, ± window decay stats.
- **sturzael/polymarket-edge-research (README + `experiments/SYNTHESIS_flb_cross_venue.md`,
  pre-registered, 2026-03→2026-04).** https://github.com/sturzael/polymarket-edge-research
  954M-row SII-WANGZJ on-chain archive. Ten strategies, **all ten killed at
  retail latency ($1k bankroll, 200–300 ms, REST polling)**. NegRisk arb
  persistence: median window **1.0 min**, p75 1.2 min, p95 2.8 min, max 5 min
  (n=30 events, 90-day window); ≥24-h windows only **2.2%** of events,
  concentrated in low-liquidity books; sudden termination (one taker eats the
  whole leg), not decay. 39 live sum-violations on 2026-04-20 → ~half **phantom
  depth** (correct tail-risk pricing for unlisted outcomes); surviving
  structural arbs ≤3% edge with multi-month capital lockup. Sports
  **settlement-lag arb: +3.99% net backtest (n=47)** but zero live
  opportunities near close (UMA liveness closes books within ~2 h of game end).
  MM forensics: one tracked HFT operator median entry **0.981**, ~0.1%/trade
  edge, $20k–150k positions — scale-over-edge operating point.
  `SYNTHESIS_flb_cross_venue.md`: **Polymarket sports favorites in the
  0.55–0.60 bucket at T-7d resolve YES ~+30pp above the implied read**
  (e16: yes_rate 0.875, z=5.1, n=32 of 628 sports; e23 refinement +25.8pp,
  z=7.6, n=120 with ≤14d lifespan / ≥$5k window volume). Cross-venue control:
  Betfair ≤±6pp (73k+ selections, close-anchored), Azuro ≤+3pp (1.86M
  outcome-rows) — the effect is **venue × anchor specific** (nothing trades
  liquid sports at T-7d off-Polymarket), consistent with thin early
  retail flow that converges by close. Smarkets live prices agree with
  Polymarket within ~0.75pp on shared books (n=106, n=5 in the critical bucket).
- **ArbBets — "Prediction Market Arbitrage Report 2026" (vendor, six scanner
  snapshots Dec 2025 → Aug 2026).** https://getarbitragebets.com/reports/prediction-market-arbitrage-2026
  **241 profitable Kalshi↔Polymarket arbs among 3,030 matched markets — avg
  arb rate 9.5% per scan, median fee-adjusted ROI 2.1%**, max 32.3%; ROI
  concentrated 2–5% (64.7% of observations); politics 51.9% of arbs, crypto
  8.3%, sports 7.5%. Named resolved examples (Jan 2026 BTC-below-$85k short
  window at 14.9%, Epstein-files name at 11.1%, etc). Vendor incentive bias
  noted (they sell a scanner); the numbers are point-in-time snapshots, not
  continuous capture.
- **QuantPedia — "Systematic Edges in Prediction Markets" (Nov 27 2025).**
  https://quantpedia.com/systematic-edges-in-prediction-markets/ — survey.
  Cites *Price Discovery and Trading in Prediction Markets* (Polymarket vs
  Kalshi vs PredictIt, Oct 23 → Nov 5 2024): **Polymarket leads Kalshi
  price discovery (higher liquidity, most informative in final hours);
  inter-venue arb windows seconds-to-minutes, transaction costs kill most of
  it.** Also intra-venue buy-all/sell-all arbs, PredictIt 2016 precedent
  (sum > $1 mispricing surviving fee reform into 2020, up to $0.55/contract),
  longshot-bias bibliography (football 12,084 matches: favorites −3.6%,
  outsiders −26.1%; NFL Tradesports calibration curve favoring favorites).
- **Lookonchain — "Draining the Bots: How a Trader Made $233K Exploiting
  Polymarket's Thin Liquidity" (2026-01-19).**
  https://www.lookonchain.com/articles/1217 — @a4385 pushed 15-minute XRP
  up/down markets on thin **weekend/overnight** books, swamping retail-vs-bot
  depth, then nudged Binance spot ~$1M to settle the direction. Total cost
  ~$6.2k. Repeat play; several bot wallets wiped incl. a full year of profits.
  **Caution: this documented incident is manipulation and the soft targets
  hardened afterwards — it is context for the quiet-hours liquidity film, not
  a strategy.**
- **Dev.to — "Negative Risk Markets on Polymarket" (Jun 19 2026).**
  https://dev.to/fatherson/negative-risk-markets-on-polymarket-capital-efficient-multi-outcome-trading-for-advanced-bots-3gdi
  negRisk adapter conversion mechanics; production bot practice: inventory
  skew **across the whole negRisk group**, auto-`convert()` post-fill,
  conversion-parity monitoring. This is the mechanism behind family (d)'s
  *predictable hedging flow* claim.
- **Bitquery — "Polymarket Insider & Fresh-Wallet Detection API" docs.**
  https://docs.bitquery.io/docs/examples/polymarket-api/polymarket-insider-detection-api/
  Fresh-wallet + funding-source + concentration flags codified as a research
  tool — the ROSCA view of family (e). Also `whaletracks.com/tools/insider-radar`
  (large-tape → one entry per wallet/market → enrich age/book) documents the
  same shape at retail; company `cohven.com` rebuilds tracked-wallet
  portfolios from on-chain positions.
- **Columbia Business School / Kanoria et al. — up to ~25% of Polymarket
  volume possibly wash trading** (Bloomberg/Fortune/Yahoo coverage, late 2025).
  https://business.columbia.edu/faculty/press/polymarket-volume-inflated-artificial-activity-study-finds
  Not read in full (press only). Implication for all whale-following families:
  volume and trader counts are polluted; tape burst + wallet-age evidence is
  cleaner than volume-ranked evidence.
- Found but **not read** (Cloudflare/SSRN wall; recorded as found-only):
  SSRN 5910522 (478M-trade accuracy/skill/bias study),
  SSRN 6658364 "The Anatomy of a Decentralized Prediction Market"
  (30B-event, 52-day tick-level book-vs-onchain joined archive — a source to
  revisit), PolyBench arXiv 2604.14199, the zernerdoescode cross-venue
  arb paper-trading repo PDF. No claim in this doc rests on these.

---

## 2. Candidate families

Notation: **EV** = external evidence grade (A = pre-registered/peer-style
study; B = consistent practitioner data; C = single anecdotes/vendor);
**COST** = falsification cost; **NOVL** = overlap with a falsified line;
**FIT** = do we already own the needed tape. Score is the honest eyeball
product of all four; the ranked shortlist is §3.

### (a) Resolution-timing / combinatorial residual — stale siblings after one leg resolves information

- **Mechanism.** negRisk events and date ladders are exhaustive/exclusive
  condition sets. When one sibling resolves (or a hit news makes one sibling
  ~certain), the implied floor for dependent siblings moves instantly — but
  thin siblings reprice on bot attention, not on logic. Residuals: sum-of-asks
  < $1 across a condition set, or a sibling still trading at P incompatible
  with a just-resolved leg (e.g., a "by March 15" member of a ladder stays
  bid days after its parent event collapsed to a known date).
- **EV: A−.** Saguillo et al. found $40M realized (2024-04→2025-04) — but also,
  per sturzael's reading of the same corpus, **general arb windows collapsed
  12.3 s (2024) → 2.7 s (2025) with 73% of profit captured by sub-100 ms
  operators.** sturzael's own SII-WANGZJ re-analysis (2026): negRisk windows
  median **1 minute**; the only persistent film (≥24 h, 2.2% of events) sits in
  low-MM-attention books, is often **phantom tail risk**, and the structural
  remainder is ≤3% edge behind multi-month capital lockups (~$400–900/yr at
  $1k deployed — sturzael's own number, ÷5-rule would halve it again).
- **2026 verdict prior:** the fast liquid film is gone (bots); what may survive
  is exactly the thin-book, long-duration tail — and that tail is
  concession-flow-capture, not HFT. Crowding pressure is real but the thin tail
  is *below* bot attention, which is why it persists.
- **FIT: strong.** We own full per-market fills tapes (`data/oosExpansion`
  10.66M fills, `data/universe` 3.9M), the negRisk flag per market, and
  resolution + winner columns. A residual sweep is pure tape math.
- **COST: low (~4–8 h). NOVL: clean** (arb residuals, not copy-trading).
- **Test 1 (this-week shape).** `scripts/research/negRiskStale.py`:
  over `data/oosExpansion` + `data/universe` (never mixed), group markets by
  negRisk event; at each sibling's resolvedAt (or winner-final fill), walk the
  other siblings' buy prints on the tape and measure (i) time-to-repricing
  above/below the implied floor, (ii) the size of the stale window at
  T+1 min…T+24 h, (iii) whether a taker could sell the stale leg with the
  depth on tape. Kill criterion: if a taker-side stale leg ≥ $100 depth with
  sum-violation ≥ 2% occurs in < 1% of resolution events on the 260+ event
  holdout → no capturable film → dead.
- **Test 2 (optional, $0).** `/v2/resolutions` burst comparison: markets whose
  UMA-liveness-opened resolution fires hours before sibling repricing bursts
  — the "date ladder resolves info ahead of siblings" variant. Same tape.

### (b) Cross-venue spread: Polymarket ↔ Kalshi (same-question, incl. mirrored books)

- **Mechanism.** Two CLOBs, no shared book, different fee stacks, different
  regulation-gated participant pools; gaps persist minutes-to-days in
  low-attention questions. Round-trip costs: Kalshi taker fee is
  formula-per-contract (publicly ~7% of p·(1−p) on many categories, category
  schedules vary; one 2026 trade-press headline pegs both venues near a $1.75
  cap per contract for some categories — verify per category before sizing);
  Polymarket taker 0 unless `feesEnabled` (we flag those per market already).
- **EV: B (vendor-grade but quantitative).** ArbBets 2026 report: 9.5% of
  matched markets contain a profitable arb per scan, median fee-adjusted ROI
  **2.1%**, stable across 6 snapshots Dec 2025 → Aug 2026 — i.e. the film
  *renewed itself* through 2026 (crowding has not killed it; fees have
  compressed it to low-single-digit). QuantPedia's cited price-discovery study
  says the windows are seconds-to-minutes on fast political questions —
  consistent with the residual surviving in slow questions.
- **Caveats.** Install/identity friction and fees on Kalshi are the whole edge;
  the medians are ROI-on-stake for scanner-sized fills at snapshot time, not
  continuous capture; the report only names resolved/aged examples. The
  mirrored US/"Iceland book" variant (same franchise question on both books)
  has resolution-clause mismatch risk the vendors themselves flag.
- **FIT: partial.** Polymarket side is fully ours (books + fees + negRisk).
  Kalshi side needs a REST snapshot poller (public endpoints). No Etherscan
  pulls needed.
- **COST: medium (~1–2 d of plumbing + a 24-h collection window). NOVL: clean.**
- **Test (this-week shape).** `scripts/research/kalshiSpread.py`: match by
  explicit slug→Kalshi ticker map for ~200 slow questions (politics dates,
  crypto thresholds, sports futs, military-adjacent won't usually match);
  collect snapshots every 5 min for 48 h; compute fee-adjusted
  (Kalshi-fee formula + `feesEnabled` taken) both-direction arb rate, size of
  gaps at the 10th/50th/90th percentile of persistence time, and share of
  arbs still open after 10 min (is this a humans-can-chase film or a bot film?).
  Kill: if fee-adjusted arbs with ≥10-min persistence are < 2% of matched
  pairs over 48 h → the retail-chasable film is absent → dead for us; if the
  film is there but the median ROI < ~1% AND resolution-clause mismatch rate >
  ~5% → dead for anyone honest.

### (c) Post-burst continuation across categories (the control cell says momentum is real — we only ever tested *copying longshots*)

- **Mechanism.** A ≥$10k burst moves the book and the tape records follow-through
  for hours-days as slower books/retail converge. The +1.1% / 90.9% control cell
  says the *event* carries continuing information; we already know the
  6 h→1 d→resolution return ladder from `priceMove.md` (0 h +2.9%, +30% by 6 h
  on the suspicious set) and `newsAnchor.md` puts all military edge post-news.
  We have never cut this axis by **category on non-military books**, nor tested
  favorite-side / mid-price-band continuation as a *direct* taker strategy
  (not an insider-copy gate). `favoriteBursts.md` covers the favorite-copy
  family pre-registration but its verdicts run on the military slugs only.
- **EV: A− internal, corroborated.** Internal control cell n=16,896 OOS is the
  single strongest measured continuation fact on this project's tapes. External:
  the FLB/convergence evidence (sturzael §sports + Betfair/Azuro baselines)
  is the same convergence-to-truth mechanism near close; longshot-bias studies
  say the *underdog side* of the book is systematically the wrong side —
  continuation favors the side retail underprices.
- **2026 verdict prior:** plausible survivor. It is also the most frequented
  idea in the ecosystem (every bot vendor demos momentum), so the fast slice
  (seconds-minutes) must be assumed dead; the slice we can actually execute is
  the tape-delayed 5-min→6 h slice on liquid books, which is exactly what our
  delay-realistic pricing models.
- **FIT: maximal.** All dirs in hand; `entrySweep` grid axes (minUsd, price
  bands, age, marketsSoFar) already exist; only the dir scope and the price
  band surface change.
- **COST: low (~half a day of sweep runs, machinery is `entrySweep --data-dir`).**
  NOVL: **partial but separable** — this is the control-cell axis executed
  directly, explicitly NOT the ≤0.35 longshot copy (bands [0.35,0.55), [0.55,0.85)
  and >0.85 are the new surface; military slugs stay EXCLUDED from the
  candidate surface to avoid re-litigating the falsified cell).
- **Test (this-week shape).** `scripts/research/postBurstContinuation.py` —
  a thin wrapper (oosTransport style) around entrySweep internals: grid over
  minUsd ∈ {$2k,$5k,$10k} × burst-avg price band ∈ {[0,0.15), [0.15,0.35),
  [0.35,0.55), [0.55,0.85), [0.85,1.0]} × hold horizon ∈ {T+60m fair-value
  exit via mid prints, hold-to-resolution} on `data/oosExpansion` first
  (all-military — treat as pilot only), then on `data/universe` (86 events
  mixed-category) as the category-generic test; military slugs dropped from the
  universe cut by the shipped tuple. Report the full pre-registered gate set.
  Kill: any band with n ≥ 20 events, delay-realistic p5 ≤ 0 or top-event share
  ≥ 60% → band dead; if ALL bands at hold-to-resolution fail on the 196-event
  fresh holdout with delay-realistic pricing → family dead OOS (the control
  cell stays what it is — a non-executed whole-burst average).

### (d) negRisk date-ladder flow conditioning — front-running the predictable hedge

- **Mechanism.** In a negRisk event, a large BUY of one leg mechanically impels
  the negRisk-aware exchangers/MMs to rebalance: they convert No to the whole
  sibling basket (adapter conversion), quote-skew all sibling legs opposite,
  and arb the parity. If a big BUY on leg X arrives, other legs should
  (transiently) sell off / fill in a predictable direction. A taker standing
  on the sibling side just before/at conversion flows captures the forced-flow
  premium without any insider hypothesis at all.
- **EV: C+ honest.** No published quantitative demonstration found. Mechanism
  documented at practitioner level (dev.to piece: inventory skew across the
  negRisk group, auto-convert(), parity monitoring); the arb persistence stats
  (median 1-min windows ending on a single taker) imply conversion/flow capture
  is consumed *fast*. Internal color: `sampleReview.md` found date-ladder
  sprays as the speculator tell — i.e. ladder-leg flow is rich, linked, and
  exactly the shape this family conditions on.
- **2026 verdict prior:** unresolved-by-evidence; cheap to decide. The film, if
  real, is minutes-scale (bounded by the 1-min arb-window median) — an execution
  edge, sized in bps, capacity small.
- **FIT: strong.** Fills tapes carry every leg; negRisk flag on markets;
  co-trading links already built.
- **COST: low (~a day). NOVL: clean.**
- **Test (this-week shape).** `scripts/research/ladderFlow.py`: in ladder-negRisk
  events (detect via >2 sibling markets sharing an event, `negRisk=true`),
  event-study around each ≥$5k BUY burst on one leg: sibling-leg mid evolution
  at T+[60s, 5m, 15m, 60m] with matched controls (sibling legs without the
  trigger leg's burst, same event-day). Kill: if the mean drift laid
  on the *hedge-anticipated side* is ≤ 0 net of 50bps round costs at every
  horizon, or P(>0) < 60% with n ≥ 20 trigger events → dead. If positive but
  < 50bps → not worth live plumbing → archive.

### (e) New-account deposit morphology — the funding event itself as signal

- **Mechanism.** A ≤3-day-old wallet that receives >$50k then trades ONE market
  is the documented insider *shape*. The deposit is visible before the first
  fill (funding tape), so conditioning on deposit size — not fill size — moves
  the trigger earlier and is a different variable than the falsified
  "fresh longshot ≤0.35 burst copy" (which gated on fill price band on
  military events). Same shape at discovery level (precision) is documented:
  our own `verdictBenchmark` (fresh ≤7d + ≥$5k = 55–75% recall) and Bitquery's
  insider API codify fresh+funded+concentrated.
- **EV: B−.** No public backtest of *deposit-gated* copying found; vendor tools
  (Bitquery, whaletracks Insider Radar, WalletRadar's 19.5M-trade taxonomy)
  assert shape detection but publish no OOS return series. Our internal
  credibility is real but the fresh-account copy family FAILED OOS universe-wide
  and on both military pulls — the honest prior is that any residual deposit
  edge is event-episodic (Iran-style) and may not transport.
- **2026 verdict prior:** leaning dead as a *copy strategy*; possibly useful as
  a discovery-precision input rather than a signal. This test exists mainly to
  write a clean tombstone on the deposit-gated variant.
- **FIT: strong — with one hard constraint: NO NEW ETHERSCAN/RELAY pulls.**
  `funding.parquet` + `firstTs` exist for all three dirs; the test must run on
  pre-funded fields only (3 r/s Etherscan is out; waterfall pulls out).
- **COST: low (~4–6 h). NOVL: NEAR-MISS — explicit non-overlap protocol:** the
  candidate gate is `first-funding ≥ $50k AND ≤72h between first-funding and
  first fill AND marketsTraded ≤ 2`, with NO price-band filter (the ≤0.35 band
  is the falsified axis); graded on `data/oosExpansion` (the deciding holdout)
  and `data/universe` separately.
- **Test (this-week shape).** `scripts/research/depositMorph.py`: reuse the
  entrySweep cache; derive per-account first-funding USD at trigger time from
  the cached funding scores (no on-chain calls); gate burst candidates on the
  deposit condition; grade with the standard PASS/FAIL gates + delay-realistic.
  Kill: any deposit-gated cell failing p5 > 0/P(>0) ≥ 85% on the 196-event
  holdout → dead as a copy signal (record as discovery-only residue); if the
  gated population is < 20 events across all dirs → INCONCLUSIVE, do not
  spend execution infra on it.

### (f) Overnight / quiet-hours books (US-nighttime liquidity vacuum)

- **Mechanism.** Two films: (1) books that materially misprice during hours US
  retail is asleep and book depth is thin (Europe/Asia-driven events, crypto
  thresholds crossing at night); (2) predictable providers absent on weekend
  nights (Lookonchain's documented $233k weekend-night drain is the extreme
  version; its middle form is simple spread/depth capture, not manipulation).
- **EV: C (anecdote + one structured analogue).** The Lookonchain case is a
  single documented exploit (Jan 2026), and its soft targets hardened within
  days — antisurvival evidence for the *manipulative* variant. sturzael's e26
  (Hyperliquid, adjacent venue) found the residual retail path is "niche
  inventory management in the 03–12 UTC band," i.e. the quiet-hours liquidity
  premium exists but is a bookmaking edge, not a taker edge. No published
  study of hour-of-day depth on Polymarket books found.
- **2026 verdict prior:** the violent variant is decayed; the measured variant
  (depth/spread/quote-quality by UTC hour on our 1,330 open military books and
  wider) is unmeasured on our side and cheap to measure. Expected verdict: a
  microstructure finding worth having before any MM future, low direct alpha.
- **FIT: strong.** Watcher infra can snapshot CLOB books on the open markets
  hourly without touching `data/live` (separate state file).
- **COST: medium (24–72 h of passive collection + 1 day of analysis). NOVL: clean.**
- **Test (this-week shape).** `scripts/research/quietHours.py`: hourly depth
  capture (best-bid/ask + top-5 levels) on the 1,330 open markets + the 200
  largest open non-military, for 48 h; join to resolution-impactful events
  occurring 02:00–10:00 UTC vs US-hours. Kill (documentary, not alpha): if
  median top-of-book size at night ≥ 50% of the daily mean and night-time
  post-news burst mispricing ∝ nothing, the vacuum is folklore → archive;
  if vacuum exists, the follow-on alpha test is passive resting-liquidity
  *backtesting* against the tape, not taker signals.

### (g) Whale cash-out front-running (tracked clusters SELLING)

- **Mechanism.** Our funding tracing + co-trade clusters see deployments AND
  (unlike RT-only stacks) original funding; when a *known, winning* cluster
  begins selling its position before resolution (cash-outs early / flips), the
  share of informedness in the book drops. Front-running their exits =
  fade-their-fade: buy what they dump IF their dump is liquidity-constrained
  liquidation rather than information. The falsifiable form: does a
  tracked-cluster SELL burst precede systematic *price decay to resolution*
  (they're cashing richer odds with no news) or *price survival* (exit on news
  already priced)?
- **EV: C (honest: weakest of the set).** Public products exist that track
  whale positions with verified P&L (cohven, polytrace, kairos) but none
  publishes an exit-front-running edge study; the wash-trading finding
  (Columbia/Kanoria: up to ~25% of volume possibly artificial) makes naive
  whale-volume chasing unreliable. Internal precedent cuts AGAINST transport:
  what a flagged account does after its win "is not informed"
  (`freshAccountSignal.md` — the exact anti-pattern for copying cluster exits).
- **FIT: strong (clusters, fills, funding all in hand).**
  **COST: low–medium (~1 day). NOVL:** adjacent to a dead family (post-win
  copying) — the differentiator must be the SELL-side trigger, not the
  account flag.
- **Test (this-week shape).** `scripts/research/cashoutFade.py`: for every
  co-trade-clustered account (from the existing cluster edges), find first
  SELL ≥ $5k after a net long build; event-study the market mid at
  T+[1 h, 6 h, resolution], split by whether the market carries a ≥$10k BUY
  burst in the same 24 h (informed exit vs liquidation). Kill: if
  fade-their-fade retReal (hold-to-resolution) p5 < 0 on ≥ 20 trigger events
  in the OOS holdout → dead; if the split shows the effect only appears
  clustered on 1–2 events → record as episodic, dead OOS, consistent with the
  known episode-concentration failure mode.

### (h) Sports category scan — favorites at T-7d on game books (the best-published retail edge we have NOT falsified)

- **Mechanism.** Sports game-outcome favorites priced 0.55–0.60 seven days
  before a game resolve YES at ~+25–30pp above the implied read
  (sturzael e16/e23: yes_rate 0.875 at 0.575-implied, z=5.1–7.6; cross-venue
  control says Betfair/Azuro show ≤±6pp at their own close-anchored windows —
  so the effect is specifically the thin, retail-dominated, T-7d anchor on
  Polymarket-style early listing). Mechanism candidate: early books are
  retail-biased, and the favorite side is systematically underpriced before
  sharp/late flow converges it.
- **EV: A−.** Above-average credibility: pre-registered num, large on-chain
  corpus, cross-venue falsification attempt, live scanner deployed by the
  author (the same repo killed all ten of its other ideas — the methodology is
  default-to-kill). Note the internal tension: n=32 (e16) / 120 (e23 bucket);
  the Smarkets-agreement check (n=5 in-bucket) is thin; the paper's own
  ÷5-adjusted planning number is $4–11k/yr on $5–25k — a real but small edge.
- **2026 verdict prior:** untouched by our OOS kills (military-only tape so
  far). Risk: it is now publicly documented (the repo is indexed by search),
  so decay is possible since 2026-04 — this test doubles as a decay check.
- **FIT: partial → needs one small fetch.** Our fills are military-heavy by
  construction (the 15-keyword tuple); sports game books inside
  `data/universe`/`data/raw` exist only as incidental fills (recreational
  tell analysis). A sports-only sweep needs a Gamma crawl by sports tags
  (closed=true, resolved game markets, MLB/NBA/NFL/NHL + majors) — same CRAWL
  mechanics as the oosExpansion roster build, quarter-size pull, NO rate-limited
  chain calls, NO touching `data/live`.
- **COST: medium (~1 day crawl + half day sweep). NOVL: clean** (and it is the
  one falsification the ecosystem evidence says should PASS — worth spending
  OOS discipline on).
- **Test (this-week shape).** `scripts/research/sportsFavT7d.py`: crawl ~1k
  resolved game markets (any sport with ≥$5k window volume), join fills;
  at T-7d±12h snapshot each book's favorite mid into the ladder
  [0.45,0.55), [0.55,0.65), [0.65,0.75); compare realized YES-rate vs implied
  mid, per sport, with SU sport-cluster bootstrap; entry = buy favorite at
  mid next print (delay-realistic, next-print fill + 50bps), hold to resolution; report
  calibration gap AND tradeable ret with 50bps costs. Kill: if the 0.55–0.60
  band's calibration excess is < 8pp (i.e. decayed to half the cited 25.8pp) or
  tradeable ret p5 < 0 on ≥ 100 games → dead (record as citation-confirmed
  decay); if excess survives ≥ 15pp → the whole family graduates to a live
  scanner design doc.

### (i) Long-duration sum-violation captures in thin books (negRisk sum < $1, hours-to-months)

- **Mechanism.** Buy the full basket for < $1 where the violation persists for
  ≥ several hours (sturzael: 2.2% of events, thin/low-attention books), funding
  the capital lockup.
- **EV: B−.** Same corpus as (a); sturzael's live finding: structural remainder
  ≤3% edge, multi-month lockups, ~$400–900/yr/$1k — below execution risk for
  retail/non-atomic multi-leg at their scale. Honesty note: this is the
  "expected to die" complement of (a); listed because our negRisk tapes make
  it free to check ON THE TAPE level we hold.
- **COST: near-zero (piggybacks Test 1 of family (a) — same script,
  different persistence cut). NOVL: clean.**
- **Kill-criterion:** every detected ≥6-h violation on the holdout tapes with
  non-phantom verification (tail risk excluded via "all listed siblings sum ≥
  0.97 across the record") yielding < 1%/yr-equivalent → dead for our capital
  scale; phantom-density > 50%·detections → method must add off-tape tail checks
  to be usable at all.

---

## 3. Ranked shortlist (top 5)

Ranked by evidence × cost × non-overlap. Each: first test spec, verdict
timeline (from start of the test run, not including analyst debate).

### #1 — (c) Post-burst continuation, direct taker, non-military + favorite/mid bands

- **Why on top:** the only candidate whose decisive evidence is an OOS-grade
  number we already own (control cell +1.1%/90.9%, n=16,896), machinery already
  written (`entrySweep` + `oosTransport` + `favoriteBursts.md` grid), zero new
  data, zero chain calls. Execution slice (delay-realistic, 5-min-window entry)
  is bounded and honest.
- **First test:** `postBurstContinuation.py` sweep as spec'd in §2(c): price
  bands [0.35,0.55)/[0.55,0.85)/[0.85,1.0] × usd {$2k,$5k,$10k} × horizon
  {T+60m, resolution} on `data/oosExpansion`, then `data/universe` with military
  slugs excluded. All pre-registered gates + delay-realistic grading.
- **Kill:** the standard gate per band; family dead if all delay-realistic
  bands p5 ≤ 0 on the holdouts.
- **Evidence:** internal control cell; `priceMove.md` 6h-ladder; QuantPedia
  arb/behavioral survey for the convergence mechanism; sturzael FLB for the
  underpriced-side asymmetry.
- **Verdict timeline: 1–2 sessions (~1–2 days wall).**

### #2 — (h) Sports favorites at T-7d (sturzael e23 replication + decay check)

- **Why:** the strongest *published* retail edge in the corpus, pre-registered,
  cross-venue controlled, and in a category our canvases deliberately skipped
  (citation: z=7.6, n=120 bucket; planning $4–11k/yr on $5–25k). Also the best
  test of the "documented edges decay" thesis — the study is from 2026-04.
- **First test:** sports crawl (Gamma by MLB/NBA/NFL/NHL + majors tags,
  resolved game markets, ≥$5k window volume, ~1k markets; same crawl adapter as
  the oosExpansion roster) + `sportsFavT7d.py` calibration/ret sweep per §2(h).
- **Kill:** Δcalibration < 8pp in the 0.55–0.60 band OR tradeable ret p5 < 0 on
  ≥ 100 games.
- **Evidence:** sturzael repo + `SYNTHESIS_flb_cross_venue.md` (links above);
  longshot-bias literature (QuantPedia §longshot; football favorites-outsiders
  returns).
- **Verdict timeline: ~3–5 days wall (crawl + sweep + sport-level bootstrap).**

### #3 — (d) negRisk date-ladder hedge-flow conditioning

- **Why:** novel (no published test found), fully in-tape, dual-value: a live
  result also refines our burst-entry execution model in ladders (our shipped
  market shape is negRisk-dense military ladders) even if it fails to trade.
- **First test:** `ladderFlow.py` sibling event-study vs matched controls,
  T+[60s, 5m, 15m, 1h], ≥$5k trigger leg bursts, 50bps round costs, per §2(d).
- **Kill:** hedge-side drift ≤ 0 at every horizon (net of costs) or
  P(>0) < 60% at n ≥ 20 triggers; archive if positive but < 50bps.
- **Evidence:** dev.to negRisk mechanics + adapter conversion; sturzael
  1-min-window consumption stats (upside bound); internal ladder-spray
  observations (`sampleReview.md`).
- **Verdict timeline: ~2 days wall (it shares the entry cache with #1).**

### #4 — (b) Polymarket ↔ Kalshi spread persistence test

- **Why:** the only family with a numerically renewing public record through
  Aug 2026 (9.5% arb rate per scan, median 2.1% fee-adjusted ROI). It is a
  *market-plumbing* question (48 h of snapshots) before any capital question,
  and it prices the crowding/decay question directly (persistence ≥ 10 min?).
- **First test:** `kalshiSpread.py` 48-h 5-min snapshot poller over ~200
  matched slow questions; fee-adjusted both-direction arb rate; persistence
  histogram; resolution-clause mismatch census per §2(b).
- **Kill:** < 2% of matched pairs with ≥10-min persistent fee-adjusted arbs →
  retail-chasable film absent → dead; clause-mismatch rate > ~5% → dead for
  honest books regardless.
- **Evidence:** ArbBets 2026 report; QuantPedia's price-discovery survey;
  vendor scanners (predterminal, skreenr, predictmarketcap) as existence
  proofs, not numbers.
- **Verdict timeline: ~4–6 days wall (plumbing + collection + analysis).**
  Note Kalshi fee schedule must be verified per category from their official
  schedule before any ROI number is trusted.

### #5 — (a)+(i) Stale-sibling / residual sweep on the tapes (expect-kill, nearly free)

- **Why:** the literature consensus is that this film collapsed to sub-100 ms
  operators in liquid books; but our negRisk fills + resolutions make the
  *offline* check a half-day, no new risk model, no chain calls — a cheap
  tombstone or a bounded thin-book tail discovery (2.2% ≥24-h persistence).
- **First test:** `negRiskStale.py` time-to-reprice + stale-window census at
  sibling resolutions across `data/oosExpansion` + `data/universe` per §2(a);
  persistence cut per §2(i).
- **Kill:** non-phantom capturable violations ≥2% with ≥$100 taker depth in
  < 1% of resolution events → dead; phantom-density > 50% → paper-trail note
  only.
- **Evidence:** Saguillo et al. ($40M, window collapse); sturzael persistence
  forensics (median 1 min, long-tail 2.2%).
- **Verdict timeline: 1–2 days wall.**

### Report-card table

| family | EV | FIT | COST | NOVL | prior | rank |
|---|---|---|---|---|---|---|
| (c) post-burst continuation | A− (internal) | max | low | partial-separable | plausible live | **1** |
| (h) sports T-7d favorites | A− | partial (crawl) | medium | clean | live, decay risk | **2** |
| (d) ladder hedge-flow | C+ | strong | low | clean | unresolved, fast | **3** |
| (b) Kalshi spreads | B | partial | medium | clean | live, fees compressed | **4** |
| (a)/(i) residual sweep | A− (negative-directed) | strong | near-zero | clean | expected dead | **5** |
| (e) deposit morphology | B− | strong (no chain) | low | near-miss | lean dead | 6 |
| (g) whale cash-out fade | C | strong | low–med | adjacent-to-dead | lean dead/episodic | 7 |
| (f) quiet-hours | C | strong | medium (passive) | clean | folklore probe | 8 |

### Sequencing note

#1, #3, #5 share one entry cache; #2 shares the crawl adapter with the
oosExpansion builder; #4 and #6–8 are independent. If run in
three parallel sessions the whole shortlist is falsified-or-promoted within a
week, without touching `data/live`, without a single Etherscan/Relay call,
and with every verdict pre-registered. Honest expectation: 1–2 of the five
survive their first kill-criterion, and the most likely survivor is #1
(because its decisive evidence is already OOS-internal) or #2 (because it was
never tested here at all).
