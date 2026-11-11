# PolyCrawler2

Backtest-first detection of insider-style wallet clusters on Polymarket. Net exposure is
reconstructed by tracing Polygon collateral funding rather than inferred from trade timing,
and every strategy rule is tunable through config files.

- Spec: [`SPEC.md`](SPEC.md)
- Where the code has moved away from that spec, and which side should change:
  [`SPEC-DIVERGENCES.md`](SPEC-DIVERGENCES.md)
- The paper-lane books: time semantics, horizon anchoring, price coverage, signal identity, and
  what in the live books is untrustworthy: [`docs/paper-lane-records.md`](docs/paper-lane-records.md)
- v0.1 spec, docs, and scaffolding: [`archive/v1/`](archive/v1/) (reference only)

## Status

Four working `pc2` commands:

| Command | Behaviour |
|---|---|
| `pc2 fetch` | Markets and fills to `data/markets.parquet` + `data/fills.parquet`. Raw JSON cached in `data/raw/`; `--refresh` refetches. `--set strategy.delaySec=60` overrides any config value. |
| `pc2 discover` | Flags suspicious accounts from pre-`splitDate` behaviour, traces Polygon collateral funding, writes `data/funding.parquet` + `data/clusterAccounts.parquet`. `--step1-only` stops after the suspicious-account list. `--labels <csv>` prints labeled-wallet recall and which labeled wallets landed in a cluster. |
| `pc2 backtest` | Replays copied buys off the local parquet tape with no lookahead; writes a run to `runs/<hash>/`. |
| `pc2 sweep` | Runs a grid of backtest configs and ranks them by one summary field. |

Paper-lane book-keeping, execution-fill stamps, and the weekly lane readout live in
`scripts/` rather than as `pc2` subcommands.

**Not implemented:** there is no automated live trading loop. `scripts/execute.py` places
real CLOB orders only under `--live`, which requires `POLYMARKET_PRIVATE_KEY` in the
environment. Nothing here is a validated edge — the OOS and falsification sweeps under
`research/` exist largely to try to kill the candidates before money is risked.

## Quickstart

```bash
uv sync
uv run pc2 fetch --config configs/base.yaml --event-slug cbb-valp-uic-2025-03-06
uv run pc2 discover --config configs/base.yaml
```

`discover` needs `ETHERSCAN_API_KEY` in `.env` (not committed) for the funding trace.

## Design

**Why backtest first.** The question is not whether an edge exists but whether one survives
a realistic copy delay. A live result is unfalsifiable, so discovery and strategy are plain
functions over Parquet — no network, no database, no clock — and identical inputs plus an
identical config produce an identical result.

**What a cluster is.** A parent funding wallet plus the Polymarket accounts it funded, held
as one position: per market, the cluster's Yes shares minus its No shares.

**Why funding traces.** An insider reuses one bankroll to fund their wallets, and that flow
is on-chain permanently. Trade correlation is confounded by ordinary co-movement and by
anyone copying a public signal; collateral arriving at a set of fresh accounts is a far
narrower filter, so the expensive work happens once, at the funding layer.

## Testing

212 tests across 26 files, all passing:

```bash
uv run pytest
```

## License

Apache-2.0 — see [`LICENSE`](LICENSE).

Research tool, paper trading only. Not financial advice, and not a recommendation to trade
any market.
