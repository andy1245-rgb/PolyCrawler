# PolyCrawler

Backtest-first research on Polymarket: find wallets that look informed in past data, then test
whether copying them afterwards survives a realistic delay. For researchers who would rather see a
rule falsified on a holdout than drawn on a chart.

[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

## What it does

Four commands, one step each of the same pipeline. They communicate through Parquet on disk, so any
step can be rerun without repeating the one before it.

| Command | Input | Output |
|---|---|---|
| `pc2 fetch` | event slugs, or tag and volume filters, from a YAML config | `data/markets.parquet`, `data/fills.parquet`, `data/prices.parquet`, plus a raw-JSON cache |
| `pc2 discover` | the fills before `splitDate` | `data/suspicious.parquet`, `data/funding.parquet`, `data/origins.parquet`, `data/parents.parquet`, `data/clusterAccounts.parquet` |
| `pc2 backtest` | the fills after `splitDate`, plus a strategy config | `runs/<hash>/params.yaml`, `runs/<hash>/summary.json`, `runs/<hash>/trades.parquet` |
| `pc2 sweep` | a grid of backtest configs | a ranked table over the grid, written under `runs/` |

`pc2 fetch` prints four lines as it lands — `markets`, `fills`, `accounts`, `prices` — the last
counting quote rows the CLOB pull returned; `--no-prices` skips that step, two requests per market.
That pull is why a market nobody traded inside the six-hour window still prices at all: `fetchPrices`
in `src/polycrawler/fetch.py` writes `prices.parquet`, and `priceAt` in `src/polycrawler/priceMove.py`
consults it only where the trade tape has nothing.

A backtest prints a summary whose first lines decide whether the rest of it means anything:
`noPriceSkips` counts entry attempts, exit attempts and open positions that found no price, and
`entryCoverage` the share of copy attempts that did; a copy that cannot be priced is counted, never
dropped. `priceSources` reports those four cases apart — `entryPrint`, `entryQuote`, `exitPrint`,
`exitQuote` — so a run priced from a CLOB quote reads separately from one priced from a trade print.
The two are not the same evidence — a print is what a trader paid, a quote is what the book was
showing — so a result leaning on quotes is a claim about the tape, not about fills.

Here is the shipped backtest path replayed over the holdout tape, command and output as they came:

```bash
uv run pc2 backtest --config configs/militaryBacktest.yaml \
    --data-dir data/oosExpansion --set strategy.minNetUsd=10000
```

```
run 42a4c2a39e1a
trades 137  marked 0
noPriceSkips {'entryAttempts': 0, 'exitAttempts': 0, 'markLots': 0}  entryCoverage 1.0000
priceSources {'entryPrint': 137, 'entryQuote': 0, 'exitPrint': 0, 'exitQuote': 0}
totalPnl -9831.73
capitalDeployed 13700.00
returnOnDeployed -0.7176
winRate 0.0803
maxDrawdown 10456.39
topEvent another-us-strike-on-venezuela-by  pnl 684.90  share -0.0697
pnlWithoutTopEvent -10516.64
returnWithoutTopEvent -0.7790101846304966
medianEventReturn -1.0
events 30
```

The real output ends with one further line naming the run directory it wrote. The tape that command
read is not in this repository — see [Quickstart](#quickstart) for what fetching one takes.

Two more guarantees live in `scripts/`, where the live books are written. `scripts/bookExecStamps.py`
retires an alert more than `MAX_STAMP_LATENESS_S` (24h) past its due time as `missReason=stale`, no
price recorded, so a replay noticed days late counts as a skip instead of becoming the T+300s book.
`bookLock` in `scripts/paperLanes.py` holds an exclusive `flock` on `<book>.lock` across the header
read and the append after it, so two writers cannot both see a missing file and write a header.

## The measured result, and what it is worth

Discovery ran end to end on a holdout of 200 resolved military event slugs — 962 markets and
10,666,464 fills spanning 2023-10 to 2026-10 — and flagged **14 accounts out of 2,466 scored**
(0.57%) while finding **0 clusters**: the holdout's `parents` and `clusterAccounts` tables both came
back empty. The honest n for "how many clusters kept winning after the split" is therefore zero, and
the cluster-copy strategy this repository exists to test had nothing to copy. The 11 GB behind those
counts is not in the repository.

The burst-entry rule that the in-sample sweeps ranked first was then replayed on the same holdout
and returned **−72.7% on n = 167 entries across 34 events and 113 accounts**, with a 5th-percentile
bootstrap floor of −0.875, 7.8% of entries winning, and not one of the 464 gradeable cells in the
480-cell grid clearing a positive floor. Negative in both time halves: −0.217 before the mid-split,
−0.817 after.

Neither number is a bug report. Both are the point. What is behind each one:

| Claim | Value | Recorded in | Regenerable from a clone? |
|---|---:|---|---|
| Holdout roster | 200 slugs | `configs/oosExpansionFetch.yaml` | yes — `grep -c '^    - ' configs/oosExpansionFetch.yaml` |
| Markets, by split | 962 = 376 pre-split + 537 post-split + 49 unresolved | `research/oosClusters.md` | no — corpus not distributed |
| Fills | 10,666,464 | `research/oosClusters.md` | no — corpus not distributed |
| Candidates scored → flagged | 2,466 → 14 | `research/oosClusters.md` | no — corpus not distributed |
| Clusters found | 0 | `research/oosClusters.md` | no — corpus not distributed |
| Flagship cell | −0.727, n = 167, 34 events, 113 accounts, p5 −0.875 | `research/status.md` | no — needs the burst-entry cache |
| Grid cells with p5 > 0 | 0 of 464 gradeable (480-cell grid) | `research/status.md` | no — same cache |
| Shipped backtest path, same tape | −0.718, n = 137, 30 events | the command above | no — same tape |
| Tests | 241 | `uv run pytest -q` | yes |

The last two rows are the same tape graded by two entry rules: the sweep prices entry at the burst's
running average, the shipped backtester at fill + 30 s. 167 entries become 137, −0.727 becomes
−0.718, and the verdict does not move.

The live lanes grade the same way, from floors fixed before any lane data existed: lane 2, the
T+7d horizon book, needs 8 closes before its gate may speak, and lane 3, the favourite/mid burst
book, 20. Under those floors both return `INCONCLUSIVE-THIN (n=…)` rather than a PASS or a FAIL
(`gate2`, `gate3` in `scripts/laneWeekly.py`); neither is a result yet, and no count from those
gitignored books is quoted here.

A count is only as good as its key. [`docs/paper-lane-records.md`](docs/paper-lane-records.md) §5
records a dedupe keyed on the alert timestamp alone which saw **22 of 72 alert rows**: timestamps
cluster, three different accounts shared one second, and the other 50 rows would have been skipped
in silence. Every book, cache and grid here keys on `(alertTs, account, eventSlug)` for that reason.
The same document's §9 records what a replay did to the live books — 62 of 72 signal rows
untrustworthy — and which rows are still worth quoting.

## Quickstart

Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/). Nothing else is needed for the offline
checks below.

```bash
uv sync
uv run pc2 --help
uv run pytest -q
```

`uv sync` installs the package and its `pc2` entry point, `--help` lists the four commands with their
flags, and the suite prints `241 passed`.

Fetching a corpus is the first step that needs the network: Polymarket's Gamma and Data APIs for
markets and fills, the CLOB prices-history endpoint for quotes. No key is required for that.

```bash
# network; --event-slug narrows a roster to the events you name, so a first run can be one event
uv run pc2 fetch --config configs/oosExpansionFetch.yaml --event-slug us-forces-enter-iran-by
```

`pc2 discover` needs `ETHERSCAN_API_KEY`, from the environment or a gitignored `.env`, and errors
without one. `ALCHEMY_API_KEY` is optional: it only affects on-chain payout confirmation, which
degrades to `None`. The Relay bridge lookup needs no key and is paced at one request per second.

```bash
uv run pc2 discover --config configs/oosExpansionDiscover.yaml
uv run pc2 backtest --config configs/militaryBacktest.yaml
```

`pc2 fetch`, `pc2 discover` and `pc2 backtest` each take `--set` overrides, so a variant of a config
can be run without editing it — which is how a single grid cell is expressed:

```bash
uv run pc2 backtest --config configs/militaryBacktest.yaml --set strategy.delaySec=60
```

## How it was measured

Discovery reads only data before `splitDate` and the backtest only trades after it, so the split is
what keeps the two apart. Entry is priced from the last trade print at or before `fill + delaySec`
inside a six-hour staleness window; when no print falls inside it the CLOB price-history tape is
consulted instead and the row is tagged `quote`. A copy that finds neither is counted in
`noPriceSkips`. Prices come from the tape or the CLOB, never from a midpoint, so a quote-priced row is
a published price at a published time rather than a guess at a fill.

A run also identifies the tape it priced against. `paramsHash` covers strategy parameters only, so
two runs of one config over two price universes shared a run directory and the second overwrote the
first with different numbers. `runs/<hash>/summary.json` now carries a `quotesHash` over the quote
rows, and `writeRun` refuses to overwrite a run whose `quotesHash` differs.

The holdout was built to be one: 200 slugs crawled from Gamma by tag, filtered through the same
15-keyword roster the in-sample work used, resolved-only, volume ≥ $20k, and asserted to have zero
slug overlap with every previously fetched directory.

| Document | What it records |
|---|---|
| [`research/oosClusters.md`](research/oosClusters.md) | the discovery run on the 200-event tape: timings, the candidate funnel, the zero-cluster result, post-split account P&L |
| [`research/status.md`](research/status.md) | the sweep and transport results in full — the 480-cell grid table, the pre-registered PASS/FAIL gate, the executability check |
| [`docs/paper-lane-records.md`](docs/paper-lane-records.md) | the paper-lane books: event time versus write time, horizon anchoring, price coverage, signal identity, and what in the live books is untrustworthy |
| [`docs/README.md`](docs/README.md) | index of the long-form records |
| [`SPEC.md`](SPEC.md) | the v0.2 draft the code was built against |
| [`SPEC-DIVERGENCES.md`](SPEC-DIVERGENCES.md) | where the code moved away from that draft, and which side should change |

`SPEC-DIVERGENCES.md` is a record of an audit, not a live bug list: it was written against the draft
at v0.2.0-draft, its line references have moved, and its first divergence is closed — the `prices`
table it called unimplemented now lives in [`src/polycrawler/fetch.py`](src/polycrawler/fetch.py),
covered by [`tests/test_prices_history.py`](tests/test_prices_history.py).

## What it does not do

- **It does not ship its data, and it cannot audit itself from a clone.** No Parquet, no run
  directory, no log is tracked, and the paper-lane books under `data/live` were partly reconstructed
  by replay. A clone reads the code, runs the suite and fetches a corpus; it cannot reproduce a
  published count without doing the fetch, and §9 of
  [`docs/paper-lane-records.md`](docs/paper-lane-records.md) is where the trustworthy live rows are
  separated from the rest.
- **It does not claim an edge.** The rule that won in-sample lost on the holdout, and the cluster
  strategy had nothing to copy there at all: 0 clusters from 14 flagged accounts. No configuration
  in this repository has passed an out-of-sample test.
- **It does not follow a cluster's net exposure the way `SPEC.md` describes.** It copies signed BUY
  bursts per `(group, market, outcome)` and never forms Yes − No; sizing mirrors their shares rather
  than their net. See SD-12…16 in [`SPEC-DIVERGENCES.md`](SPEC-DIVERGENCES.md).
- **It does not trade by itself.** No loop calls the executor. `scripts/execute.py` places an order
  only when `--live` is passed *and* `POLYMARKET_PRIVATE_KEY` is in the same invocation, and then
  only under hard per-order and open-exposure caps. Everything else is a dry run.
- **It does not cover more than one venue, one chain, or two outcomes.** Markets come from
  Polymarket, funding from Polygon collateral transfers, and the synthetic complement `1 − p` is
  only valid for two-outcome markets.

Two dead knobs remain in the config model: `minCoTradeMarkets` is declared and read by nothing, and
three result-changing constants — the 10-minute burst window, the 6-hour staleness window and the
3,650-day mark horizon — are module constants rather than config fields, despite the spec's claim
that every knob is in the config file.

## Repository layout

| Path | What is in it |
|---|---|
| `src/polycrawler/` | the package — `fetch`, `discovery`, `strategy`, `backtest`, `priceMove`, `sweep`, `http`, `config`, `cli` |
| `configs/` | YAML: fetch rosters, discovery settings, strategy settings, and the grids under `configs/sweeps/` |
| `scripts/` | the operational layer the CLI does not cover — live watcher, paper lanes, execution — plus the studies under `scripts/research/` |
| `tests/` | 241 tests over 27 files, with JSON fixtures for the API response shapes |
| `research/` | one document per study, each with its numbers and its verdict |
| `docs/` | long-form records, indexed by purpose in `docs/README.md` |
| `archive/v1/` | the v0.1 spec, docs and scaffolding, kept for reference only |
| `data/`, `runs/`, `logs/` | generated and gitignored — a fresh clone is empty here, and no count above lives in them |

Root files worth knowing: `pyproject.toml` (package, deps, `pc2` entry point), `uv.lock`,
`SPEC.md`, `SPEC-DIVERGENCES.md`, `LICENSE`.

## Licence and attribution

Apache-2.0 — see [`LICENSE`](LICENSE). Research tooling for paper trading. Not financial advice, and
not a recommendation to trade any market.

Order signing uses [`py-clob-client`](https://github.com/Polymarket/py-clob-client) and
`py-clob-client-v2` (Polymarket Engineering). Market, trade, price and funding data come from
Polymarket's Gamma, Data and CLOB APIs, Etherscan's V2 proxy on chain 137, Alchemy JSON-RPC and
Relay's bridge-request lookup. Nothing from those services is redistributed here.
