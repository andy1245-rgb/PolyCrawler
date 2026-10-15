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


def test_dataFingerprint_coversKeywordTuple(tmp_path: Path) -> None:
    # headline of the keyword-generalization commit was untested: the cache
    # fingerprint must change with the event-keyword tuple, else the
    # military frame and the non-military complement collide on one cache
    # name (fields must exist on disk — the fingerprint stats each file)
    for name in ("fills.parquet", "markets.parquet"):
        pl.DataFrame({"x": [1]}).write_parquet(tmp_path / name)
    dirs = [str(tmp_path)]
    base = esw.dataFingerprint(dirs, keywords=("iraq",))
    assert base != esw.dataFingerprint(dirs, keywords=("iran",))
    assert base != esw.dataFingerprint(dirs, keywords=None)      # complement
    assert base == esw.dataFingerprint(dirs, keywords=("iraq",))  # stable


def test_evaluate_is_row_order_deterministic() -> None:
    # group_by row order used to feed rng.randrange indexing; evaluate now
    # sorts events on a stable key, so shuffled input rows must not move
    # any digit
    rows = [entry(T0 + timedelta(hours=3 * i), 0.2 + 0.01 * (i % 7),
                  event=f"iran-strike-{i % 19}", usd=5000 + (i % 3) * 1000)
            for i in range(60)]
    a = esw.evaluate(pl.DataFrame(rows), random.Random(7))
    b = esw.evaluate(pl.DataFrame(list(reversed(rows))), random.Random(7))
    shuffled = list(rows)
    random.Random(0).shuffle(shuffled)
    c = esw.evaluate(pl.DataFrame(shuffled), random.Random(7))
    assert a == b == c


def test_gridCellsExpandsCartesian() -> None:
    cells = esw.gridCells({"minUsd": [1000], "maxPrice": [0.2, 0.35],
                           "ageDays": [1], "marketsSoFar": [2]})
    assert len(cells) == 2
    assert cells[0] == {"minUsd": 1000, "maxPrice": 0.2, "ageDays": 1, "marketsSoFar": 2}
    assert cells[1] == {"minUsd": 1000, "maxPrice": 0.35, "ageDays": 1, "marketsSoFar": 2}


def test_runSweepRanksByFloorP5NotMean() -> None:
    # Cell A (minUsd 10000, maxPrice 0.5): two events, retReal +3.0 vs -1.0
    # -> high mean (1.0), p5 floor -1. Cell B (minUsd 7000, maxPrice 0.3):
    # two +0.1 events -> low mean (0.1), floor ~0.1. The gates are thresholds
    # so cells nest along a single axis; splitting minUsd up vs maxPrice down
    # isolates the two sets. Floor ranking must put B first even though the
    # old ret-descending sort would have picked A.
    def cell(usd: float, price: float, events: list[tuple[str, float]],
             startH: int) -> list[dict]:
        rows = []
        for ev, retReal in events:
            for i in range(24):
                rows.append(dict(entry(T0 + timedelta(hours=startH + i), price,
                                       usd=usd, event=ev), retReal=retReal))
            startH += 40
        return rows
    frame = pl.DataFrame(
        cell(12000.0, 0.45, [("a", 3.0), ("b", -1.0)], 0)
        + cell(8000.0, 0.25, [("c", 0.1), ("d", 0.1)], 2000))
    ranked = esw.runSweep(frame, {"minUsd": [10000, 7000], "maxPrice": [0.5, 0.3],
                                  "ageDays": [5], "marketsSoFar": [3]})
    rows = {(r["minUsd"], r["maxPrice"]): r for r in ranked.iter_rows(named=True)}
    bCell, aCell, empty = rows[(7000, 0.3)], rows[(10000, 0.5)], rows[(10000, 0.3)]
    assert ranked["minUsd"][0] == 7000 and ranked["maxPrice"][0] == 0.3  # floor cell wins
    assert bCell["p5"] > 0
    assert aCell["ret"] > bCell["ret"]  # the mean would have ranked A first
    assert empty["ret"] is None and empty["p5"] is None  # dead cells sink
