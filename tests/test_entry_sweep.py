"""Tests for the cached entry-sweep filter and evaluation."""

import importlib.util
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

spec = importlib.util.spec_from_file_location(
    "esw", Path(__file__).resolve().parents[1] / "scripts" / "research" / "entrySweep.py"
)
esw = importlib.util.module_from_spec(spec)
sys.modules["esw"] = esw
spec.loader.exec_module(esw)

T0 = datetime(2024, 6, 1, tzinfo=timezone.utc)


def entry(ts: datetime, price: float, usd: float = 6000, age: float = 0.5,
          markets: int = 1, event: str = "iran-strike-x", win: bool = True) -> dict:
    return {
        "ts": ts, "account": "0xa", "marketId": "m", "outcome": "Yes",
        "usd": usd, "price": price, "marketsSoFar": markets, "ageDays": age,
        "eventSlug": event, "winner": "Yes" if win else "No",
        "resolvedAt": ts,
        "fillPrice": price * 1.01,  # small slippage vs our entry price
        "isMilitary": True,
        # ret: 1/price - 1 when won (hold to resolution); retReal: fillPrice push
        "ret": 1 / price - 1 if win else -1.0,
        "retReal": (1 / (price * 1.01) - 1) if win else -1.0,
    }


def test_filterCellAppliesAllGates() -> None:
    frame = pl.DataFrame([
        entry(T0, 0.3),                              # passes all
        entry(T0 + timedelta(days=1), 0.3, age=6.0),  # age gate
        entry(T0 + timedelta(days=1), 0.3, usd=400),  # size gate
        entry(T0 + timedelta(days=1), 0.4),           # price gate
        entry(T0 + timedelta(days=1), 0.3, markets=4),  # markets gate
    ])
    out = esw.filterCell(frame, {"minUsd": 5000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3})
    assert out.height == 1


def test_evaluateSmallSampleAndSplits() -> None:
    rows = [entry(T0 + timedelta(hours=i), 0.2 + 0.01 * i, event=f"iran-strike-{i}") for i in range(25)]
    rows += [entry(T0 + timedelta(hours=25 + i), 0.2 + 0.01 * i, win=False,
                   event=f"iran-strike-loser-{i}") for i in range(25)]
    frame = pl.DataFrame(rows)
    rng = random.Random(3)
    res = esw.evaluate(frame, rng)
    assert res["n"] == 50
    assert 0 <= res["p"] <= 1
    assert res["p5"] < res["p95"]
    # 25 longshot winners (ret up to +4x) against 25 losers at -1: the mean
    # must be positive here since the synthetic wins outnumber the loss depth
    assert res["ret"] > 0
    bad = rows[:1]
    assert esw.evaluate(pl.DataFrame(bad), rng)["ret"] is None


def test_gridCellsExpandsCartesian() -> None:
    cells = esw.gridCells({"minUsd": [1000], "maxPrice": [0.2, 0.35],
                           "ageDays": [1], "marketsSoFar": [2]})
    assert len(cells) == 2
    assert cells[0] == {"minUsd": 1000, "maxPrice": 0.2, "ageDays": 1, "marketsSoFar": 2}
    assert cells[1] == {"minUsd": 1000, "maxPrice": 0.35, "ageDays": 1, "marketsSoFar": 2}


def test_runSweepRanksDescending() -> None:
    rows = [entry(T0 + timedelta(hours=i), 0.3) for i in range(30)]
    frame = pl.DataFrame(rows)
    ranked = esw.runSweep(frame, {"minUsd": [5000], "maxPrice": [0.35],
                                  "ageDays": [5], "marketsSoFar": [3]})
    assert ranked.height == 1
    assert ranked["ret"][0] is not None
