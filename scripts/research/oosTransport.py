"""OOS transport eval of the floor-ranked military burst-entry cells.

Thin wrapper around scripts/research/entrySweep.py: reuses its cache building
(loadEntries — same CACHE_SCHEMA_VERSION fingerprint -> data/entrySweep/
entries_v2_*.parquet), its filterCell, its evaluate() bootstrap (1000 draws of
per-event pnl/cap -> P(>0), p5 floor, 2025-06-01 half split) and its military
keyword market scoping — nothing re-implemented. What the sweep CLI cannot do
(and why this script exists):

1. an explicit lower-age gate (the candidate cell restricts entry age to
   2-5d: ageDays > 1 & <= 5), needed for the 0-1d vs 2-5d age split;
2. a delay-realistic return variant per status.md engineParity honesty
   constraint: the whole-burst cell pretends the copy bought the full burst
   average at the burst's first print. A real copy enters on the first BUY
   print AFTER the trigger; if no print lands within the 300s fill window the
   position never opens and the entry is DROPPED here (entrySweep's retReal
   falls back to the trigger price instead, which over-counts ~5.6% of
   in-sample entries per engineParity). Landed entries are priced at the
   tape's next print + 50bps slippage instead of the burst average.

Run: uv run python scripts/research/oosTransport.py --data-dir data/oos
"""

import argparse
import importlib.util
import random
import sys
import time
from pathlib import Path
from typing import Any

import polars as pl

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]
SLIP = 0.005  # 50bps slippage on the delayed entry fill

_spec = importlib.util.spec_from_file_location(
    "esw", ROOT / "scripts" / "research" / "entrySweep.py")
esw = importlib.util.module_from_spec(_spec)
sys.modules["esw"] = esw
_spec.loader.exec_module(esw)

# researchData by-path too — the C3 extraction moved RESEARCH_FETCH there, and
# entrySweep no longer re-exports it (reaching through esw broke with an
# AttributeError caught in re-review).
_spec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_spec)
sys.modules["researchData"] = researchData
_spec.loader.exec_module(researchData)  # RESEARCH_FETCH (fetch.dataDirs)

from polycrawler.backtest import dirsFromConfig  # noqa: E402  (same routing as entrySweep)

AGE_WINDOWS = {  # name -> (minAge exclusive, maxAge inclusive)
    "all": (0.0, 5.0),      # shipped rule: fresh <= 5d, <= 3 markets
    "0-1d": (0.0, 1.0),
    "2-5d": (1.0, 5.0),     # in-sample candidate
    "2-7d": (1.0, 7.0),
}
USDS = [5000.0, 7500.0, 10000.0, 12500.0]
PRICES = [0.30, 0.35, 0.40]

COLS = ["minUsd", "maxPrice", "age", "n", "retReal", "p5", "P>0", "h1", "h2",
        "events", "accts", "share", "topEvent", "topR",
        "landed%", "landed30%", "drN", "drRetReal", "drP5", "drP>0", "drShare"]


def filterCellMinAge(entries: pl.DataFrame, minUsd: float, maxPrice: float,
                     minAge: float, maxAge: float, markets: int = 3) -> pl.DataFrame:
    cell = {"minUsd": minUsd, "maxPrice": maxPrice, "ageDays": maxAge,
            "marketsSoFar": markets}
    out = esw.filterCell(entries, cell)
    if minAge > 0:
        out = out.filter(pl.col("ageDays") > minAge)
    return out


def evalCell(entries: pl.DataFrame, rng: random.Random) -> dict[str, Any]:
    """Bootstrap via entrySweep.evaluate (exact reuse: retReal col in →
    p5 floor, P(>0), h1/h2, events out), plus single-event PnL share on the
    same per-event pnl/cap table shape evaluate() uses."""
    out = dict(esw.evaluate(entries, rng))  # thin cells omit p5/p95/events keys
    if out["ret"] is None:
        out.update(account=entries["account"].n_unique(), topEvent=None,
                   eventShare=None, topR=None, events=0, p=None, p5=None)
        return out
    ev = (entries.group_by("eventSlug")
          .agg(pnl=(pl.col("retReal") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")))
    tot = ev["pnl"].sum()
    top = ev.sort("pnl", descending=True).row(0, named=True)
    out.update(account=entries["account"].n_unique(),
               topEvent=top["eventSlug"], topR=round(top["r"], 3),
               eventShare=round(float(top["pnl"]) / float(tot), 3) if tot > 0 else 1.0)
    return out


def addLanded(entries: pl.DataFrame, dirs: list[str]) -> pl.DataFrame:
    """Rebuild the next-BUY-print tape (entrySweep convention: BUYs sorted per
    (market, outcome), shift(-1), unique keep last) and mark per burst entry
    whether a delayed copy would have found a print within 300s / 30s."""
    lazy = pl.concat((pl.scan_parquet(f"{d}/fills.parquet") for d in dirs),
                     how="diagonal_relaxed")
    nextPrints = (lazy.filter(pl.col("side") == "BUY")
                  .select("ts", "marketId", "outcome", "price")
                  .sort("marketId", "outcome", "ts")
                  .with_columns(nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"),
                                nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"))
                  .unique(subset=["ts", "marketId", "outcome"], keep="last")
                  .collect())
    gap = (pl.col("nextTs") - pl.col("ts")).dt.total_seconds()
    return (entries.join(nextPrints.select("ts", "marketId", "outcome", "nextTs", "nextPrice"),
                         on=["ts", "marketId", "outcome"], how="left")
            .with_columns(landed300=pl.col("nextPrice").is_not_null() & (gap <= 300),
                          landed30=pl.col("nextPrice").is_not_null() & (gap <= 30))
            .drop("nextTs"))


def delayRealReturn(entries: pl.DataFrame) -> pl.DataFrame:
    """retReal50: entry cost = the next print after the trigger + 50bps
    (NOT the burst average), hold to resolution."""
    cost = pl.col("nextPrice") * (1 + SLIP)
    return entries.with_columns(
        retReal50=pl.when(pl.col("outcome") == pl.col("winner"))
        .then(1 / cost - 1).otherwise(-1.0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    dirs = [str(p) for p in dirsFromConfig(ROOT, args.data_dir, researchData.RESEARCH_FETCH)]
    entries = esw.loadEntries(dirs, args.refresh)
    entries = addLanded(entries, dirs)
    print(f"entries {entries.height} landed300 {100 * entries['landed300'].mean():.2f}% "
          f"({time.time() - t0:.0f}s)", flush=True)

    rng = random.Random(7)
    rows = []
    for u in USDS:
        for p in PRICES:
            for w, (mn, mx) in AGE_WINDOWS.items():
                df = filterCellMinAge(entries, u, p, mn, mx)
                base = evalCell(df, rng)
                # delay-realistic: keep only entries where a next print landed
                # within 300s, price at that print + 50bps
                landed = (delayRealReturn(df.filter(pl.col("landed300")))
                          .with_columns(pl.col("retReal50").alias("retReal")))
                dr = evalCell(landed, rng)
                rows.append({"minUsd": u, "maxPrice": p, "age": w,
                             "n": base["n"], "retReal": base["ret"], "p5": base["p5"],
                             "P>0": base["p"], "h1": base["h1"], "h2": base["h2"],
                             "events": base["events"], "accts": base["account"],
                             "share": base["eventShare"], "topEvent": base["topEvent"],
                             "topR": base["topR"],
                             "landed%": round(100 * int(df["landed300"].sum()) / max(df.height, 1), 1),
                             "landed30%": round(100 * int(df["landed30"].sum()) / max(df.height, 1), 1),
                             "drN": dr["n"], "drRetReal": dr["ret"], "drP5": dr["p5"],
                             "drP>0": dr["p"], "drShare": dr["eventShare"]})
                print(f"done {u}/{p}/{w} n={base['n']} ({time.time() - t0:.0f}s)", flush=True)
    table = pl.DataFrame(rows)
    print("\n=== candidate neighborhood (minUsd x maxPrice x age, <= 3 markets) ===")
    for r in rows:
        print(" | ".join(str(r.get(c)) for c in COLS))
    print("\nranked by native p5:")
    with pl.Config(tbl_rows=60, tbl_cols=len(COLS), fmt_str_lengths=40):
        print(table.sort("p5", descending=True, nulls_last=True))
    out = ROOT / "data" / "entrySweep" / "oosTransportCells.parquet"
    table.write_parquet(out)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
