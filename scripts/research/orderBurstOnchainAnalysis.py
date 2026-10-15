"""Burst-vs-order analysis on the on-chain rebuild (research/ideasResearch.md #2,
answered from Polygon logs instead of Dune, whose site/key path is blocked).

Reads the cached sampled-day legs from scripts/research/orderBurstOnchain.py
(data/raw/dune/onchainBuy_<date>.csv: ts, account, marketId, outcome, shares,
price, usd, orderHash) and rebuilds the shipped military cell both ways on the
SAME legs, reusing duneOrderBurst.py's entry/report machinery:
  burst level  = sum of BUY fills inside each 10-minute window (shipped rule)
  order level  = one entry per signed order_hash, fills reassembled across time
Wallet age (firstTs) and the realistic-fill tape come from the FULL
fills.parquet universe restricted to military markets, so ageDays/marketsSoFar
stay honest rather than being computed on the sampled legs only.

Caveat baked into the output: legs exist only on the --per-month sampled days,
so counts are a sample, not the full history; the comparison between the two
definitions on the same days is still apples-to-apples.

Run:  uv run python scripts/research/orderBurstOnchainAnalysis.py [--dir data/raw/dune]
"""

import importlib.util
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location(
    "dob", ROOT / "scripts" / "research" / "duneOrderBurst.py")
dob = importlib.util.module_from_spec(spec)
sys.modules["dob"] = dob
spec.loader.exec_module(dob)  # burstEntries, orderEntries, annotate, report, RULE_MIN_USD

_spec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_spec)
sys.modules["researchData"] = researchData
_spec.loader.exec_module(researchData)  # researchDataDirs, militaryMarketsFrame

LEG_FIELDS = ["ts", "account", "marketId", "outcome", "shares", "price",
              "usd", "orderHash", "exchange"]
MID = int(dob.RULE_MIN_USD)
LOW = 1000


def loadLegs(dir_: Path) -> tuple[pl.DataFrame, int, int]:
    """Legs from the sampled-day caches, plus (sampled days, days with legs).
    Each CSV is parsed exactly once — the frame itself carries the
    header-only check, so no second read for a height count.

    Header-only days count as sampled (a zero-leg day is a valid pull
    result); days whose rows all lack a ts are not counted as legs. If no
    day has any legs, exit with a clear message instead of letting
    pol.concat raise its ValueError."""
    caches = sorted(dir_.glob("onchainBuy_*.csv"))
    if not caches:
        sys.exit(f"no onchainBuy_*.csv under {dir_}; run orderBurstOnchain.py first")
    frames = []
    for p in caches:
        frame = pl.read_csv(p, infer_schema_length=0)
        if frame.height <= 1:
            continue  # header-only day: sampled, but no legs
        frame = frame.select(LEG_FIELDS).with_columns(
            pl.col("ts").str.to_datetime(time_zone="UTC", strict=False),
            pl.col("shares").cast(pl.Float64), pl.col("price").cast(pl.Float64),
            pl.col("usd").cast(pl.Float64))
        frames.append(frame.drop_nulls("ts"))
    fills = pl.concat(frames, how="vertical")
    return (fills.unique(subset=["marketId", "orderHash", "account", "ts"], keep="first"),
            len(caches), len(frames))


def universeFills(dirs: list[Path]) -> pl.DataFrame:
    """All BUY fills of the tracked universe (full tape — firstTs here must
    match the research convention: wallet age counts markets of ANY category,
    not just military)."""
    parts = []
    for d in dirs:
        if (d / "fills.parquet").exists():
            parts.append(pl.scan_parquet(d / "fills.parquet").filter(
                pl.col("side") == "BUY").with_columns(
                (pl.col("size") * pl.col("price")).alias("usd"))
                .select("ts", "account", "marketId", "outcome", "price", "usd")
                .collect())
    return pl.concat(parts, how="diagonal_relaxed")


def spannedOrderCount(fills: pl.DataFrame, orders: pl.DataFrame) -> tuple[int, int]:
    """Orders >=MIN whose fills cross more than one 10-minute burst window —
    the picks no 10-minute-burst rule can ever see."""
    windows = (fills.sort("ts")
               .with_columns(newWindow=(pl.col("ts").diff()
                                        .over(["account", "marketId", "outcome", "orderHash"])
                                        .dt.total_seconds() > dob.BURST_WINDOW_SEC)
                             .fill_null(True))
               .group_by(["account", "marketId", "outcome", "orderHash"])
               .agg(nWindows=pl.col("newWindow").sum())
               .join(orders.filter(pl.col("usd") >= MID)
                     .select("account", "marketId", "outcome", "orderHash"),
                     on=["account", "marketId", "outcome", "orderHash"], how="semi"))
    return windows.filter(pl.col("nWindows") > 1).height, windows.height


def buildTape(universe: pl.DataFrame) -> pl.DataFrame:
    """Realistic fill: next BUY print in the same (market, outcome) within 5 min."""
    return (universe.sort("marketId", "outcome", "ts")
            .with_columns(nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"),
                          nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"))
            .with_columns(fillPrice=pl.when(
                (pl.col("nextTs") - pl.col("ts")).dt.total_seconds() <= dob.FILL_WINDOW_SEC)
                .then(pl.col("nextPrice")).otherwise(pl.col("price")))
            .unique(subset=["ts", "marketId", "outcome"], keep="last")
            .select("ts", "marketId", "outcome", "fillPrice"))


def addRetReal(entries: pl.DataFrame, tape: pl.DataFrame) -> pl.DataFrame:
    return (entries
            .join(tape, on=["ts", "marketId", "outcome"], how="left")
            .with_columns(retReal=pl.when(pl.col("winner").is_null()).then(None)
                          .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("fillPrice") - 1)
                          .otherwise(-1.0)))


def parseArgs():
    """CLI parsing, only on the real command line (the monitor calls
    main(dir_=...) directly with its own in-process arguments)."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=None,
                        help="directory holding the onchainBuy_*.csv day caches")
    parser.add_argument("--data-dir", action="append", default=None)
    return parser.parse_args()


def main(dir_: str | Path | None = None) -> None:
    # dir_ argument (the monitor's in-process call) wins over --dir > default
    # and skips argv parsing entirely.
    requested = None
    if dir_ is None:
        args = parseArgs()
        requested = args.data_dir
        dir_ = args.dir or ROOT / "data" / "raw" / "dune"
    dir_ = Path(dir_)
    # fills/markets dirs routed through the config system (same precedence as
    # the engine); defaults keep the data/ + data/universe research scope.
    fillDirs = researchData.researchDataDirs(ROOT, requested)
    fillsAll, sampledDays, daysWithLegs = loadLegs(dir_)   # each csv read once
    print(f"sampled days: {daysWithLegs} with legs of {sampledDays} pulled "
          f"({time.time() - t0:.0f}s)\n")

    markets = researchData.militaryMarketsFrame(fillDirs)
    militarySet = set(markets["marketId"].to_list())
    print(f"military markets: {len(militarySet)} across {markets['eventSlug'].n_unique()} events",
          flush=True)

    if fillsAll.height == 0:
        sys.exit(f"{daysWithLegs} day cache(s) under {dir_} carry no legs; "
                 "run orderBurstOnchain.py again once more days are pulled")
    fills = fillsAll.filter(pl.col("marketId").is_in(militarySet))
    universe = universeFills(fillDirs)
    firstSeen = universe.group_by("account").agg(firstTs=pl.col("ts").min())
    tape = buildTape(universe)
    print(f"legs {fills.height} military fills on sampled days, "
          f"universe tape from {universe.height} BUY fills ({time.time() - t0:.0f}s)")

    base = addRetReal(dob.annotate(dob.burstEntries(fills), markets, firstSeen), tape)
    orders = addRetReal(dob.annotate(dob.orderEntries(fills), markets, firstSeen), tape)
    print(f"entries: burst-level {base.height}, order-level {orders.height} ({time.time() - t0:.0f}s)")

    flt = lambda df: df.filter((pl.col("usd") >= MID) & (pl.col("price") <= 0.50))
    rng = random.Random(7)
    rows = [
        dob.report("burst >=5k <=0.50 (shipped def)", flt(base), rng),
        dob.report("order >=5k <=0.50 (order_hash def)", flt(orders), rng),
        dob.report("burst >=1k <=0.50 (lower thr ref)", base.filter(
            (pl.col("usd") >= LOW) & (pl.col("price") <= 0.50)), rng),
        dob.report("order >=1k <=0.50 (lower thr ref)", orders.filter(
            (pl.col("usd") >= LOW) & (pl.col("price") <= 0.50)), rng),
    ]
    fresh = (pl.col("ageDays") <= 3) & (pl.col("marketsSoFar") <= 3)
    bKeys = set(map(tuple, flt(base.filter(fresh)).select("account", "marketId", "outcome").iter_rows()))
    oKeys = set(map(tuple, flt(orders.filter(fresh)).select("account", "marketId", "outcome").iter_rows()))
    print(f"\nfresh >=5k <=0.50: burst-level {len(bKeys)} (account,market,outcome) picks, "
          f"order-level {len(oKeys)}, shared {len(bKeys & oKeys)}, "
          f"order-only {len(oKeys - bKeys)}, burst-only {len(bKeys - oKeys)}")
    over, tot = spannedOrderCount(fills, orders)
    print(f"orders >=$5k spanning >1 burst window (invisible to bursts): {over} of {tot}")

    out = {"rows": rows, "overlap": {
        "freshBurst": len(bKeys), "freshOrder": len(oKeys),
        "shared": len(bKeys & oKeys), "orderOnly": len(oKeys - bKeys),
        "burstOnly": len(bKeys - oKeys), "spannedOrders": over, "spannedTotal": tot,
        "sampledDays": daysWithLegs, "generatedAt": datetime.now(timezone.utc).isoformat()}}
    (dir_ / "orderBurstOnchainReport.json").write_text(json.dumps(out, indent=2))
    print(f"\nreport -> {dir_ / 'orderBurstOnchainReport.json'} "
          f"; done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
