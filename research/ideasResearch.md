# New ideas research (2026-10-09, web research + subagent)

Ranked by (evidence × cost). Sources inline. Companion to status.md §5.

## 0. BLOCKER found: execute.py uses V1 CLOB signing — would fail on first live order

**RESOLVED 2026-10-09**: `scripts/execute.py` now signs V2 via the official
`py-clob-client-v2` 1.2.0 (Polymarket Engineering, PyPI, Sep 2026 — the May-era
L1-auth bug note below predates it). Server `get_version()` returns 2; tick
size, negRisk routing and order version are resolved server-side by the client.
Dry-run path verified; live order placement still gated by the paper-trading
gate (status.md §6).

Polymarket migrated the CLOB to **CTF Exchange V2 in April 2026**; the server rejects
every V1 order (`400 invalid order version`). `scripts/execute.py` imported
`py_clob_client.client.ClobClient` with `signature_type=1` — V1-only. Options
were: npm `@polymarket/client` canary
(only package field-confirmed to place accepted V2 orders), `py-clob-client-v2` on PyPI
(open L1-auth bug binding the key to the EOA at the time), or the official `Polymarket/py-sdk`
successor. V2 changes that matter: order struct drops
taker/expiration/nonce/feeRateBps, adds timestamp/metadata/builder; domain version "2";
salt ≤ 2^53−1; pUSD collateral; min marketable BUY 1 share ≥ $1 notional; response
`{ok, orderId, status, makingAmount, takingAmount, transactionsHashes}`. A hand-rolled
signer failed in the field — the canary's type hash differs from public ts-sdk source,
so use a real client. Military ladders are frequently negRisk — the V2 client resolves
neg_risk per token from the server. Source: https://github.com/kollikrishnarao/polymarket-endpoints-test/blob/main/v2-discovery.md

## 1. Watcher fixes applied same day (liveWatcher.py)

- Tape-fetch resilience: `getWithRetry` (3 attempts, 1/2/4s backoff) around dataApi
  /trades and the two Gamma GETs; CLOB /book already fail-soft.
- Fresh-gate rescue: accounts first seen during backfill (previously permanently
  ineligible) get a ONE-time `GET /activity?user=...&start=bet−5d&end=bet−1` check;
  empty window → rescued (`backfill=False, ageVerified=True`), any row → confirmed old.
  Fails closed on bad payloads. Result cached on the account dict.
  **Requires a watcher restart to take effect** (daily report restarts it).
- Next tape upgrade: RTDS `wss://ws-live-data.polymarket.com` topic `activity` type
  `trades` with per-event filters (235 subs replace 1,220-market polling); envelope
  timestamp is **ms**, payload timestamp **s**. Pair with `/v2/trades` server-side
  filters `filter_type=CASH&filter_amount=5000` to stop parsing the whole tape.
  `/v2/resolutions?condition=...` for paperPnl closing. Sources: topics-and-schemas.md
  (same repo), docs.polymarket.com/market-data/realtime-data.
  **DONE 2026-10-09**: `scripts/rtdsTape.py` (global tape, client-side mid filter —
  the per-event filter shapes ack but deliver nothing; verified live) + `/v2/trades`
  CASH≥$5k gap-rescue poll in `liveWatcher.py`. Requires a watcher restart.

## 2. Rebuild "burst" on order_hash (Dune) — pure backtest

**SCRIPTED 2026-10-09**: `scripts/research/duneOrderBurst.py` (needs `DUNE_API_KEY`;
pulls cached to `data/raw/dune/`). Rebuilds the shipped cell both ways and reports
overlap + how many ≥$5k orders span multiple burst windows.

Dune `polymarket_polygon.market_trades` (v1+v2 rows, non-gated) carries `order_hash`:
group on it to reassemble one signed order's partial fills. Tests whether "single burst
≥$5k" should be order-level: recovers $8k orders split into sub-$5k chunks, drops $5k
assembled from unrelated $1k orders. Re-run shipped cell (+116% baseline) both ways.
Also future-proofs past the Nov 2026 relay-v2 retirement (v2 fee fields, neg_risk,
outcome_index on-chain). Insiders may deliberately split orders — the backtest decides.
Source: https://docs.dune.com/data-catalog/curated/prediction-markets/polymarket/market_trades

## 3. "No public news yet" anchor (GDELT) — the mechanism, encoded

Enforcement record 2025–26 is unanimous: insiders trade *before first public news*
(Van Dyke/Maduro ~$410k profit; Israel-strikes-Iran 13%→99.7% in 11.7h pre-news;
Lookonchain: three newly-created wallets front-ran the Maduro capture). Test: anchor each
of the shipped rule's signals to the first GDELT GKG article on topic, split pre-news vs
post-news, re-run the event bootstrap. Promote to a live gate only if pre-news n ≥ ~150
and P(0) ≥ 95%. Use article anchors only — ForesightFlow (arXiv:2605.00493) shows
resolution-anchored proxies reverse the separation; timestamp quality is the binding
constraint. Sources: github.com/veeradittya/polymarket-insider-detection;
wp.nyu.edu/compliance_enforcement 2026/05/14 (Van Dyke).

## 4. Third universes with public insider evidence: earnings/audit, pardons, M&A, FDA

Gamma tags verified live: `earnings` (1013), `merger` (100474), `acquisition` (934),
`fda` (101489). Evidence: WSJ-reported cluster winning near-perfectly on quarterly
earnings of KPMG-audited companies; CFTC FOIA probes into Biden-pardons/Iran/Google
markets; Debevoise forecasts M&A + clinical-trial insider theories. Caveats: FDA/earnings
resolve on scheduled deadlines (favorable per ForesightFlow) but books are thin — the
≥$5k burst population may be tiny. **Check per-market fee schedule first**: geopolitics
is 0% taker; politics 4%, economics 5% — at p=0.10 a 4% market costs 3.6% of stake per
entry. Sources: WSJ b4d322f7 (KPMG cluster); ccn.com CFTC FOIA piece.

## 5. Holder-based discovery: `/v2/holders?include_pnl=true` — second, disjoint path

Top holders per outcome with entry price, cost basis, PnL. Scan open military markets
for any holder with cost ≥$5k and avg entry ≤0.35 regardless of how the position was
assembled — catches slow accumulators the burst rule is blind to (cluster members trade
5–12 markets). Cheapest test: recall check against knownWallets.csv, then copy-backtest.
Source: https://data-api.polymarket.com/v2/openapi.json

## 6. Fee-aware execution: geopolitics is fee-free; prefer maker entries elsewhere

Fee = shares × rate × p × (1−p), taker-only. Where fees exist, the entry-decay finding
(edge grows with delay) means a resting limit at the ask (maker, $0 fee + rebate share)
is often strictly better than crossing. Two-arm paper test (taker vs limit) over next
~50 live signals. Sources: docs.polymarket.com/trading/fees; polymarketrader.com fee tool.

## 7. Fold volume-share into step-1 scoring (Lanker 2026 replication)

SSRN 7455078: positive-unlabeled RF on 889,569 trades / 93 geopolitical markets,
AUC 0.946, four pre-resolution features — avg entry price, capital deployed, trade
count, **market volume share** (the one we lack). Independently validates our caps:
insiders' median entry 46¢ vs 77¢ non-insiders. Test: add
`burstUsd / rolling24hMarketVolume` to `discovery/flagging.py`, re-run
`verdictBenchmark.py` on both labeled samples; keep only if precision improves at full
recall. Extra labeled sets from arXiv:2605.02287 (Gomez-Cram 1,950 accounts; Mitts &
Ofir 210k wallets) for recall checks.

## 8. Instrument edge decay / countermeasure tracking

Polymarket referred dozens of military-insider accounts to DOJ (Aug 2026), ~100 wallets /
$200M flagged H1-2026 flow (Bloomberg); CLOB rate limits went volume-tiered per-signer
(Aug 2026) naming copy-trading. Add: monthly rolling PnL + signal-count dashboard from
data/live/paperPnl.csv with alarm on two consecutive negative months; order-impact
tracking as crowding proxy; respect Poly-RateLimit-Warning / Retry-After. Verify venue/
geo before real size (Polymarket US is a separate venue with its own fee schedule).
Sources: cnn.com 2026/08/21; predictionauthority.com $200M recap;
docs.polymarket.com/api-reference/trading-rate-limits.

## Honest uncertainty (applies to #3, #4)

Enforcement-visible insiders are the ones who got caught (and are systematically
deadline-resolved); they may not resemble the population our rule copies. Both ideas are
cheap to falsify with the described backtests.

## Suggested order

1. Restart watcher (activates today's fixes).
2. Dune order_hash backtest (#2) — no live infra, answers a definitional question.
3. GDELT pre-news split (#3) — cheapest precision gain on the shipped cell.
4. V2 execution port (#0) before the paper gate ever passes.
5. Holders scan (#5) and volume-share scoring (#7) on the existing universe.
