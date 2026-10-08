# PolyCrawler2

Backtest-first rework of PolyCrawler: detect insider-style Polymarket wallet clusters and copy their net exposure, with every rule tunable via backtests and config sweeps.

- Spec: [`SPEC.md`](SPEC.md)
- v0.1 spec, docs, and scaffolding: [`archive/v1/`](archive/v1/)

## Quickstart

```bash
uv sync
uv run pc2 fetch --config configs/base.yaml --event-slug cbb-valp-uic-2025-03-06
```

Writes `data/markets.parquet` and `data/fills.parquet`. Cached raw JSON lives in `data/raw/`; pass `--refresh` to refetch. `--set strategy.delaySec=60` overrides config. `discover`, `backtest`, and `sweep` are not implemented yet.
