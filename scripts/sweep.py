"""Rank a grid of backtests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from polycrawler.backtest import BacktestParams, loadInputs, prepareBacktest, resolveDataDirs
from polycrawler.config import loadConfig
from polycrawler.sweep import formatSweep, loadSweep, runSweep, writeSweep


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep strategy knobs and rank runs")
    parser.add_argument("sweep", nargs="?", default="configs/sweeps/basic.yaml")
    parser.add_argument("--config", default="configs/insiderCases.yaml")
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    configPath = Path(args.config)
    sweepPath = Path(args.sweep)
    if not configPath.is_absolute():
        configPath = root / configPath
    if not sweepPath.is_absolute():
        sweepPath = root / sweepPath
    loaded = loadConfig(configPath)
    spec = loadSweep(sweepPath)
    params = BacktestParams.model_validate(loaded.strategy.model_dump())
    dirs = resolveDataDirs(root, args.data_dir, loaded.fetch.dataDir)
    fills, markets, accounts, clusterMap = loadInputs(dirs)
    endTs = fills.select(pl.col("ts").max()).collect().item()
    startTs = datetime(
        loaded.splitDate.year, loaded.splitDate.month, loaded.splitDate.day, tzinfo=timezone.utc
    )
    prepared = prepareBacktest(fills, markets, accounts, startTs, endTs, clusterMap)
    ranked = runSweep(prepared, params, spec.grid, spec.objective, spec.minTrades, spec.minEvents)
    out = writeSweep(ranked, spec.name, root / args.runs_dir)
    kept = int(ranked.filter(pl.col("eligible")).height) if ranked.height else 0
    print(formatSweep(ranked, spec.objective, limit=args.limit))
    print(
        f"wrote {out}  ({ranked.height} runs, {kept} eligible, "
        f"objective {spec.objective}, minTrades {spec.minTrades}, minEvents {spec.minEvents})"
    )


if __name__ == "__main__":
    main()
