"""Burst-entry sweep engine: cache the military burst-entry tape once, then
evaluate any threshold grid instantly.

Semantics follow scripts/research/militarySweep.py exactly (verified against
its outputs): entries are per (account, market, outcome) 10-minute bursting
windows; entry price is the burst's running average; realistic fill price is
the next BUY print in the same (market, outcome) within FILL_WINDOW_SEC
(300s default); ret is hold-to-resolution; retReal uses the fill price.
Per-event PnL is resampled (bootstrap draws of events) for P(>0), with
2025-06-01 time-half stability and neighbor stability, so results stay
directly comparable to the validated +71%/+82% research cell.

Cache: data/entrySweep/entries_<hash>.parquet (hash of data-dir fill
fingerprints, see --refresh).

Run: uv run python scripts/research/entrySweep.py \
        [--grid configs/sweeps/militaryEntryGrid.yaml] [--refresh]
"""

import argparse
import hashlib
import itertools
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from polycrawler.backtest import dirsFromConfig
from polycrawler.config import Config, FetchConfig

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "entrySweep"

# Research cells span the accrued universe (data/ + data/universe); dir
# resolution goes through the config system like the engine side.
RESEARCH_FETCH = Config(fetch=FetchConfig(dataDirs=["data", "data/universe"]))

FILL_WINDOW_SEC = 300
HALF_SPLIT = datetime(2025, 6, 1, tzinfo=timezone.utc)
BOOTS = 1000
MIN_CELL = 20

MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela",
            "nato", "strike")

GRID_AXES = {
    "minUsd": [500, 1000, 2000, 5000, 10000, 20000],
    "maxPrice": [0.2, 0.35, 0.5, 0.65],
    "ageDays": [1, 2, 3, 5, 7],
    "marketsSoFar": [1, 2, 3, 5],
}


# ------------------------------------------------------------------ build ---

def dataFingerprint(dirs: list[str]) -> str:
    digest = hashlib.sha1()
    for d in dirs:
        p = Path(d) / "fills.parquet"
        digest.update(str(Path(d).resolve()).encode())
        digest.update(str(p.stat().st_size).encode())
    return digest.hexdigest()[:10]


def militaryMarketsTable(markets: pl.DataFrame) -> pl.DataFrame:
    bases = markets.unique("marketId", keep="last").select(
        "marketId", "eventSlug", "winner",
        pl.coalesce("resolvedAt", "endDate").alias("resolvedAt"))
    return bases.filter(pl.col("eventSlug").map_elements(
        lambda s: any(k in (s or "").lower() for k in MILITARY), return_dtype=pl.Boolean))


def buildEntries(dirs: list[str]) -> pl.DataFrame:
    lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet") for d in dirs], how="diagonal_relaxed")
    markets = pl.concat(
        [pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
    milMarkets = militaryMarketsTable(markets)
    cols = ["ts", "account", "marketId", "outcome", "side", "size", "price"]
    firstSeen = lazy.group_by("account").agg(firstTs=pl.col("ts").min()).collect()
    entries = (
        lazy.filter(pl.col("side") == "BUY").drop("side")
        .sort("account", "marketId", "outcome", "ts")
        .with_columns(
            burst=(pl.col("ts").diff().over("account", "marketId", "outcome")
                   .fill_null(pl.duration(days=1)) > pl.duration(minutes=10))
            .cum_sum().over("account", "marketId", "outcome"))
        .group_by("account", "marketId", "outcome", "burst")
        .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(),
             shares=pl.col("size").sum())
        .with_columns(price=pl.col("usd") / pl.col("shares"))
        .drop("burst", "shares")
        .collect()
    )
    entries = (entries.join(milMarkets, on="marketId").join(firstSeen, on="account")
               .sort("account", "ts")
               .with_columns(
                   marketsSoFar=pl.col("marketId").is_first_distinct().cast(pl.Int32).cum_sum().over("account"),
                   ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                   isMilitary=pl.lit(True),
                   won=pl.col("outcome") == pl.col("winner"),
                   ret=pl.when(pl.col("winner").is_null()).then(None)
                   .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1)
                   .otherwise(-1.0))
               .filter(pl.col("ret").is_not_null()))
    tape = (lazy.filter(pl.col("side") == "BUY")
            .select("ts", "marketId", "outcome", "price")
            .sort("marketId", "outcome", "ts")
            .with_columns(nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"),
                          nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"))
            .with_columns(
                fillPrice=pl.when(
                    (pl.col("nextTs") - pl.col("ts")).dt.total_seconds() <= FILL_WINDOW_SEC)
                .then(pl.col("nextPrice")).otherwise(pl.col("price")),
            )
            .unique(subset=["ts", "marketId", "outcome"], keep="last").collect())
    entries = (entries.drop("price")
               .join(tape.select("ts", "marketId", "outcome", "price", "fillPrice"),
                     on=["ts", "marketId", "outcome"], how="left")
               .with_columns(
                   retReal=pl.when(pl.col("winner").is_null()).then(None)
                   .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("fillPrice") - 1)
                   .otherwise(-1.0)))
    return entries.drop("firstTs")


def loadEntries(dirs: list[str], refresh: bool) -> pl.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"entries_{dataFingerprint(dirs)}.parquet"
    if cache.exists() and not refresh:
        frame = pl.read_parquet(cache)
        print(f"loaded {frame.height} cached entries ({cache.name})", flush=True)
        return frame
    frame = buildEntries(dirs)
    frame.write_parquet(cache)
    print(f"built {frame.height} entries -> {cache} ({time.time() - t0:.0f}s)", flush=True)
    return frame


# -------------------------------------------------------------- evaluate ---

def filterCell(entries: pl.DataFrame, cell: dict[str, float]) -> pl.DataFrame:
    out = entries.filter(
        (pl.col("usd") >= float(cell["minUsd"]))
        & (pl.col("price") <= float(cell["maxPrice"]))
        & (pl.col("ageDays") <= float(cell["ageDays"]))
        & (pl.col("marketsSoFar") <= int(cell["marketsSoFar"])))
    return out


def evaluate(df: pl.DataFrame, rng: random.Random) -> dict[str, Any]:
    row: dict[str, Any] = {"n": df.height}
    if df.height < MIN_CELL:
        row["ret"] = row["p"] = row["h1"] = row["h2"] = None
        return row
    ev = (df.group_by("eventSlug")
          .agg(pnl=(pl.col("retReal") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")))
    events = list(ev.iter_rows(named=True))
    boots = []
    for _ in range(BOOTS):
        samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
        boots.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
    boots.sort()
    h1 = df.filter(pl.col("ts") < HALF_SPLIT)["retReal"].mean()
    h2 = df.filter(pl.col("ts") >= HALF_SPLIT)["retReal"].mean()
    row.update({
        "ret": round(df["retReal"].mean(), 3),
        "p": sum(1 for b in boots if b > 0) / len(boots),
        "p5": round(boots[50], 3),
        "p95": round(boots[BOOTS - 51], 3),
        "h1": round(h1, 3) if h1 is not None else None,
        "h2": round(h2, 3) if h2 is not None else None,
        "events": len(events),
    })
    return row


GRID_KEYS = list(GRID_AXES)


def gridCells(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    cells = []
    for combo in itertools.product(*(grid.get(k, GRID_AXES[k]) for k in GRID_KEYS)):
        cells.append(dict(zip(GRID_KEYS, combo)))
    return cells


def runSweep(entries: pl.DataFrame, grid: dict[str, list[Any]]) -> pl.DataFrame:
    rng = random.Random(7)
    rows = []
    for cell in gridCells(grid):
        row = dict(cell)
        row.update(evaluate(filterCell(entries, cell), rng))
        rows.append(row)
    return pl.DataFrame(rows).sort(["p5", "ret"], descending=True, nulls_last=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--grid", default="configs/sweeps/militaryEntryGrid.yaml")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    dirs = [str(p) for p in dirsFromConfig(ROOT, args.data_dir, RESEARCH_FETCH)]
    spec = yaml.safe_load(Path(args.grid).read_text()) or {}
    grid = spec.get("grid") or {}
    entries = loadEntries(dirs, args.refresh)
    ranked = runSweep(entries, grid)
    good = ranked.filter(pl.col("ret").is_not_null())
    with pl.Config(tbl_rows=60, fmt_str_lengths=30):
        print(good.head(args.limit))
    print(f"cells {ranked.height} ({good.height} eligible) "
          f"({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
