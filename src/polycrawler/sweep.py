"""Grid of backtests, ranked by one summary field."""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import polars as pl
import yaml

from polycrawler.backtest import BacktestParams, BacktestResult, Prepared, runPrepared

summaryFields = (
    "totalPnl",
    "capitalDeployed",
    "returnOnDeployed",
    "tradeCount",
    "winRate",
    "maxDrawdown",
    "topEvent",
    "topEventPnl",
    "topEventPnlShare",
    "pnlWithoutTopEvent",
    "capitalWithoutTopEvent",
    "returnWithoutTopEvent",
    "medianEventReturn",
    "eventCount",
    "markedCount",
    "startTs",
    "endTs",
)


@dataclass
class SweepSpec:
    name: str
    objective: str
    grid: dict
    minTrades: int = 20
    minEvents: int = 3


def loadSweep(path: str | Path) -> SweepSpec:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict) or "grid" not in raw:
        raise ValueError(f"sweep file needs a grid: {path}")
    grid = raw["grid"]
    if not isinstance(grid, dict) or not grid:
        raise ValueError(f"sweep grid is empty: {path}")
    unknown = [key for key in grid if key not in BacktestParams.model_fields]
    if unknown:
        raise ValueError(f"unknown sweep keys: {', '.join(unknown)}")
    return SweepSpec(
        name=str(raw.get("name") or Path(path).stem),
        objective=str(raw.get("objective") or "medianEventReturn"),
        grid=grid,
        minTrades=int(raw.get("minTrades", 20)),
        minEvents=int(raw.get("minEvents", 3)),
    )


def gridCombos(grid: dict) -> list[dict]:
    keys = list(grid)
    combos = []
    for values in product(*(grid[key] for key in keys)):
        combos.append(dict(zip(keys, values, strict=True)))
    return combos


def _row(result: BacktestResult) -> dict:
    row = result.params.model_dump(mode="json")
    for key in summaryFields:
        row[key] = result.summary[key]
    row["pnlByEvent"] = json.dumps(result.summary["pnlByEvent"], sort_keys=True)
    row["paramsHash"] = result.paramsHash
    return row


def runSweep(
    prepared: Prepared,
    base: BacktestParams,
    grid: dict,
    objective: str,
    minTrades: int = 20,
    minEvents: int = 3,
) -> pl.DataFrame:
    if objective not in summaryFields:
        raise ValueError(f"objective must be a summary field, got {objective}")
    cache: dict = {}
    rows = [
        _row(runPrepared(prepared, base.model_copy(update=combo), cache))
        for combo in gridCombos(grid)
    ]
    frame = pl.DataFrame(rows).with_columns(
        pl.col(objective).fill_null(-1.0e300).alias("_objective"),
        (
            (pl.col("tradeCount") >= minTrades) & (pl.col("eventCount") >= minEvents)
        ).alias("eligible"),
    )
    ranked = frame.sort(
        ["eligible", "_objective", "totalPnl", "paramsHash"],
        descending=[True, True, True, False],
    ).drop("_objective")
    return ranked.with_row_index("rank", offset=1)


def writeSweep(frame: pl.DataFrame, name: str, runsDir: str | Path = "runs") -> Path:
    out = Path(runsDir) / "sweeps"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.parquet"
    frame.write_parquet(path)
    return path


def _cell(value, kind: str) -> str:
    if value is None:
        return f"{'n/a':>14}"
    if kind == "int":
        return f"{int(value):>14}"
    if kind == "pct":
        return f"{float(value):>14.3f}"
    if kind == "price":
        return f"{float(value):>14.2f}"
    if kind == "text":
        return f"{str(value):>16}"
    return f"{float(value):>14.0f}"


def formatSweep(frame: pl.DataFrame, objective: str, limit: int | None = None) -> str:
    shown = frame if limit is None else frame.head(limit)
    money = objective in {"totalPnl", "pnlWithoutTopEvent", "maxDrawdown", "capitalDeployed"}
    headers = [
        "rank",
        "ok",
        objective,
        "totalPnl",
        "return",
        "trades",
        "events",
        "copyRule",
        "maxEntry",
        "minNet",
        "delay",
        "sizing",
        "exit",
        "slip",
    ]
    lines = ["  ".join(f"{header:>14}" for header in headers)]
    for row in shown.iter_rows(named=True):
        cells = [
            _cell(row["rank"], "int"),
            _cell("Y" if row["eligible"] else "N", "text"),
            _cell(row[objective], "money" if money else "pct"),
            _cell(row["totalPnl"], "money"),
            _cell(row["returnOnDeployed"], "pct"),
            _cell(row["tradeCount"], "int"),
            _cell(row["eventCount"], "int"),
            _cell(row["copyRule"], "text"),
            _cell(row["maxEntryPrice"], "price"),
            _cell(row["minNetUsd"], "money"),
            _cell(row["delaySec"], "int"),
            _cell(row["sizing"], "text"),
            _cell(row["exitMode"], "text"),
            _cell(row["slippageBps"], "money"),
        ]
        lines.append("  ".join(cells))
    if limit is not None and frame.height > limit:
        lines.append(f"... {frame.height - limit} more rows")
    return "\n".join(lines)
