# PolyCrawler2 — status & handoff (2026-10-08)

Where the project stands, what every experiment found, and what to do next.
Written as a fresh-session handoff: everything below can be re-derived from the
files referenced, but the conclusions are already pulled out.

## 1. What the project is

Backtest-first rework of PolyCrawler: find insider-style Polymarket wallet
clusters, then copy their net exposure with a realistic delay. Spec is
`SPEC.md` (v0.2 draft). Rule of the project: no live code until backtests show
an edge; discovery only uses data before `splitDate`.

Pipeline: `pc2 fetch → data/*.parquet → discover → parents.parquet → backtest / sweep`.
`backtest` and `sweep` engines exist (commit b7ba385: streaming entries, no
lookahead, per-event objectives, rolling windows). Relay origin tracing is
implemented but partial (commit 700c05b).

## 2. Datasets

| Dataset | Contents | Size |
|---|---|---|
| `data/` (insider cases) | Iran strike ladder + Venezuela: markets, fills, funding, clusters | fills ~120 MB |
| `data/universe/` | 85 events, 3.9M buy entries (rolling backtest universe); 3647 candidate accounts → 89 suspicious at the latest run | fills.parquet + markets.parquet + suspicious.parquet |
| `data/raw/` | cached activity, etherscan, events, relay, trades | |
| `research/knownWallets.csv` | labeled insider wallets used for recall checks | 9 wallets |

Latest universe discovery run (`logs/discoverUniverse.log`, Oct 8 13:19):
3647 candidates after the winning-bet prefilter (avgBuyPrice ≤ 0.7), 89
suspicious, ~20 min, ~4 GB RSS.

## 3. What's been tested, and what it showed

### 3.1 Manual review of 20 flagged accounts — `research/sampleReview.md`

Sample: 20 accounts, `seed=7`, from the 236 flagged by step 1 on
`configs/insiderCases.yaml` (all Iran-ladder, so verdicts are event-specific).
Dossier generator: `scripts/research/accountDossiers.py`.

- **Tally: 8 insider / likely-insider, 4 possible, 8 speculator → step-1
  precision ≈ 40–60%.**
- 4 of the 8 form a **six-wallet co-trade cluster** (Lettucehead718, DimBull,
  suffix-295, wannabesedated, gulligan784, cokelight): same-second fills,
  first Feb-28-Yes buys within ~3 hours of each other on Feb 27. Co-trading
  recovered the Bubblemaps cluster **without any funding data**.
- Cleanest insider profile: fresh account, 1–2 markets, one large ticket.
- Speculator tell: date-ladder spray (many early dates, losing them) and
  recreational bets (sports, GTA 6) mixed in.
- Timing: insiders entered 4–36h before resolution; speculators 8–24 days.

### 3.2 Rolling monthly copy test of 5 flag rules — `research/discoveryIdeas.md`

`scripts/research/discoveryIdeas.py`. Each month Oct 2024 → Sep 2026: flag
with only past data, then copy that month's buys ($100 at the insider's price,
settled at resolution). Rules A (fresh longshot, current), B (repeat winner),
C (late & informed), D (high past return), E (concentrated) vs baseline.

- **Nothing makes money outside the Iran/Venezuela events.** Best is E
  (concentrated) at −9%; current rule A is −41%, about the same as copying
  *anyone's* big longshot (−45%).
- Every positive mean comes from a few huge longshot payouts in Iran.
- The ≤ 0.35 entry filter hurts (favorite–longshot bias).

### 3.3 Feature refinements + same-topic copying — `research/freshAccountSignal.md`

`scripts/research/discoveryIdeas2.py`, `freshAndTopic.py`.

- Adding the manual-review features (ladder precision, no losing ladder bets,
  ≤ 72h lead time, co-trades) to rule A made returns **worse** (−41% → −59%
  to −72%). Conclusion: **an insider's edge belongs to one event; what a
  flagged account does after its win is not informed.**
- Same-topic copying (copy only markets sharing the winning bet's topic tag):
  −32% vs −44% off-topic. Less bad, still negative.
- **Fresh-account first-bet copying** (fresh = ≤ 3 days old, ≤ 3 markets, no
  win required — so no hindsight): best variant is **fresh ≥ $5k at ≤ 0.50:
  +8%** (563 copies, 13/49 events in profit). But fragile: −9% without the
  top event, −44% without top 3, flips sign across time halves (+36% then
  −36%). Fresh ≥ $20k at ≤ 0.50: +1%.
- Best events were Yoon's removal, Biden dropping out, ZachXBT/Axiom.

### 3.5 Verdict benchmark of step-1 variants — `research/sampleVerdicts.csv` + `scripts/research/verdictBenchmark.py`

The 20 manual verdicts are now machine-readable and the seed=7 sample is
reproduced exactly by the script. Ground truth: 4 insiders (the co-trade
cluster), 4 likely insiders → 8 loose positives.

- Rule A as-is: 40% precision loose / 20% strict (recall 100% by construction).
- **One-shot (`marketsTraded ≤ 1`): 100% precision at 25% recall — but it
  only catches the *likely* insiders; all four cluster members trade 5–12
  markets and are dropped.** So "one-shot" and "cluster member" are disjoint
  insider shapes; a good rule needs both paths (one-shot OR co-trade).
- `buyUsd ≥ 5k` alone: 55% / 36% at 75–100% recall — the cheapest win.
- `fresh ≤ 7d + ≥ $5k`: 55% loose / 36% strict at 75% recall. Best combined
  gate; matches the fresh-big-bet copy result in §3.3.
- Deep-longshot gating (`avgBuyPrice ≤ 0.20`) is anti-predictive here.

### 3.6 Copy-time lead gate — `research/leadGate.md` + `research/universeVerdicts.csv`

Second 20-account verdict sample from the universe (seed=8), plus a copy-time
lead gate test. Headlines:

- **Lead time separates insiders from speculators in both labeled samples**
  (all positives ≤ 68h, all speculators ≥ 544h in the universe sample;
  `lead ≤ 168h + mkts ≤ 3` = 100%/100%).
- Gating *copies* (not flags) on `resolvedAt − bet ≤ 3–7d` lifted rule A from
  −41% to +2–5% ex-Iran/Venezuela — first non-negative result ever — but it
  fails robustness: sign flips across time halves, bootstrap P(>0) 46–77%,
  and 5% slippage pushes everything ≤ 0. The late copies are mostly 0.95+
  favorites, not longshots.
- Verdict: lead time is a real *discovery* signal (add to step-1 scoring);
  as a copy strategy it is dead ex-military. Standing conclusion unchanged.

### 3.4 Overall conclusion so far

Outside military/strike-timing events, nothing tested is reliably profitable.
Insider edge clearly exists on military and strike events — clusters show up
there and the fresh-big-longshot profile fits — but that category was
deliberately under-sampled in the universe. Next test already sketched in
`research/freshAccountSignal.md`: category-specific strategy (fresh-big-bet +
co-trade clusters) on military/strike events only, fetched across many such
events, validated with event-level resampling.

## 4. Uncommitted work in the tree

- `src/polycrawler/discovery/` (new package): `activity.py`, `flagging.py`,
  `funding.py`, `links.py` — step-1/step-2/step-4 logic split out of the
  monolithic `discovery.py`.
- `src/polycrawler/http.py`: shared rate-limited HTTP helper expanded
  (fetchMany shared limits, backoff changes).
- `configs/base.yaml` + `config.py`: one added key. `fetch.py`: 55 lines
  removed (logic moved).
- Nothing staged; commit when the discovery split is import-clean and tests pass.

## 5. Next steps (in order)

1. **Benchmark flag rules against the 20-account ground truth.** DONE for
   both samples — `research/sampleVerdicts.csv`, `research/universeVerdicts.csv`,
   `scripts/research/verdictBenchmark.py` (results in §3.5, §3.6). Remaining:
   verdict a third sample once the military-category universe exists, so the
   precision benchmark covers the category where insiders actually cluster.
2. **Fold lead time into discovery step 1.** DONE — `maxFlagLeadHours: 168`
   added to `DiscoveryConfig` and wired as a **hard gate** (not a 5th
   signal: on ladder events speculators also buy the winning date late, so
   counting it inflates the pool) in both `discovery.py` and
   `discovery/flagging.py`. Verified against both labeled samples with
   recall intact:
   - Iran sample: 236 → 151 flagged; precision 40% → 57% (recall 8/8).
   - Universe sample: 89 → 36 flagged; precision 20% → 67%, zero
     speculators flagged (recall 4/4).
   Also restored the two Alchemy helpers (`fetchErc20Transfers`,
   `alchemyBlockNumber`) the WIP refactor had dropped from `fetch.py`,
   which had left `discovery.py` unimportable; all 66 tests pass.
3. **Military-category universe.** DONE — 9 sibling events fetched
   (`configs/militaryUniverse.yaml`, 1.95M fills, universe = 81 events).
   The category-specific test ran (`research/militaryCategory.md`,
   `scripts/research/militaryCategory.py`) and is the **first robustly
   profitable configuration**: fresh ≥$5k ≤0.50 on military events returns
   +71% (+82% with realistic next-tick fills), P(>0) 97%, positive in both
   time halves, survives 10% slippage. Live config is written up in the doc;
   next is packaging it into the strategy/backtest engine and paper trading.
4. **Finish the Relay origin tracing** (commit 700c05b left lookups partial)
   so step 3 works end-to-end on the universe; note the v2 route retires
   24 Nov 2026 — after that, origin tracing needs a new source.
5. **Wire the backtest/sweep engines to the new discovery package** and run
   the first real config sweep (spec §8); ranking metric still undecided
   (total PnL vs PnL / max drawdown, spec §12.4).
6. Commit the uncommitted work once tests pass.

## 7. Session 2026-10-14/15 update

Progress against the list above:

1. **Committed** (`5ca33c1`): the whole 2026-10-09 week — discovery package,
   lead gate, RTDS watcher, V2 execution port, 10 new tests. `775f176`
   followed same day: paper-gate fix, on-chain order-burst rebuild, engine
   rule knobs, CLI wiring.
2. **Paper gate fixed.** Nothing was broken: all 8 signals sit on long-dated
   markets (Oct 28/31 + Jan 2027) so realized P&L is empty by design. New
   `scripts/paperMarkToMarket.py` (wired into `dailyCatchup.sh`) writes
   `data/live/openPositions.csv` each run — full signal context (burstUsd,
   avgPrice, ageDays, askSize) plus mark price and unrealized P&L — so the
   gate gets daily signal long before resolution. First book: 8 positions,
   $800 committed, −$33.76 unrealized.
3. **Dune order_burst rebuild → on-chain.** DUNE is Cloudflare-blocked for
   browser + needs a key we don't have; `api.relay`-style workarounds
   considered and the Dune SQL route replaced by a direct Polygon log pull:
   `scripts/research/orderBurstOnchain.py`. Verified against the contracts:
   ctfExchangeV1 (2022-09), negRiskExchangeV1 (2023-11-28), ctfExchangeV2
   (2026-03-31, explicit `Side` word), negRiskExchangeV2 (2026-04-03),
   exchangeV3 (2026-05-26). V1 era pulled via Etherscan V2 (10k page ceiling
   → range bisection; rate cap 3/s → retry), V2 era via Alchemy 10-block
   getLogs windows. BUY legs joined to fills.parquet ground truth by
   (txHash, wallet, shares, usd). Sample plan: 2 seeded days/month.
   Progress: 2023-10 → mid-2025 cached in data/raw/dune/onchainBuy_*.csv;
   full V2-era spread comes in background. Analysis runs after pull.
4. **Relay origin tracing end-to-end on the universe**: DONE — the full
   `pc2 discover --config configs/eventUniverse.yaml` run completed
   (2h25m, mostly Relay rate-limit pacing: 241 rate-limit backoffs). 144
   bridge deposits → 142 origins resolved (2 unresolved), 142 origin users
   across 10 chains (base 49, BSC 12, bases 13, avalanche 10, arbitrum,
   op-stack, blast...), 170 sibling recipients (28 outside the flagged set,
   17 first funding after the split), 6 clusters (largest: 28-account
   coTrade cluster), 383 coTrade edges. Solver payout re-verified on-chain
   via Alchemy (payoutConfirmed True). Route logged before the 24 Nov 2026
   v2 retirement; data captured under data/raw/relay/.
5. **Engines wired + military rule folded in.** `pc2 backtest` / `pc2 sweep`
   now drive the real engines; `BacktestParams`/`StrategyConfig` gained
   `maxAccountAgeDays`, `maxMarketsSoFar`, `eventSlugFilter`,
   `accountSelection: rule` (rule mode derives accounts from the fill tape
   itself — the research rule flags the account, not a step-1 suspect list).
   Validation config: `configs/militaryBacktest.yaml`; grid:
   `configs/sweeps/military.yaml`.
   **Open anomaly (2026-10-15):** rule-mode engine backtest over the full
   window comes out −19.4% (136 trades, 20 events) while the research
   pipeline's fresh ≥$5k cell was +71%. Recheck of the research sweep on
   today's refreshed universe fills is running
   (logs/militarySweepRecheck.log). Suspects: engine enters at the
   delayed/backward-asof tape price + 50bps and mirrors later fills (adds),
   while the research cell prices with the wallet's own burst average and
   next-tick fills; also possible drift in the refreshed fills.
   **RESOLVED (same session):** three compounding causes found:
   (a) the sweep recheck confirmed the research cell unchanged on refreshed
   fills (+104% ret / +115% retReal, winRate 34.6%);
   (b) intra-burst mirroring (`followAdds`) destroys the edge at mirrorPct
   (`fixed` sizing + `followAdds=false` = paper/live semantics; −19.4% →
   +24.9% on the stale data);
   (c) the stale-data runs were racing `discover`'s parquet rewrite.
   On the FINAL discovery output `configs/militaryBacktest.yaml` reproduces
   the research cell nearly exactly: 429 trades vs 433 entries, winRate
   36.4% vs 34.6%, returnOnDeployed +119.3% vs +116% realistic, 27 vs 29
   events. Engine and research pipelines are now interchangeable for the
   military rule; parity discrepancies from this point are real signal.

## 8. Gotchas learned this session

- Etherscan V2 has a permanent log-index gap for the 2026 CREATE2-deployed
  V2/V3 exchanges; V1 synthesis works (topic filter, 1000/page, 3 calls/s,
  10k page-window → bisect ranges).
- Alchemy free tier caps `eth_getLogs` at 10 blocks per call.
- `Path(__file__).resolve().parents[1]` in `scripts/research/*` points into
  `scripts/`, not the repo root (`parents[2]` needed) — bit both
  `duneOrderBurst.py` (dormant) and the new puller.
- `markets.parquet` stores `clobTokenIds`/`outcomes` as native lists, Gamma
  caches store JSON strings — parse both.
- On-chain `OrderFilled` topics: [sig, orderHash, maker, taker]; maker is
  topics[2] (the first indexed arg after the sig), easy to misindex.
- Concurrent jobs (discover re-run) rewrite `data/universe/*.parquet`
  mid-run: never validate an engine backtest against the live data dir
  while discover writes; snapshot first.

## 6. Live paper-trading system (2026-10-09)

Built and running (see `research/militaryCategory.md` for the validated rule):

- `scripts/liveWatcher.py` — continuous tape watcher over open military
  markets; fires the sweep-selected rule ($5k burst, ≤0.35, fresh ≤5d,
  ≤3 markets) and logs alerts with CLOB book sizing to
  `data/live/signals.csv`.
- `scripts/paperPnl.py` — closes resolved signals into
  `data/live/paperPnl.csv`; run daily by a scheduled report that also
  restarts the watcher if it died.
- `scripts/research/militarySweep.py` — parameter grid; every cell
  profitable, shipped point chosen for stability, not peak return.
- Watcher coverage expanded 2026-10-09: 1,220 open military markets across
  235 events (was 430/108) by widening tags + slug keywords.
- `scripts/execute.py` — execution module, **dry-run by default**. Placing
  real orders requires BOTH `POLYMARKET_PRIVATE_KEY` in the env and an
  explicit `--live` flag; hard caps $50/order, $500 total open; signals
  older than 10 min are treated as stale and refused. Not wired to any
  cron — execution is always a deliberate manual invocation.

**Money-making gate:** let the watcher accrue live paper trades until the
live sample has enough resolutions to compare against the backtest's
+116%-realistic-fill expectation (suggest ≥30 closed signals, or 4 weeks,
whichever first). If live win rate and P&L are consistent, real size is
justified; if not, the discrepancy itself is the finding. Until then, no
real orders.

## 7. Watcher hardening + news-anchor test (2026-10-09)

- `liveWatcher.py` three fixes applied and watcher restarted: (1) `getWithRetry`
  (3 attempts, 1/2/4s) on dataApi/Gamma GETs; (2) one-time `/activity` age
  verification rescues backfill-seen accounts (empty 5d pre-bet window →
  eligible, any prior activity → permanently out, fails closed); (3) fee
  filter — Gamma `feesEnabled` markets skipped (~20% of coverage carried
  10%-base taker fees). All 66 tests pass. Next tape upgrades ranked in
  `research/ideasResearch.md` (RTDS push, `/v2/trades` CASH filters,
  `/v2/resolutions` for paperPnl).
- **News-anchor test ran to full coverage (`research/newsAnchor.md`,
  `scripts/research/newsAnchor.py`): DO NOT add a pre-news gate.** Pre-news
  signals are a small loser (n=16, −22% retReal, P(>0) 26%); the entire
  +117% edge sits in post-news signals (n=412, +122%, P(>0) 98%). Caveat in
  the doc: copied traders look like fast news-riders, not pre-news insiders —
  the enforcement cases describe a different population.
- `execute.py` uses V1 CLOB signing; the April 2026 Exchange-V2 migration
  rejects V1 orders (`400 invalid order version`) — port to a V2 client
  before any real order (`research/ideasResearch.md` #0).

## 8. V2 execution port + RTDS push tape + Dune order_hash script (2026-10-09, later)

Three tape/execution upgrades from ideasResearch.md, all implemented and
verified; **the running watcher still needs a restart to pick up the new
tape** (daily report restarts it):

- **execute.py → V2 signing** (`#0` RESOLVED): now uses the official
  `py-clob-client-v2` 1.2.0 (Polymarket Engineering; the May-era L1-auth bug
  note predates this release). Verified `get_version()` == 2 against the live
  host; book walking / caps / dry-run semantics unchanged; order responses
  checked for `ok: false`. Live orders remain blocked by the paper gate.
- **RTDS push tape** (`scripts/rtdsTape.py`, new): global `activity` trades
  websocket, client-side condition-id filter, reconnect with capped backoff,
  daemon thread → queue → the same evaluate()/alert() path. Wire quirks
  documented in the module docstring (per-event `filters` shapes ack but
  deliver nothing; bare `{"topic": "activity", "type": "*"}` is the shape
  that streams; payload ts is seconds, envelope ms). Sub-second pickup of
  post-news bursts replaces 45s polling.
- **`/v2/trades` CASH≥$5k gap-rescue poll** (in `liveWatcher.py`): every
  120s, one request per 20-market chunk with server-side
  `filter_type=CASH&filter_amount=5000&side=BUY`; watermarks every market so
  quiet markets don't re-enter backfill mode; fills deduped against the push
  tape on (wallet, txHash, side, size, price, ts, market). Sub-$5k fills are
  push-tape-only by design. Old v1 `/trades` polling removed.
- **Dune order_hash burst rebuild** (`scripts/research/duneOrderBurst.py`,
  new): reassembles signed orders from `polymarket_polygon.market_trades`
  (283 military markets, batches of 300 condition ids, CSV cached under
  `data/raw/dune/`) and re-runs the shipped cell with burst-level vs
  order-level ≥$5k definitions + overlap counts. **Needs `DUNE_API_KEY` in
  the environment to run the pull.**
- Tests: 76 pass (10 new: RTDS/ts normalization, v2 row normalization, dedup
  bounds, burst-vs-order entry mechanics on synthetic fills). Watcher was
  exercised end-to-end with a temp state (1,235 markets refresh, full
  backfill, evaluate→alert with /activity age rescue) without touching the
  live process or data/live files.

## 9. Parity made durable + on-chain burst-vs-order + floor ranking (2026-10-15)

### engineParity: the 342-vs-429 drift is a data-scope bug, not engine drift
- `scripts/research/engineParity.py` (new) recomputes BOTH sides on the
  current tape every run; no pinned numbers. Written to
  `data/parity/engineResearchParity.json`.
- Root cause of the earlier mismatch (my ad-hoc rerun saw engine 342
  trades/+143% vs research 427/+105%): `configs/militaryBacktest.yaml` had no
  `fetch` section, so runs used `fetch.dataDir: data` alone (174 markets),
  while the research cell (militaryCategory.py, duneOrderBurst.py, the entry
  sweep) spans `data/` + `data/universe/` (1031 markets; all 2026-era
  markets live only in the universe dir).
- Fix: `FetchConfig.dataDirs` (list, optional) + `dirsFromConfig()` applying
  CLI --data-dir > fetch.dataDirs > fetch.dataDir. Wired into cli.py backtest
  + sweep, scripts/backtest.py, scripts/sweep.py. militaryBacktest.yaml now
  pins `fetch.dataDirs: [data, data/universe]`.
- With both dirs the rule-mode engine again reproduces the research cell on
  the current tape: engine 429 trades / 36.4% / +119.8% vs research cell
  427 entries / 34.7% / (hold-to-resolution) +105.1%.
- Residual buckets (engineParity, current tape): overlap 402/427 (94.1%),
  enginePrefixDrift 5 (engine entered on a legal prefix, later fills pushed
  the burst avg above the gate), notExecutedLegalPrefix 24 (delayed entry
  sweet spot: legal running prefix exists but the delayed fill never landed),
  noLegalPrefix 1, clusterAlreadyCopied 0. The "notExecutedLegalPrefix" 24
  are execution-side losses the whole-burst research cell under-counts —
  when tuning the live rule, remember the cell's own returns benefit from
  entries a delayed copy couldn't have made.

### burst-vs-order on Polygon (Dune replacement), partial read
- `scripts/research/orderBurstOnchainAnalysis.py` (new): reuses
  duneOrderBurst.py's burstEntries/orderEntries/annotate/report on the
  on-chain sampled legs; wallet-age firstTs + realistic-fill tape taken from
  the FULL fills universe (militaryCategory convention — one fix over the
  dune script's military-scoped firstSeen). Report JSON at
  `data/raw/dune/orderBurstOnchainReport.json`, log
  `logs/orderBurstAnalysis.log`.
- Partial day (~29-33 of 74 sampled days cached, ends 2025-02): >=1k
  reference cell order-level dominates on robustness (boot p5 +0.189 vs
  -0.043, P(>0) 98% vs 92%); orders >=$5k spanning >1 burst window only 1/26
  so far. The ≥$5k cell is still thin (n=4-5) — do NOT call it until the
  full pull exits; `scripts/research/orderBurstMonitor.py` waits out the
  full sample plan then fires the analysis automatically
  (`logs/orderBurstAnalysis.log`).
- duneOrderBurst.report: None-safe H1/H2 (sample spans can be half-empty).

### entrySweep: floor-metric ranking is now the default
- `runSweep()` ranks cells by bootstrapped per-event p5 floor (ret only as
  tiebreak), ineligible cells sink. Test proves ordering flips against the
  old ret-descending sort. Recheck log already showed the consequence:
  $10k/≤0.35 cells hold p5 +0.39..+0.57 vs +0.13 for the $5k line with
  ~150-240 trades — candidate for the live watch rule pending more OOS.

### session 2026-10-15 (later): monitor + dirs routing + fingerprint hardening
- The "git note" paragraph of the pre-ec6131f tree (dataDirs plumbing +
  parity tool "uncommitted at session end") was removed by ec6131f itself:
  b153ae3 had already landed the dataDirs routing, parity tool and on-chain
  analysis, so the note read as stale the moment it was reviewed.
- `scripts/research/orderBurstMonitor.py` (new): the promised monitor, a
  single-purpose cron job. It does NOT pull: it polls
  `data/raw/dune/onchainBuy_*.csv` until the puller's own
  `orderBurstOnchain.sampleDays()` plan is fully cached (day list imported,
  not restated; cache-complete mirrors the puller's own skip rule), then
  calls `orderBurstOnchainAnalysis.main()` in-process with its output teed
  to `logs/orderBurstAnalysis.log`. `--timeout-hours` guard exits 1 under
  cron if the pull is still incomplete.
- Data dirs of the four hardcoded research scripts (`engineParity`,
  `orderBurstOnchainAnalysis`, `duneOrderBurst`, `entrySweep`) now resolve
  through `dirsFromConfig()` — CLI `--data-dir` > `fetch.dataDirs` >
  `fetch.dataDir`, engineParity reading the pinned config like the engine
  side; defaults unchanged (data/ + data/universe), classification logic
  untouched.
- entrySweep cache fingerprint hardened: now covers fills + markets parquet
  size, mtime and metadata-only row counts per dir (`entries_v2_` cache
  name, `CACHE_SCHEMA_VERSION` constant) — an equal-size in-place rewrite
  no longer silently reuses a stale cache.
- Today's data jobs: on-chain pull RESUMED (41 of 74+ sampled days cached
  before the resume; remaining days pulling now via the external background
  process, monitor above fires the analysis when it exits); OOS fetch
  (`configs/oosFetch.yaml`) re-attempted in background.

### session 2026-10-15 (later still): two review passes applied (C1–C6)
The bb645e9..ec6131f diff went through two reviews (correctness + design);
both approved fixes are now in, one commit each:
- **C1/c87cbfe** — puller `writeCsv()` writes through `<path>.tmp` +
  `os.replace()` (no more half-written day caches read mid-pull); main()
  publishes the resolved sample plan to `data/raw/dune/samplePlan.json`
  once at startup.
- **C2/6337c3d** — monitor hardening: plan prefers
  `samplePlan.json`, then falls back to the puller's `sampleDays()`; future
  days are filtered out (the old code waited on not-yet-elapsed days →
  guaranteed timeout mid-month); run-once flock on
  `data/raw/dune/orderBurstMonitor.lock` (held → exit 0 with a note);
  completion sentinel `logs/orderBurstAnalysis_<planHash>.done`
  (planHash = sha1 over the sorted FULL plan — stable across a day, re-fires
  only when the puller's plan grows a month); `--per-month` default imports
  the puller's `PER_MONTH` instead of a hardcode; the sys.argv swap hack is
  gone (analysis `main(dir_=...)`); tee log opens with an explicit
  `=== orderBurstAnalysis started … ===` line.
- **C3/4b421c8** — `scripts/research/researchData.py` (new) is the single
  owner of `RESEARCH_FETCH`, `researchDataDirs()`, the military slug tuple,
  `militaryMarketsFrame()`; duneOrderBurst/engineParity/entrySweep/
  orderBurstOnchainAnalysis import it by-path and their duplicates are
  deleted (entrySweep's `militaryMarketsTable` replaced by the shared frame,
  engineParity no longer loads duneOrderBurst just for the slugs).
- **C4/9bc2f73** — analysis `loadLegs` parses each day CSV once (was twice
  for a height check; the day counts now come from that single pass), and
  exits with a clear message when no day has legs instead of polars' concat
  ValueError; `universeFills()` lost its unused `militaryIds` parameter.
- **C5/ecab270** — monitor test repairs landed with C2 (they were coupled:
  the elapsed-day filter invalidated the old equality assertion): the `or
  True` tautology is gone, the sampling contract is pinned
  (`samplePlanDays()[0] == 2023-10-11`, recorded at commit time, live from
  `sampleDays(seed=7)`, hermetic via PLAN_PATH monkeypatch), plus a plan-file
  preference test. entrySweep `dataFingerprint` takes ONE `stat()` per file;
  status.md's self-referential "git note is stale" line now points at the
  paragraph ec6131f removed.
- **C6/3627a5f** — scoped ruff cleanup: entrySweep + engineParity only
  (`from datetime import UTC`, stale `# noqa: E402` dropped; entrySweep's
  unused `json` import and dead `cols` variable were dropped with the C3
  extraction). Deliberately NO repo-wide pass — dune scripts still carry
  UP017s (monitor/analysis/oosTransport lost theirs with the 2026-10-15
  re-review follow-ups).
- Full suite after all of the above: 108 passed (`uv run pytest`).
- Re-review correction (the re-review #18 ran; heading above enumerates
  C1–C6, no C7): the C4 "no legs" exit was broken for the all-header-only
  case — pl.concat raised its ValueError before the guard — and is now
  fixed inside loadLegs; and the oosTransport `RESEARCH_FETCH` resolution
  regression (`esw.` no longer re-exports it) was caught in the same
  re-review. Both are fixed by follow-up commits.

### oosTransport: OOS pull cannot grade the floor-ranked candidate cells (2026-10-15, later)

- Data: `configs/oosFetch.yaml` → `data/oos`: 484,220 fills (306k buys),
  141 markets / 60 resolved military slugs, 57,478 accounts,
  2024-05-29 → 2026-09-16. Event scope applied exactly as in-sample: the
  sweep's own `militaryMarketsTable` keyword filter over the fetched slug set
  (58/60 slugs carry ≥1 sweep entry); **only 1/60 slugs overlaps the
  in-sample universe** (`nasrallah-...-through-october-31`) → clean
  event-scope OOS. Sweep cache built by the same entrySweep machinery
  (fingerprint `f2bbde9a79`, `data/entrySweep/entries_v2_f2bbde9a79.parquet`);
  480-cell grid: `scripts/research/entrySweep.py --data-dir data/oos --grid
  configs/sweeps/oosEntryGrid.yaml` (log `logs/oosEntrySweep.log`);
  neighborhood + delay-realistic: `scripts/research/oosTransport.py` (new,
  thin wrapper importing entrySweep internals — the CLI could not do the
  age > 1 lower gate or drop no-landed triggers; log `logs/oosTransport.log`).
- Verdict framework (prestated): PASS a candidate $X/≤0.35 cell if OOS p5 > 0
  AND P(>0) ≥ 85% AND retReal-scaled > 0 AND single-event share < 60% with
  n ≥ 20 events (or accounts); FAIL = publishable transport falsification;
  INCONCLUSIVE when the pull is too thin for p5 to mean anything.
- Candidate track (≤ 3 markets, age ≤ 5d; all values below the 20-entry
  bootstrap floor, so `evaluate()` refuses to emit p5/P(>0) — raw means only):

  | cell | n | evts | accts | retReal | winRate | topEvShare | delay-realistic* |
  |---|---|---|---|---|---|---|---|
  | $5k/≤0.35 | 11 | 8 | 11 | +0.246 | .36 | 96% | n=5, +1.06, 5 evts |
  | $7.5k/≤0.35 | 9 | 7 | 9 | +0.124 | .33 | 220% | — |
  | $10k/≤0.35 | 8 | 6 | 8 | +0.264 | .38 | 116% (top loss > total) | n=3, +1.25, 3 evts |
  | $12.5k/≤0.35 | 5 | 4 | 5 | +0.356 | .40 | 137% | — |
  | $5k–$10k/≤0.30 | 10 / 7 | 7 / 5 | | +0.371 / +0.445 | | 70% / 79% | |
  | $5k–$10k/≤0.40 | 15 / 11 | 9 / 8 | | +0.226 / +0.154 | | 123% / 145% | |
  | **age 2-5d, any $X ≤0.30–0.40** | **1** | 1 | 1 | −1.000 | | | empty |

  *delay-realistic (computed cheaply from the entries cache + a rebuilt
  next-print tape in oosTransport): entries with NO buy print within 300s of
  the trigger are DROPPED (position never opens; entrySweep's retReal falls
  back to the trigger price instead), landed ones priced at that print +
  50bps. Overall landed300 across all 199,538 OOS burst triggers is 49.8%;
  27–57% inside the candidate track — the whole-burst return is not
  executable in this regime, and the $5k line loses 6 of 11 entries to it.
- **Verdict: INCONCLUSIVE on every candidate cell.** nDisclaimer: the 60-slug
  OOS fetch yields only 8 events with a legal ≥$5k ≤0.35 ≤3-market burst
  (≤3 events at $10k) — the 20-event floor is unreachable, so the bootstrapped
  p5 floor is undefined by construction, not merely weak. Single-event share
  is ≥70% descriptively wherever a top event is measurable. What would fix
  it: ~8/60 OOS events carry a ≥$5k-legal burst, so ≥20 events needs
  ~150–250 additional resolved military slugs (event count, not accounts),
  ideally filtered to books that were liquid at burst time (landed300%).
- The age-2-5d restriction — the in-sample candidate's key gate — has an
  essentially EMPTY OOS population (n=1, a single loser, across every
  size/price cell): big fresh bursts sit on day-0/1 accounts in the OOS era.
  The in-sample 2-5d restriction currently has no OOS mass to transport onto.
- Strict-PASS count over the whole 480-cell OOS grid (events ≥ 20): **0**.
  The 219 gradeable cells all fail p5 > 0 + P(≥85%): best gradeable p5 is
  $2k/≤0.65/age1/1mkt (p5 +0.175, P ~50%, 29 events, h1 negative). Every
  gradeable ≤0.35 cell is negative-leaning: $2k/≤0.35/5d/3mkt n=37, 22 evts,
  ret −0.150, p5 −0.634, P(>0) 28%; $1k line p5 −0.603, P 33%; $500 line
  p5 −0.482, P 39%. h1/h2 split is wrong-signed for the shipped expectation
  (h1 −0.31..−0.50 vs h2 +0.01..+0.26 — the OOS edge, if any, postdates the
  in-sample half). Directional read: at ≤ 0.35 the OOS tape gives no
  gradeable positive cell at any size; the floor-ranked transport is
  unconfirmed and leaning negative — a partial falsification of the floor
  ranking's transport (the $10k p5 +0.39..+0.57 in-sample cells can't even be
  reproduced as populations OOS).
- Cells frozen: none. The shipped $5k/≤0.35/5d/3mkt line keeps its in-sample
  grade; no change to the live watcher rule. Next OOS pull should target
  event count (≥150 resolved slugs) before re-attempting the $10k verdict.
  (Data observation recorded as such: age-2-5d being empty and big OOS bursts
  sitting on day-0/1 accounts is a property of the OOS tape, not a rule
  change — see the older-noted bullets above.)

### 9.1 oosTransport follow-up: oosExpansion roster staged (2026-10-15, later still)

- Discovery: crawled gamma `/events` by tag (closed=true, volume-desc, 24
  military-adjacent tag_slugs through the repo's own `HttpSession` pacing
  adapter at 4 req/s with 429 penalize, 79 successful 100-event pages + deep-
  pagination-wall retries on a few tags), filtered slugs with the
  SHIPPED 15-keyword military tuple from `scripts/research/researchData.py`,
  kept resolved-only closed events with volume ≥ $20k, and excluded every
  slug already in `data/` (13), `data/universe` (81), `data/oos` (60) and
  configs (`oosFetch`, `militaryUniverse`, `eventUniverse`). Crawl yield:
  1,280 fresh resolved military slugs.
- Roster: `configs/oosExpansionFetch.yaml`, 200 slugs with a ≤5-per-stem
  diversity cap so date-ladder clones ("israel-strikes-iran-by-december-31",
  ...) don't drown one question. Episode spread: iran 45, ukraine-russia 45,
  gaza-hamas 25, venezuela-maduro 20, houthis-yemen 15, hezbollah-lebanon 15,
  pakistan-india 10, syria 10, nato 8, taiwan 5, other-strike 2.
  Schema matches `oosFetch.yaml` (same `splitDate: 2026-01-01`;
  `fetch.dataDir: data/oosExpansion` — a separate dir, so the 60 oosFetch
  slugs stay untouched alongside).
- Smoke test (no bulk pull): `pc2 fetch --config configs/oosExpansionFetch.yaml
  --event-slug <3 of them> --set fetch.dataDir=data/oosProbe` → 3 slugs all
  resolved (`markets 11, fills 12063, accounts 2090`), markets.parquet carried
  winner + resolvedAt for each; probe dir deleted afterward. Config load +
  slug-uniqueness + zero-overlap check: PASS.
- Next step: launch the full 200-slug fetch into `data/oosExpansion` under
  supervision, then re-run the floor-ranked candidate-track evaluation with
  the same entrySweep/oosTransport machinery as the 60-slug pull. No PnL
  claims from this subsection; the fetch itself is not yet run.

### 9.2 oosExpansion: the transport verdict is FAIL at resolution (2026-10-15, latest)

- Data: `data/oosExpansion` fetched landed. 200 slug-roster events, 962
  markets, 10.66M fills, 469k accounts, tape 2023-10-15 → 2026-10-03
  (splitDate 2026-01-01 pinned in the roster config). Scope checks: all
  200/200 slugs carry ≥1 of the shipped 15 military keywords (the keyword
  filter is a no-op on this all-military roster, as expected); ZERO
  marketId/eventSlug overlap against `data/`, `data/universe` and `data/oos`
  — a clean fresh holdout. 49 markets across 4 events are unresolved (no
  winner/resolvedAt) and drop from the entry tape by design (ret-null filter).
- DataDirs for the eval: `[data/oosExpansion]` ALONE, via CLI
  `--data-dir data/oosExpansion` (dirsFromConfig precedence: CLI >
  fetch.dataDirs > fetch.dataDir). Deliberately NOT mixed with the in-sample
  dirs — nothing in-sample could leak into the numbers below.
- Machinery, unchanged: 480-cell grid `configs/sweeps/oosExpansionEntryGrid.yaml`
  (NEW config, grid axes identical to `oosEntryGrid.yaml` /
  `militaryEntryGrid.yaml`; only the fetch scope differs) run through
  `scripts/research/entrySweep.py` (log `logs/oosExpansionEntrySweep.log`),
  candidate neighborhood + delay-realistic through
  `scripts/research/oosTransport.py` (log `logs/oosExpansionTransport.log`)
  on the same entries cache
  (`data/entrySweep/entries_v2_5a57e33ce8.parquet`: 3,599,688 burst entries,
  200 events, 468k accounts). Nothing re-implemented, nothing tuned to the
  data; episode-level regrouping was NOT done (the account-overlap episode
  rule lives on feature/episodeScope and is not trivially reproducing from
  main's docs — skipped, noted as a limitation).
- Executability resolved: overall landed300 = **68.8%** of all burst
  triggers (was 49.8% on the 60-slug pull), and 85–98% inside the
  candidate track — these expansion books are liquid at burst time, so the
  "whole-burst not executable" objection no longer applies; the
  delay-realistic numbers below are graded on 88–97% of each cell's entries.
- **Full-grid strict-PASS count stays 0 — but no longer for thinness.** 464
  of 480 cells reach the MIN_CELL floor (was 219 with only ~8 real events)
  and NOT ONE has p5 > 0: best gradeable p5 anywhere = −0.304 (all top cells
  are ≤0.65 deep-favorite cells), best gradeable ret anywhere = −0.166,
  mean gradeable ret −0.473. The 224 gradeable cells at ≤0.35/≤0.40 are
  worse: max p5 −0.621, max ret −0.373. Grace at scale: a control on the
  same tape (all $10k+ bursts, any price/age: n=16,896, ret +1.1%,
  winRate 90.9%) shows the tape and winner coding are sound — the loss is
  specific to the ≤0.35 longshot copy line.
- Candidate track (whole-burst retReal = hold-to-resolution at the next-print
  fill price; the pre-registered gate: PASS only if p5 > 0 AND P(>0) ≥ 85%
  AND delay-corrected > 0 AND top-event share < 60%; MIN_CELL = 20 entries
  this time — every cell below is gradeable, so these are PASS/FAIL verdicts
  not INCONCLUSIVE):

  | cell (≤5d fresh, ≤3 mkts) | n | evts | accts | retReal | winRate | p5 | P(>0) | h1 | h2 | landed300 | delay-real. n / ret / P(>0) |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | $5k/≤0.30 | 338 | 53 | 223 | −0.599 | 5.6% | −0.865 | 2.8% | −0.677 | −0.587 | 92.0% | 311 / −0.604 / 2.6% |
  | $7.5k/≤0.30 | 211 | 43 | 142 | −0.851 | 3.8% | −0.954 | 0.0% | −0.625 | −0.890 | 91.0% | 192 / −0.899 / 0.0% |
  | $10k/≤0.30 | 142 | 29 | 97 | −0.811 | 4.9% | −0.940 | 0.0% | −0.584 | −0.842 | 92.3% | 131 / −0.852 / 0.0% |
  | $12.5k/≤0.30 | 104 | 23 | 71 | −0.845 | 3.8% | −0.975 | 0.1% | −0.650 | −0.869 | 93.3% | 97 / −0.875 / 0.0% |
  | $5k/≤0.35 | 394 | 60 | 262 | −0.550 | 8.1% | −0.809 | 2.0% | −0.487 | −0.563 | 91.9% | 362 / −0.579 / 1.5% |
  | $7.5k/≤0.35 | 252 | 48 | 172 | −0.734 | 7.5% | −0.868 | 0.0% | −0.366 | −0.810 | 90.9% | 229 / −0.801 / 0.0% |
  | **$10k/≤0.35 (in-sample floor-ranked)** | **167** | **34** | **113** | **−0.727** | **7.8%** | **−0.875** | **0.0%** | **−0.217** | **−0.817** | **91.0%** | **152 / −0.812 / 0.0%** |
  | $12.5k/≤0.35 | 121 | 27 | 82 | −0.737 | 7.4% | −0.905 | 0.1% | −0.092 | −0.850 | 91.7% | 111 / −0.834 / 0.0% |
  | $5k/≤0.40 | 491 | 65 | 321 | −0.557 | 9.8% | −0.766 | 0.5% | −0.541 | −0.560 | 90.8% | 446 / −0.579 / 1.5% |
  | $7.5k/≤0.40 | 322 | 54 | 219 | −0.689 | 9.9% | −0.832 | 0.0% | −0.448 | −0.748 | 89.8% | 289 / −0.738 / 0.0% |
  | $10k/≤0.40 | 220 | 41 | 150 | −0.700 | 9.5% | −0.858 | 0.0% | −0.446 | −0.756 | 88.6% | 195 / −0.762 / 0.0% |
  | $12.5k/≤0.40 | 160 | 31 | 107 | −0.705 | 9.4% | −0.872 | 0.0% | −0.436 | −0.765 | 90.0% | 144 / −0.766 / 0.0% |
  | **2–5d age slice, $10k/≤0.35** | 66 | 20 | 35 | −0.895 | – | −1.000 | 0.0% | −1.000 | −0.886 | 95.5% | 63 / −0.890 / 0.0% |

  Top-event share is n/a for the PASS gate in a darker sense than thinness:
  EVERY cell's total per-event pnl is negative, so no single event carries a
  positive edge (the flagship $10k/≤0.35 cell: 34 events, total −$12.1k on
  167 entries; the BEST event is +$689 on 2 entries
  ("another-us-strike-on-venezuela-by"), 7 of 167 entries won vs a mean
  burst price of 0.218 — break-even winRate at that price is ~22%).
- **Age split (the first OOS round's empty check, now graded):** the 2–5d
  restriction has real mass this time (n=37–166 per size/price cell) and is
  consistently WORSE than age 0–1d, not better (e.g. $10k/≤0.35: 0–1d
  ret −0.618 / p5 −0.840 vs 2–5d ret −0.895 / p5 −1.000). The in-sample
  candidate's key gate is anti-confirmatory where it can finally be tested.
- **Verdict per the pre-registered gate: FAIL on all 12 candidate cells ×
  both age windows and on the whole 480-cell grid (0/464 gradeable cells
  with p5 > 0).** The floor-ranked $10k/≤0.35 edge does NOT transport:
  in-sample p5 +0.39..+0.57 territory and +105% realistic ret with ~35%
  winRate becomes OOS p5 −0.875, P(>0) 0.0%, ret −0.727, winRate 7.8%, on
  167 entries over 34 previously-unseen events, delay-realistic
  (executable ≈ 91% of entries) −0.812. This is resolution, not padding:
  with 196 resolved fresh events (vs the 60-slug pull's ~8 gradeable) the
  20-event floor is met everywhere, both time halves are negative, and the
  best-case single events are drops in a negative pool. It is consistent
  with the honest episode-level regrade that flagged the in-sample edge as
  one-episode-concentrated: the edge is event-specific to the in-sample
  Iran-war-screen tape, not a property of "big fresh longshot bursts on
  military markets". The shipped $5k/≤0.35/5d/3mkt cell is in the same
  boat OOS (ret −0.550, P(>0) 2.0%) — both OOS pulls agree.
- Caveats kept honest: (1) whole-burst retReal benefits from entries a
  delayed copy couldn't make (engineParity note) — but delay-realistic is
  equally negative here, so the direction doesn't depend on that;
  (2) the expansion roster's ≤5-per-stem diversity cap spread the
  Iran-war-screen era thin (45 iran slugs across distinct questions), which
  is exactly the population transport asks about; (3) hold-to-resolution
  pricing is the sweep convention unchanged from in-sample, so the
  comparison is apples-to-apples; (4) episode-level regrouping (outstanding
  from the feature/episodeScope side) could only INFLATE event count
  stability checks — it cannot turn a −0.87 p5 positive.
- Watcher/live: unchanged. The paper-gate remains the money gate; both OOS
  pulls now say the category-wide military rule's expectation
  (+116% realistic, in-sample) is falsified outside its original events —
  the live paper sample, not more backtest cells, is the deciding evidence
  for or against keeping the rule live-published. Cells frozen (shipped
  cells keep pinned in-sample grades, printing only): none.


