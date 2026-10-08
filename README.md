# PolyCrawler2

Backtest-first rework of PolyCrawler: detect insider-style Polymarket wallet clusters and copy their net exposure, with every rule tunable via backtests and config sweeps.

- Spec: [`SPEC.md`](SPEC.md)
- v0.1 spec, docs, and scaffolding: [`archive/v1/`](archive/v1/)

## Quickstart

```bash
uv sync
uv run pc2 fetch --config configs/base.yaml --event-slug cbb-valp-uic-2025-03-06
```

Writes `data/markets.parquet` and `data/fills.parquet`. Cached raw JSON lives in `data/raw/`; pass `--refresh` to refetch. `--set strategy.delaySec=60` overrides config.

`pc2 discover` flags suspicious accounts, then traces Polygon collateral funding and writes clusters. `--step1-only` stops after the suspicious-account list. `--labels research/knownWallets.csv` prints labeled-wallet recall and which of those wallets landed in a cluster. `backtest` and `sweep` are not implemented yet. Etherscan funding calls need `ETHERSCAN_API_KEY` in `.env` (not committed).
