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
