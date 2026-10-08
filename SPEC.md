# PolyCrawler2 — Spec (v0.2.0-draft)

> The v0.1 spec and docs live in `archive/v1/` for reference only.

## 1. Goal

Answer one question first: **can we find insider clusters from past data, and does copying them afterwards make money with a realistic delay?**

- **Cluster** = a parent funding wallet + the Polymarket accounts it funded.
- **Net position** = per market, the cluster's Yes shares minus No shares.

Everything is built to be backtested and tuned by config. Paper/live trading come later and reuse the same code.

## 2. Rules

1. **Backtest first.** No live code until backtests show an edge.
2. **Same inputs + same config = same result.** Discovery and strategy are plain functions — no network, no database, no clock.
3. **Every knob is in the config file.**
4. **No peeking at the future.** Discovery only uses data before `splitDate`; the backtest only trades after it.

## 3. How it fits together

```
fetch → data/*.parquet → discover (before splitDate) → parents
                                         ↓
                       backtest (after splitDate) → runs/<id>/ → sweep / compare
```

| Command | Does |
|---------|------|
| `pc2 fetch` | Download markets, trades, prices, and funding data into `data/` |
| `pc2 discover` | Score accounts, group by funder, write `parents.parquet` |
| `pc2 backtest` | Copy discovered clusters after `splitDate` with one config |
| `pc2 sweep` | Run many discover + backtest combos over a grid and rank them |

The `splitDate` is what keeps this honest: we only copy clusters we *could* have found at that time.

## 4. Data

Parquet tables in `data/`:

| Table | Columns | Source |
|-------|---------|--------|
| `markets` | `marketId`, `question`, `tags`, `endDate`, `winner`, `volumeUsd` | Gamma API |
| `fills` | `ts`, `account`, `marketId`, `outcome`, `side`, `size`, `price` | Data API `/trades?market=` |
| `funding` | `ts`, `fromAddr`, `toAddr`, `amountUsd`, `txHash` | Polygon ERC-20 collateral transfers (Etherscan) |
| `prices` | `ts`, `marketId`, `outcome`, `price` | CLOB `prices-history` |

Fetch order: pick markets (by tags / volume / date) → all their fills → funding for accounts that look interesting → prices for markets clusters traded.

## 5. Discovery

**Step 1 — Flag suspicious accounts.** For each account, from fills in markets resolved (`resolvedAt`) before `splitDate`, score the account on its most profitable winning bet (shares bought − USD spent):

| Signal | Config key | Default |
|--------|-----------|---------|
| New account (days from first trade to the big bet) | `maxAccountAgeDays` | 14 |
| Few markets traded | `maxMarketsTraded` | 5 |
| Bought at long odds | `maxBuyPrice` | 0.3 |
| Big bet | `minBetUsd` | 1000 |
| Won | — | required |

An account is **suspicious** if it passes at least `minSignals` of these (default 4).

**Step 2 — Trace funding.** For each suspicious account, and for labeled wallets when a label file is supplied, read Polygon ERC-20 transfers from Etherscan (`chainid=137`). Keep collateral only: USDC.e, native USDC, pUSD, and Polygon USDT (USDT0). Drop anything under `minFundingUsd` (default 1). Incoming transfers are funding. Outgoing transfers are cash-outs, except where the other side is a Polymarket contract (CTF exchange, NegRisk exchange/adapter, conditional tokens, proxy/safe factories, and the V2 position, router, and collateral ramp contracts) — those are trades and redeems. Raw responses are cached under `data/raw/etherscan/`.

A counterparty is a **hub** when a page of its transfers (up to 1000) has at least `hubMinCounterparties` distinct collateral counterparties (default 50). The newest page is checked first. If that page is full and still under the threshold, the oldest page is checked too. A contract with real bytecode (not a tiny clone) that fills a 1000-row page is a hub even when those rows sit on a few pools. Hubs are deposit solvers, bridges, routers, and exchange hot wallets. They are not parents. `excludedFunders` is the same kind of skip, entered by hand.

**Step 3 — Group into clusters.** Using transfers before `splitDate` only, link accounts that share a non-hub funder, share a non-hub cash-out destination, or send collateral to each other. If `fundingHops` is 2 (the default) and a funder is a non-hub EOA, also link accounts that share that funder's funder. A connected component with at least `minSuspiciousAccounts` suspicious accounts (default 2) is a cluster. The parent is the non-hub funder shared by the most suspicious accounts in the component. If the component is only tied by cash-outs or direct transfers, the parent is `component:<clusterId>`.

Then list every account that parent sent collateral to, including accounts funded after `splitDate`. Those siblings are what the strategy would copy.

Output:

- `funding.parquet` — `ts`, `fromAddr`, `toAddr`, `amountUsd`, `txHash`
- `parents.parquet` — `parent`, `clusterId`, `accountCount`, `suspiciousCount`, `totalProfitUsd`, `firstSeen`, `linkTypes`
- `clusterAccounts.parquet` — `clusterId`, `account`, `linkType`

**Checking discovery on its own:** of the clusters found before `splitDate`, how many kept winning after it? That's the first number to look at — if found clusters don't keep winning, the strategy can't work.

## 6. Strategy

Applied to each cluster fill after `splitDate`, in time order:

1. **Update net.** `net = sum(Yes shares) − sum(No shares)` across the cluster's accounts in that market.
2. **Entry** (only when we hold nothing in that market): enter if `|net| × price >= minNetUsd` and the price paid is `<= maxEntryPrice`.
3. **Size.** `target = net × mirrorPct`, capped at `maxPositionUsd`. Once in, the target follows net.
4. **Exit.**
   - `exitMode: followCluster` — exit when the cluster's net is ~0 (below `minNetUsd`), or at resolution.
   - `exitMode: holdToResolution` — ignore cluster sells; hold to resolution.
5. **Fill price.** The market price `delaySec` after their fill, plus `slippageBps`.
6. **Resolution.** Winning shares pay $1, losing pay $0.

## 7. Config

```yaml
splitDate: 2026-01-01

fetch:
  marketTags: [politics, geopolitics]
  minMarketVolumeUsd: 100000
  from: 2024-01-01

discovery:
  maxAccountAgeDays: 14
  maxMarketsTraded: 5
  maxBuyPrice: 0.3
  minBetUsd: 1000
  minSignals: 4
  minSuspiciousAccounts: 2
  excludedFunders: []
  hubMinCounterparties: 50
  fundingHops: 2
  minFundingUsd: 1

strategy:
  minNetUsd: 500
  maxEntryPrice: 0.5
  mirrorPct: 1.0
  maxPositionUsd: 1000
  exitMode: followCluster   # followCluster | holdToResolution
  delaySec: 30
  slippageBps: 50
```

Override any value from the CLI: `pc2 backtest --set strategy.delaySec=60`.

## 8. Results

Each backtest writes `runs/<configHash>/`:

- `config.yaml` — exact config used
- `parents.parquet` — clusters discovery found
- `trades.parquet` — every trade we made
- `summary.json` — clusters found, % still winning after split, total PnL, trade count, win rate, max drawdown, PnL by cluster

`pc2 sweep sweep.yaml` runs a grid over any config keys (discovery or strategy) and prints a ranked table.

## 9. Stack

Python 3.12, `uv`, Pydantic, Polars, httpx, web3.py, Typer, pytest.

```
src/polycrawler/
  config.py     # config model + loading + --set
  fetch.py      # download → data/*.parquet
  discovery.py  # suspicious accounts → funders → parents
  strategy.py   # net, entry, size, exit
  backtest.py   # replay, fills, PnL, summary
  sweep.py      # grid runs + ranking
  cli.py
```

Discovery stays in this repo for now. It only talks to the rest through `data/` and `parents.parquet`, so it can move to its own repo later without changes.

## 10. Phases

| # | Deliverable |
|---|-------------|
| 1 | `fetch` for markets + fills (no RPC needed yet) |
| 2 | Discovery step 1 — list suspicious accounts; eyeball them |
| 3 | Funding fetch + discovery steps 2–3 — first clusters |
| 4 | Price-move check: after cluster buys, how did price move at 1h / 1d / resolution, for several delays? Stop if no edge. |
| 5 | `backtest` + `sweep` |

## 11. Later (not in v0.2)

Scored ranking instead of signal counts · funding hops past `fundingHops` · take profit / stop loss · order book fills · walk-forward validation · paper trading · live trading · dashboard · alerts · database.

## 12. Open questions

1. Polygon funding source — resolved: Etherscan V2 (`chainid=137`). Alchemy Polygon was not enabled for this key.
2. Collateral after the V2 migration — labeled deposits in this window are USDC.e. Native USDC, pUSD, and Polygon USDT (USDT0) also move and are all kept.
3. Starting market set: which tags / date range.
4. Ranking metric for sweeps: total PnL or PnL ÷ max drawdown.
