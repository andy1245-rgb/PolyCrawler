# Monetization research (2026-10-17, web research + live checks)

How PolyCrawler2 could actually make money. Ground truth of today: one
strategy whose OOS edge was falsified (`oosFailureDiagnosis.md`), no live
PnL — but real, working infra: an RTDS watcher over 1,330 military markets
(233 events), a sub-second burst-signal engine (RTDS tape + `/v2/trades
CASH≥$5k` filters), a paper-trading gate, an on-chain funding-trace/cluster
discovery engine (Etherscan + relay origins + co-trading), and 100+ tests.
The question is what buyers exist **independent of whether copying insider
trades is profitable**.

Verified-live markers: prices checked against vendor pages today unless
noted. JS-gated prices are marked "not publicly crawlable" rather than guessed.

## 1. Legal / practical landscape first

### 1.1 Insider trading on prediction markets is being prosecuted — but against participants

- **2026-05-27**: SDNY charged **Michele Spagnuolo** (Google engineer, Polymarket
  handle "AlphaRaccoon") with insider trading for ~$1.2M profit betting Google's
  Year-in-Search with confidential business data. US Attorney Jay Clayton quote in
  https://techcrunch.com/2026/05/27/google-engineer-charged-with-insider-trading-after-making-1-2m-on-polymarket/
- Same coverage: DOJ charged a **US Army soldier** for trading the Maduro capture
  operation (~$400K). https://techcrunch.com/2026/05/27/... (same article)
- **2026-02-27**: OpenAI fired an employee for using confidential info on
  prediction markets (no charges; employment action).
  https://techcrunch.com/2026/02/27/openai-fires-employee-for-using-confidential-info-on-prediction-markets/
- NYT: "U.S. Begins Investigating Polymarket" (CFTC investigation of the
  platform), headline-only here.

**What we did not find**: any 2024–2026 precedent of legal action against a
*Polymarket analytics or signal seller* — searches surfaced only
participant cases. Absence of evidence is not evidence of absence, but the
documented enforcement mode is " prosecute the trader," not "prosecute the
dashboard." The realistic risk to a vendor is contract/counter-pressure, not
indictment:

- The Information: **"Polymarket Reverses Course on Startups That Piggyback on
  Insider Trades"** (paywalled; headline as surfaced via Google News 2026-10-17).
  The platform has a track record of revoking support for copy-on-insider
  startups.
- Polymarket is hiring Blockchain surveillance (Palantir) "as fraudulent
  schemes thrive off-chain on Telegram" (Open Measures via Google News) —
  platform actively monitors the off-chain signal economy.
- Polymarket docs reserve the right to revoke **builder fees** at "its sole
  discretion, for any reason or no reason" and the Relay v2 route our origin
  tracing depends on is retired **24 Nov 2026** (SPEC §5). Data access is
  revocable by policy; nothing we sell should *require* undocumented access.
- Positive precedent for sellers: alert/terminal vendors (below) are openly
  marketed, listed in directories, run affiliate programs, and at least one
  (Unusual Whales, public company-adjacent, quoted by Siebert Financial) is
  mainstream. Selling **detection/forensics** is a normal software business;
  selling **copy-execution of insider signals** is where platform risk
  concentrates.

### 1.2 How Polymarket itself pays out (official docs, fetched live today)

| Program | Terms (docs.polymarket.com) |
|---|---|
| Taker fee | `fee = C × feeRate × p × (1−p)`; Crypto 0.07, Sports 0.05, Politics/Finance/Mentions/Tech 0.04, etc. **Geopolitics is fee-free** — our military-ladder home. https://docs.polymarket.com/trading/fees.md |
| Maker rebates | 15–25% of taker fees redistributed **daily in pUSD** to makers who get filled (Fee-curve weighted; Politics 25%, Crypto 20%, Sports 15%). https://docs.polymarket.com/programs/maker-rebates.md |
| Liquidity rewards | Per-market reward allocation for resting orders near midpoint (min payout $1). https://docs.polymarket.com/programs/liquidity-rewards.md |
| Taker rebate tiers | Live 2026-05-28; 7 tiers Bronze→Obsidian, wV = size × (1−entry price) × category weight; one-time tier bonuses. PolyAlertHub's X account cites a $25,000 tier bonus for $10M+ monthly volume (not re-verified — tweet only). https://docs.polymarket.com/programs/taker-rebates.md |
| Referral | 10% direct / 5% indirect share of referees' net trading fees; requires $10k lifetime volume. Retail side is farmed by promo-code media (Cleveland.com, SI have $25-$50 codes). https://docs.polymarket.com/programs/referral-program.md |
| **Builder fees** | CLOB V2: attach a builder code to orders routed through your app → a flat % fee on **every matched order**, additive to platform fees, limits enforced. This is Polymarket's own monetization lane for app owners. https://docs.polymarket.com/programs/builders/fees.md |
| Venue grants | *Gate.io*, not Polymarket: $3M grant program for event-contracts infrastructure + white-label builder (Fortune / TradingView, Oct 2026). No Polymarket grants program found this pass. |

## 2. Market map — what the ecosystem actually charges

### 2.1 Retail alert/signal SaaS (the lane closest to our core signal)

| Product | What it is | Price (live-checked) | Coverage & source |
|---|---|---|---|
| **PolyPulse** | Whale alerts + auto-trade bots, Kalshi + Polymarket; "Insider Score™" marketing; $10K+ trades "in under 3 seconds" | Scout $0 (15-min delay) / Pulse **$29/mo** / Pro **$79/mo** / Elite **$199/mo** (whale mirroring on Kalshi + REST API) | https://www.polypulse.app/ — fetched live 2026-10-17 |
| **Unusual Whales → Unusual Predictions** | Prediction-market insider/whale/smart-money screeners, absorbed Hashdive | Free tier (limited whale alerts); **$17/mo** ($204/yr annual, $20 monthly) for "Full potential insider alerts, unusual activity flagged the moment it prints"; included in UW retail options-flow plans at $50/$75/$120 (annual: $42/$63/$102); API tokens sold separately | https://unusualwhales.com/pricing?product=predictions fetched live; retail tiers via Wayback 2026-09-07 snapshot of /pricing |
| **PolyAlertHub** | Real-time price/whale/**insider**/fresh-wallet alerts, paper trading terminal, API, browser extension | Plans page is a JS app — **not publicly crawlable**; nav confirms Insider Alerts + Insider Detection + paper trading | https://polyalerthub.com/ (plans page renders client-side only) |
| **Polymarket Analytics** (formerly by Hashdive) | Dashboards, whale tracker, trader leaderboards, PolyGun launch-sniper | Public dashboards free; API/alerts/exports paid; premium pricing **not publicly crawlable** (GamingToday has a premium review, bot-blocked) | https://www.hashdive.com/ fetched live; directory entry checked 2026-09-29 at https://www.predictionmarket.tools/tools/polymarket-analytics |
| **Kairos** | Pro trading terminal, one book across Kalshi/Polymarket/Predict.fun, global best bid/ask | Pricing not publicly listed on-site | https://www.predictionmarket.tools/tools/kairos (checked 2026-09-29 dir list) |
| **Telegram whale bots** (e.g. Hysen Labs "Whale Alerts") | Polymarket live-WebSocket monitoring, configurable size/probability thresholds; some hold a wallet in-bot (grey execution) | Free/open-source variants on GitHub exist | https://hysenlabs.com/projects/dunefalcon1qrj-telegram-bot |

**Price band this lane tolerates: $0 → $29 (mainstream) → $79-$199 (pro, with
execution/API). Important datapoint: Unusual Whales prices full
"potential-insider alerts" at $17/mo — generic insider alerts are already
commodity-priced. Also: Hashdive (a Polymarket analytics startup) sold to/merged
into Unusual Whales — consolidation is happening in this lane.**

### 2.2 Data APIs selling prediction-market data

| Product | Terms |
|---|---|
| **OddsPipe** | Polymarket+Kalshi matched markets, confidence scores; **Free / $49 / $99 / $299 per month** (Build/Launch/Scale). https://www.predictionmarket.tools/tools/oddspipe (checked 2026-09-29) |
| **Oddpool**, **Prediction.com/Hunt** | Normalized multi-venue data APIs (same directory) |
| **Unusual Whales API** | 200+ REST endpoints + WebSocket/Kafka + MCP server incl. prediction markets; API tokens on /pricing?product=api |
| **PolyAlertHub / Polymarket Analytics APIs** | API access advertised as paid tier of existing products |

### 2.3 Wallet-labeling (the Nansen analogue)

- On the Polymarket side, wallet labeling is served by Arkham ("How To Track
  Polymarket Whales" research piece) and the analytics products above. **A
  paid Polymarket wallet-label feed is an open niche right now** —
  PolyAlertHub's "Insider Detection" reads as fresh-wallet age tracking, not
  funding-trail forensics (feature surfaces as of 2026-10-17).

### 2.4 Liquidity / market-making side

- Officially defined above: maker rebates (15–25% of taker fees) +
  per-market liquidity rewards. Platform-encouraged; our politics/military
  category carries a 25% maker rebate while geopolitics itself is fee-free
  (relevant: military ladders span both).
- Community bounty precedent from the tools directory: "YeNo × Builderr
  Volume Bot Challenge" (volume-incentive competitions exist).
- BYO-MM software: kairos-style terminals and poly-clob clients make MM
  feasible; our V2 sign execution is dry-run verified (ideasResearch.md §0).

### 2.5 Demand signals (why this lane pays at all)

- The tools directory (predictionmarket.tools) lists **60+ prediction-market
  tools**; ≥8 are insider/whale alert products (PolyPulse, PolyAlertHub,
  Polysights, Betmoar, Alphascope, Whalidate, PolyTracer, PredictFolio...).
- Comparison-SEO exists purely to arbitrage this demand ("Best Polymarket
  Alert Tools", launchpoly/compare, gamingtoday reviews).
- Pay-adjacent content: Bitget research ran a multi-part "How to achieve
  ultra-high win rates on Polymarket through insider information" series
  (2026); Arkham publishes whale-tracking guides. Following "insiders" is a
  mainstream retail funnel.
- Polymarket itself inverted the funnels: taker-rebate tiers + referral share
  make volume worth paying for; US retail expansion is backed by a $1B round
  (Forbes) and the Kalshi comparison market is valued toward $42B (Fortune).

## 3. Competitive scan — closest to "wallet-cluster insider alerts"

| # | Product | What data it exposes | What it charges | Gap vs us |
|---|---|---|---|---|
| 1 | **Unusual Predictions (Unusual Whales)** | "Potential insider" flags from prediction-market trade data; whale trades; smart-money screeners; the moment it prints | $0 / $17/mo / bundled into $42-102 UW plans | No on-chain funding trails, no cross-account cluster graph, no bridge-origin identity. Generic across categories, not military-vertical. |
| 2 | **PolyAlertHub** | Price alerts, whale alerts, **fresh-wallet "insider" alerts** (account-age heuristics), trader alerts, paper trading | Not publicly crawlable (JS-gated) | Fresh-wallet age ≠ funding forensics; no parent/child attribution, no burst-context tape. |
| 3 | **PolyPulse** | Every $10K+ trade within ~3s, whale tiers, "Insider Score™", wallet following, auto-mirroring on Kalshi | $0 / $29 / $79 / $199 | Size-threshold + score heuristics only; no funding-trail evidence or cluster attribution; execution-first. |
| 4 | **Polymarket Analytics (ex-Hashdive)** | Whale tracker, wallet PnL, trader leaderboards, positions, entry-price distributions | Free dashboards; paid API/alerts (price not public) |Wallet-performance forensics, not *pre-resolution* cluster detection; PolyGun = launch sniping, not insider. |
| 5 | **Bubblemaps** | Generic token-holder cluster graphs (Polygon included), overlap web | Free tool; intel/subscription product on X/utility tokens | Not prediction-market aware; no market/resolution context; no alerts product on PM markets (product scan, no pricing verified). |

**What our signals give that none of these showed in their materials:** the
SPEC's step 2-4 evidence chain — Polygon funding edges from non-hub parents,
bridge-origin identity via Relay, co-trade linking within a 10s window, and
cluster grouping — plus burst context from a sub-second RTDS tape scoped to
1,330 military markets. Our own sample review (`sampleReview.md`) recovered a
6-wallet co-trade cluster "without any funding data", which is literally the
differentiator nobody in the table above sells: **attribution of *who is
behind* the burst** (parent fingerprint), not just *that* a burst happened.
The nearest neighbour (UW) sells the "potential insider" *label* at $17/mo;
nobody sells the *evidence dossier*.

## 4. Double-edge risk (one honest paragraph)

Two edges cut on us. Signal decay: an alert feed that works gets crowded and
the crowd moves the price before subscribers are filled — every alert we sell
teaches the market our trigger; insider fronts themselves adapt (fresh wallets
are cheap to rotate, and the account-level OOS failure says exactly that:
what made an account special did not survive contact with the next event).
Platform/counter-pressure: actual enforcement 2024–2026 targets
**participants** (Spagnuolo, the Maduro-bet soldier, the OpenAI firing), and
no case against a Polymarket analytics/signal *seller* was found — but
Polymarket's counter-move is unilateral: The Information reports the platform
"Reverses Course on Startups That Piggyback on Insider Trades", Polymarket
hires Palantir-grade on-chain monitoring while fraud thrives off-chain on
Telegram, builder fees are revocable at sole discretion, and the Relay v2
route our identity tracing depends on dies 24 Nov 2026. The positioning that
shelters us from both edges: sell **detection/forensics** (who clustered, who
funded, when the burst printed — data that is as useful to researchers,
journalists, compliance, and the platform itself as to copy-traders) rather
than copy-trading execution, and price the product so no single inflection
(insider-cluster copying) is on the P&L.

## 5. Ranked paths (effort-from-current-infra × demand evidence × edge-independence)

### Path A — Productize the burst watcher: paid insider-burst feed for military/geo markets

- **What exists today**: live RTDS watcher over 1,330 military markets (233
  events) with sub-second tape + `/v2/trades CASH≥$5k` gap-rescue; burst
  triggering; a paper-trading gate that can publish honest hit-rate numbers;
  seed=list-era discovery engine + dossier generator (`accountDossiers.py`).
- **Must build (2-3 weeks)**: (1) Telegram bot alert routing (templates,
  size/price-fresh filters, dedup) — the tape is already structured;
  (2) live incremental cluster attribution: run the discovery engine's
  funding-trace steps on watcher-flagged accounts on the fly (Etherscan +
  Relay costs serial to real-time instead of batch — mind the Relay v2 sunset,
  needs the Dune `order_hash` path as fallback, `duneOrderBurst.py` exists);
  (3) a public credibility page fed by the paper gate (free tier shows
  delayed/dossier-less alerts — the exact Scout-free→paid ladder PolyPulse
  runs); (4) billing: Stripe or pUSD, publish at $29/mo intro tier.
- **Positioning vs the $17/mo incumbent**: vertical focus (military/geo —
  Polymarket's fee-free, highest-salience category), evidence-first (funding
  trail + parent fingerprint links in the dossier), and honest hit-rate
  metrics. Differentiate on *depth*, not speed — UW and PolyPulse already win
  latency.
- **First-revenue milestone**: 20 paying subscribers at $25-35/mo (~$500-700
  MRR) within ~2 months of a public launch post. Launch trigger: one
  fully-attributed high-profile military burst dossier published on X in
  real time — that event *is* the ad unit (PolyAlertHub's whole X presence
  does exactly this).
- **Edge-independence**: sells whether copying insiders is profitable or not
  — detection/forensics demand exists while copy demand is questionable.

### Path B — Sell the dataset/API to researchers, journalists, tool-builders

- **What exists today**: parquet schema over markets/fills/funding/origins
  (SPEC §4), the discovery pipeline, and burst-event logs; the Dune
  `polymarket_polygon.market_trades` environment proves research workflow
  compatibility.
- **Must build (3-6 weeks)**: documentation + schema freeze (the repo
  writes outside the codebase are already the dataset); token-gated REST
  endpoints (markets-with-flagged-instances, burst timeline, cluster graph,
  funding edges); uptime/SLA story; a Delta-sharing or Parquet-over-S3
  variant for quant buyers.
- **Buyers & price anchors**: quant researchers/papers, investigative
  journalists (participant prosecutions above create a story desk demand for
  attribution data), and tool-builders in the 60+-name directory
  (OddsPipe band: **$49/$99/$299/mo** is what normalized PM data actually
  lists for).
- **First-revenue milestone**: two pricing conversations + one paid pilot at
  $250-500/mo. Realistically slower sales — this is a pipeline, not a launch.
- **Edge-independence**: fully independent of our copy-rule PnL.

### Path C — Platform-native: maker rebates + liquidity rewards + builder fee

- **What exists today**: V2 order signing (`execute.py`) dry-run verified,
  paper gate, the sweep/entry framework.
- **Must build (4-6 weeks)**: real-time quoting engine on negRisk ladders in
  the 25%-rebate categories (Politics/Finance — note: pure geopolitics is
  fee-free so *zero* maker rebate there; reward-bearing adjacent categories
  are the target); inventory risk management (the falsified OOS edge means
  directional overlay is forbidden — quotes must be decomposition-arb /
  ladder-structural); a builder-code wrapper app to attach the fee layer to
  our own routed orders.
- **Evidence**: maker rebates are a defined, daily-paid program (25% of
  taker fees, Politics/Finance 25%); liquidity rewards per-market caps are
  live config (market-details API); tier bonuses (PolyAlertHub cites a
  $25,000 top-tier bonus) create asymmetric upside for a desk-size operation.
  This is how you monetize **from trading, not from users**.
- **First-revenue milestone**: first maker-rebate pUSD payout ≥ $1 (the
  documented minimum) within the paper-gate → live transition; then a
  monthly number vs the paper baseline. Note ordering: the paper gate must
  clear first — this path inherits whatever the gate proves.
- **Edge-independence**: partial — MM returns depend on decomposition/ladder
  structure, not on insider copying, but capital + the gate are shared.

### Ranking rationale

A first: smallest build from what works today (a watcher that already runs),
strongest demand evidence (whole SaaS tier priced $17-199/mo, one incumbent
at $17, one exit to Unusual Whales proving M&A liquidity), and fully
edge-independent. B second: real price anchors, no platform risk, but a
sales-cycle business, and the dataset must survive the Relay-v2 sunset to
stay asset valuable. C third: lowest dependence on buyers, highest
dependence on the paper gate and on inventory math we haven't validated;
also partially exposed to Polymarket's discretionary-revocation clause.

Practical sequencing: A pays the rent and is by definition C's marketing
surface (an alert feed that proves burst quality is evidence a desk/builder
app exists), and B's dataset is A's exhaust. None of the three paths
requires the OOS-falsified copy rule to be un-falsified.
