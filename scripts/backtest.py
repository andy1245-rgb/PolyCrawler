"""Run one backtest from a config file and the local parquet tape."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from polycrawler.backtest import (
    BacktestParams,
    formatSummary,
    loadInputs,
    resolveDataDirs,
    runBacktest,
)
from polycrawler.config import applyOverride, loadConfig


def paramsFrom(configPath: Path, overrides: list[str]):
    loaded = loadConfig(configPath)
    raw = {"strategy": loaded.strategy.model_dump()}
    for item in overrides:
        applyOverride(raw, item)
    return BacktestParams.model_validate(raw["strategy"]), loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy suspicious accounts after splitDate")
    parser.add_argument("--config", default="configs/insiderCases.yaml")
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--runs-dir", default="runs")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    configPath = Path(args.config)
    if not configPath.is_absolute():
        configPath = root / configPath
    params, loaded = paramsFrom(configPath, args.set)
    dirs = resolveDataDirs(root, args.data_dir, loaded.fetch.dataDir)
    fills, markets, accounts, clusterMap = loadInputs(dirs)
    endTs = fills.select(pl.col("ts").max()).collect().item()
    startTs = datetime(
        loaded.splitDate.year, loaded.splitDate.month, loaded.splitDate.day, tzinfo=timezone.utc
    )
    result = runBacktest(
        fills,
        markets,
        accounts,
        params,
        startTs,
        endTs,
        clusterMap=clusterMap,
        runsDir=root / args.runs_dir,
    )
    print(formatSummary(result))
    print(f"wrote {root / args.runs_dir / result.paramsHash}")


if __name__ == "__main__":
    main()
