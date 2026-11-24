# PolyCrawler

Backtest-first research tool for Polymarket: find insider-style wallet clusters from past data,
then ask whether copying them afterwards survives a realistic delay. For researchers and traders
who would rather see a claim falsified than a chart.

[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

## What it does

Four commands, each a step of the same pipeline. Nothing between them but Parquet on disk, so a
step can be rerun without repeating the one before it.

| Command | Input | Output |
|---|---|---|
| `pc2 fetch` | event slugs or tag/volume filters in a YAML config | `data/markets.parquet`, `fills.parquet`, `prices.parquet`, plus a raw-JSON cache |
| `pc2 discover` | the fills, before `splitDate` | `suspicious.parquet`, `funding.parquet`, `origins.parquet`, `parents.parquet`, `clusterAccounts.parquet` |
| `pc2 backtest` | fills after `splitDate` + a strategy config | `runs/<hash>/` — `params.yaml`, `summary.json`, `trades.parquet` |
| `pc2 sweep` | a grid of backtest configs | a ranked table over the grid |

A fetch prints its own shape, which is the first thing to look at:

```
markets 962
fills 10666464
accounts 469000
prices 1841
```

A backtest prints a summary whose first two lines decide whether the rest of it means anything:

```
trades 167  marked 0
noPriceSkips {'entryAttempts': 0, 'exitAttempts': 0, 'markLots': 0}  entryCoverage 1.0000
priceSources {'entryPrint': 167, 'entryQuote': 0, 'exitPrint': 0, 'exitQuote': 0}
```

`entryCoverage` is the share of copy attempts that found a price at all. A copy that could not
be priced is counted, never silently dropped.

Concretely: point `pc2 fetch` at a roster of resolved military events, and it gives you a fills
tape; run `pc2 discover` over the part of it before the split date and you get accounts flagged on
pre-split behaviour plus the clusters they form; run `pc2 backtest` on the part after the split and
you get what copying those clusters would have returned, at their delayed price.

## The measured result, and what it is worth

The corpus this project was judged on is a fresh holdout: 200 resolved military event slugs,
962 markets, **10,666,464 fills**, tape from 2023-10-15 to 2026-10-03. Discovery ran end to end on
it and produced **14 suspicious accounts out of 2,466 scored, and zero clusters** — n = 0, so
there is no cluster to copy and no statement about "how many clusters kept winning after the
split" to make.

The copy rule that the in-sample sweeps ranked first was then replayed on the same holdout:
**−72.7% mean return over n = 167 entries across 34 events and 113 accounts** (5th-percentile
bootstrap floor −0.874, win rate 7.8%, and 0 of 464 gradeable cells in the 480-cell grid clearing a
positive floor). Negative in both time halves: −0.217 before the mid-split, −0.817 after.

Both results are fails, and that is what this repository is for. What backs each number:

| Number | Value | How it was counted | Regenerable from a clone? |
|---|---:|---|---|
| Events in the holdout roster | 200 | `grep -c '^    - ' configs/oosExpansionFetch.yaml` | **yes** |
| Markets / resolved / unresolved | 962 / 913 / 49 | `markets.parquet`, recount of `resolvedAt` against `splitDate: 2026-01-01` | no — corpus not distributed |
| Fills in the holdout | 10,666,464 | `fills.parquet` row count | no — corpus not distributed |
| Candidates scored / suspicious | 2,466 / 14 | `suspicious.parquet`, `suspicious` column | no — corpus not distributed |
| Clusters found | 0 | `parents.parquet`, `clusterAccounts.parquet` — both 0 rows | no — corpus not distributed |
| Gradeable grid cells with a positive floor | 0 of 464 | `scripts/research/entrySweep.py` + `configs/sweeps/oosExpansionEntryGrid.yaml` | no — needs the burst-entry cache |
| Flagship cell | n = 167, 34 events, −0.727 | same grid, `$10k / ≤0.35 / ≤5d / ≤3mkts` | no — needs the burst-entry cache |
| Tests | 241 | `uv run pytest -q` | **yes** |

**The corpus is not in this repository.** `data/`, `runs/` and `logs/` are gitignored, so the clone
carries the roster, the configs, and the code that turns a fetch into a number — not the 11 GB of
fills behind any count above. Every figure in that table was recounted against the on-disk
artifacts and reconciled with the committed records in [`research/oosClusters.md`](research/oosClusters.md)
and [`research/status.md`](research/status.md) before it was published here; reproducing them means
re-running the fetch, not re-reading the repository.

## Quickstart

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). No key is needed for any step below.

```bash
uv sync
uv run pc2 --help
uv run pytest -q
```

Those three are the whole offline check: `uv sync` installs the project and its `pc2` entry point,
`--help` lists the four commands, and the suite prints `241 passed`.

Fetching a corpus needs network access to Polymarket's Gamma and Data APIs, which the CLOB price
fetch also uses. `--event-slug` narrows a roster config to the events you name, so a first run can
be one event rather than two hundred:

```bash
# network
uv run pc2 fetch --config configs/oosExpansionFetch.yaml --event-slug us-forces-enter-iran-by
```

`pc2 discover` additionally needs `ETHERSCAN_API_KEY` in the environment (or a `.env` at the repo
root, which is gitignored) to read Polygon collateral transfers, and `ALCHEMY_API_KEY` for on-chain
payout confirmation, which degrades to `None` without it. Relay lookups need no key but are paced at
one request per second by default.

```bash
uv run pc2 discover --config configs/oosExpansionDiscover.yaml
uv run pc2 backtest --config configs/militaryBacktest.yaml
```

Every config value can be overridden per invocation, which is how a grid cell is expressed without
editing a file:

```bash
uv run pc2 backtest --config configs/militaryBacktest.yaml --set strategy.delaySec=60
```

## How it was measured

Discovery takes only data before `splitDate` and the backtest only trades after it, so the split is
what keeps the two apart. Entry is priced from the last trade print at or before
`fill + delaySec`, inside a six-hour staleness window; when no print is inside that window the CLOB
price-history tape is consulted instead, and the row is tagged `quote` so the two populations are
reported apart rather than blended. A copy that finds neither is counted in `noPriceSkips` and
shows up in `entryCoverage`. Prices come from the tape and the CLOB, never from a midpoint, so a
quote-priced row is a published price at a published time and not an optimistic guess at a fill.

The holdout was built to be one: 200 slugs crawled from Gamma by tag, filtered by the same keyword
roster the in-sample work used, resolved-only, volume ≥ $20k, and asserted zero slug overlap against
every previously fetched directory.

Detail lives in these, all committed:

| Document | What it records |
|---|---|
| [`research/oosClusters.md`](research/oosClusters.md) | the discovery run on the 200-event tape: timings, candidate funnel, the zero-cluster result, post-split account P&L |
| [`research/status.md`](research/status.md) | the sweep and transport results in full, including the 480-cell grid table and the pre-registered PASS/FAIL gate |
| [`docs/paper-lane-records.md`](docs/paper-lane-records.md) | the paper-lane books: event time vs write time, horizon anchoring, price coverage, signal identity, and what in the live books is untrustworthy |
| [`SPEC.md`](SPEC.md) | the v0.2 draft the code was built against |
| [`SPEC-DIVERGENCES.md`](SPEC-DIVERGENCES.md) | where the code moved away from that draft, and which side should change |

`SPEC-DIVERGENCES.md` is a record of an audit, not a live bug list: it was written at v0.2.0-draft,
its line numbers have since moved, and its first divergence is now closed — the `prices` table it
called specified-but-unimplemented is implemented in [`src/polycrawler/fetch.py`](src/polycrawler/fetch.py)
and covered by [`tests/test_prices_history.py`](tests/test_prices_history.py). Read that section
against the code rather than trusting its count of tests.

## What it does not do

- **It does not ship its data.** No Parquet, no run directory, no log is tracked. A clone can read
  the code, run the suite, and re-fetch a corpus; it cannot reproduce a published count without
  doing the fetch.
- **It does not claim an edge.** The copy rule that survived in-sample selection lost on the
  holdout, and the cluster strategy had nothing to copy there at all: 0 clusters from 14 flagged
  accounts. There is no configuration in this repository that has passed an out-of-sample test.
- **It does not follow a cluster's net exposure the way `SPEC.md` describes.** The code copies
  signed BUY bursts per `(group, market, outcome)` and never forms Yes − No; sizing mirrors their
  shares rather than their net. See SD-12…16 in [`SPEC-DIVERGENCES.md`](SPEC-DIVERGENCES.md).
- **It does not trade on its own.** No loop calls the executor. `scripts/execute.py` places real
  orders only when `--live` is passed *and* `POLYMARKET_PRIVATE_KEY` is set in the same invocation,
  and only under hard per-order and open-exposure caps. Everything else is a dry run.
- **It does not cover more than one venue, one chain, or two outcomes.** Markets come from
  Polymarket, funding from Polygon collateral transfers only, and the synthetic complement `1 − p`
  is only valid for two-outcome markets.
- **It does not validate its own live book.** The paper-lane books under `data/live` are untracked
  and partly reconstructed by replay; [`docs/paper-lane-records.md`](docs/paper-lane-records.md)
  §9 states which rows are trustworthy and which are not, and §10 the rebuild that clears them.

Two known dead knobs are still declared in the config model: `minCoTradeMarkets` is read by nothing,
and three result-changing constants (`burstWindow` at 10 minutes, `staleWindow` at 6 hours,
`markHorizon` at 3,650 days) are not configurable despite the spec's "every knob is in the config
file".

## Repository layout

| Path | What is in it |
|---|---|
| `src/polycrawler/` | the package — `fetch`, `src/polycrawler/discovery/`, `strategy`, `backtest`, `priceMove`, `sweep`, `http`, `config`, `cli` |
| `configs/` | YAML configs: rosters, discovery and strategy settings, and the sweep grids under `configs/sweeps/` |
| `scripts/` | the operational layer the CLI does not cover — the live watcher, paper lanes, execution, and `scripts/research/` where the studies live |
| `tests/` | 241 tests over 27 files, plus JSON fixtures for the API shapes |
| `research/` | one document per study, each with its numbers and its verdict |
| `docs/` | the paper-lane record book |
| `archive/v1/` | the v0.1 spec, docs and scaffolding, kept for reference only |

## Licence and attribution

Apache-2.0 — see [`LICENSE`](LICENSE). Research tool, paper trading only. Not financial advice, and
not a recommendation to trade any market.

Order signing uses [`py-clob-client`](https://github.com/Polymarket/py-clob-client) and
`py-clob-client-v2` (Polymarket Engineering). Market, trade, price and funding data come from
Polymarket's Gamma, Data and CLOB APIs, Etherscan's V2 proxy on chain 137, Alchemy JSON-RPC, and
Relay's `/requests/v2` bridge lookup; nothing from those services is redistributed here.
