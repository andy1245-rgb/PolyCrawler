"""Horizon-exit grading: marked exit PnL at T+1h / T+1d / T+7d post entry.

Changes the outcome variable from hold-to-resolution PnL (the shipped
grading convention, which takes months) to a marked exit: the copy closes
at the first available print at or after T+H, paying 50bps sell-side
slippage, falling back to the last earlier print, and to the resolution
value when the market settled before the mark (pre-registered in
research/horizonExits.md BEFORE any grading — definitions and gates live
there).

Reuses, read-only:
  entrySweep.py    burst trigger, fingerprinted entries caches
                   (data/entrySweep/entries_v2_<hash>.parquet),
                   filterCell, evaluate() seeded bootstrap (1000 event
                   draws, p5/P(>0), MIN_CELL=20)
  oosTransport.py  delay-realistic entry: landed300 next-BUY-print join and
                   nextPrice*(1+50bps) cost (delayRealReturn)
  researchData.py  RESEARCH_FETCH / researchDataDirs / military slugs

Grades the focused candidate grid (fresh <=5d, <=3 markets) per data dir
SEPARATELY (in-sample [data, data/universe], OOS [data/oos], fresh holdout
[data/oosExpansion]) — never mixed. Mechanical gate per cell x horizon x
dir: PASS iff n >= 20 AND events >= 20 AND p5 > 0 AND P(>0) >= 0.85 AND
top-event share < 0.60; n < 20 or events < 20 -> INCONCLUSIVE-THIN;
else FAIL. Nothing tuned to results (see doc).

Run: uv run python scripts/research/horizonExits.py 2>&1 | tee logs/horizonExits.log
"""

import argparse
import importlib.util
import random
import sys
import time
import warnings
from datetime import timedelta
from pathlib import Path
from typing import Any

import polars as pl

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]

# join_asof 'by' groups can't be checked for sortedness — the order is
# pinned by construction (exitTs sort on the left, tape sort below).
warnings.filterwarnings("ignore", message="Sortedness of columns cannot be checked")

_spec = importlib.util.spec_from_file_location(
    "esw", ROOT / "scripts" / "research" / "entrySweep.py")
esw = importlib.util.module_from_spec(_spec)
sys.modules["esw"] = esw
_spec.loader.exec_module(esw)  # filterCell / evaluate / loadEntries / MIN_CELL

_spec = importlib.util.spec_from_file_location(
    "mo", ROOT / "scripts" / "research" / "oosTransport.py")
mo = importlib.util.module_from_spec(_spec)
sys.modules["mo"] = mo
_spec.loader.exec_module(mo)  # addLanded / delayRealReturn / SLIP

_spec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_spec)
sys.modules["researchData"] = researchData
_spec.loader.exec_module(researchData)  # researchDataDirs

SLIP = mo.SLIP          # 50bps entry slippage (oosTransport convention)
EXIT_SLIP = 0.005       # 50bps sell-side slippage at the marked exit
EVENT_FLOOR = 20

USDS = [5000.0, 7500.0, 10000.0, 12500.0]
PRICES = [0.30, 0.35, 0.40]
AGE_DAYS, MARKETS = 5.0, 3
SHIPPED = (5000.0, 0.35)  # the shipped cell, marked ★ in tables

HORIZONS = {  # column suffix -> exit distance from entry ts
    "t1h": timedelta(hours=1),
    "t1d": timedelta(days=1),
    "t7d": timedelta(days=7),
}
DIR_SETS = {
    "in-sample": None,          # researchDataDirs() -> [data, data/universe]
    "oos": ["data/oos"],
    "oosExpansion": ["data/oosExpansion"],
}

TBL = ["cell", "n", "evts", "retMean", "win%", "p5", "P>0", "topShare", "verdict"]


def cellDef(minUsd: float, maxPrice: float) -> dict[str, float]:
    return {"minUsd": minUsd, "maxPrice": maxPrice,
            "ageDays": AGE_DAYS, "marketsSoFar": MARKETS}


def exitTape(dirs: list[str]) -> pl.DataFrame:
    """All-print tick tape (BUY and SELL), collapsed to one price per
    (marketId, outcome, ts): deterministic keep='last' over a fully pinned
    (marketId, outcome, ts, price) sort. (The shipped tape's keep-last is
    order-unpinned on same-second ties — see research/horizonExits.md.)"""
    lazy = pl.concat((pl.scan_parquet(f"{d}/fills.parquet")
                      .select("ts", "marketId", "outcome", "price") for d in dirs),
                     how="diagonal_relaxed")
    return (lazy.sort("marketId", "outcome", "ts", "price")
            .unique(subset=["marketId", "outcome", "ts"], keep="last")
            .collect())


def markHorizon(df: pl.DataFrame, tape: pl.DataFrame, delta: timedelta,
                name: str) -> pl.DataFrame:
    """ret{name} = exitValue/cost - 1 with resolution precedence:
    resolvedAt <= target -> 1.0/0.0 (settled, no live mark exists); else
    the first print at/after the target (asof forward), else the last
    print before it (asof backward), else the paid entry print (nextPrice;
    market fell silent right after the burst — mark carries, slippage
    applies)."""
    left = (df.select("rid", "ts", "marketId", "outcome", "won", "resolvedAt",
                      "cost", "nextPrice")
            .with_columns(exitTs=pl.col("ts") + delta)
            .sort("exitTs"))
    after = left.join_asof(tape, left_on="exitTs", right_on="ts",
                            by=["marketId", "outcome"], strategy="forward")
    before = left.join_asof(tape, left_on="exitTs", right_on="ts",
                             by=["marketId", "outcome"], strategy="backward")
    marked = (after.with_columns(price_before=before["price"])
              .with_columns(exitValue=pl.when(pl.col("resolvedAt") <= pl.col("exitTs"))
                            .then(pl.when(pl.col("won")).then(1.0).otherwise(0.0))
                            .when(pl.col("price").is_not_null())
                            .then(pl.col("price") * (1 - EXIT_SLIP))
                            .when(pl.col("price_before").is_not_null())
                            .then(pl.col("price_before") * (1 - EXIT_SLIP))
                            .otherwise(pl.col("nextPrice")))
              .with_columns((pl.col("exitValue") / pl.col("cost") - 1)
                            .alias(f"ret{name}")))
    return df.join(marked.select("rid", f"ret{name}"), on="rid", how="left")


def topEventShare(df: pl.DataFrame, retCol: str) -> float | None:
    ev = df.group_by("eventSlug").agg(pnl=(pl.col(retCol) * 100).sum())
    tot = float(ev["pnl"].sum())
    if tot <= 0:
        return None
    return round(float(ev["pnl"].max()) / tot, 3)


def horizonEval(df: pl.DataFrame, retCol: str, rng: random.Random) -> dict[str, Any]:
    row: dict[str, Any] = {"n": df.height}
    if df.height < esw.MIN_CELL or df["eventSlug"].n_unique() < EVENT_FLOOR:
        row.update(events=df["eventSlug"].n_unique(), retMean=None,
                   winRate=None, p5=None, p=None, topShare=None,
                   verdict="INCONCLUSIVE-THIN")
        return row
    exp = esw.evaluate(df.with_columns(pl.col(retCol).alias("retReal")), rng)
    share = topEventShare(df, retCol)
    verdict = ("PASS" if exp["p5"] > 0 and exp["p"] >= 0.85
               and share is not None and share < 0.60 else "FAIL")
    row.update(events=exp["events"],
               retMean=exp["ret"],
               winRate=round(100 * float((df[retCol] > 0).mean()), 1),
               p5=exp["p5"], p=round(exp["p"], 3), topShare=share,
               verdict=verdict)
    return row


def gradeCell(minUsd: float, maxPrice: float, graded: pl.DataFrame,
              landedFull: pl.DataFrame, rng: random.Random) -> list[dict[str, Any]]:
    """One pre-registered grid cell over the delay-realistic graded frame
    (landed300 subset), evaluated at every horizon. landed300% is measured
    on the whole-burst frame (the share of entries a delayed copy could
    execute), NOT on the landed-only grades."""
    cell = cellDef(minUsd, maxPrice)
    base = esw.filterCell(graded, cell)
    settled = esw.filterCell(landedFull, cell)
    landed = round(100 * float(settled["landed300"].mean()), 1) if settled.height else 0.0
    rows = []
    for hname in HORIZONS:
        row = horizonEval(base, f"ret{hname}", rng)
        rows.append({"cell": f"${minUsd/1000:g}k/≤{maxPrice:g}",
                     "horizon": hname, "landed": landed, **row})
    return rows


def shippedCorrelations(graded: pl.DataFrame) -> None:
    df = esw.filterCell(graded, cellDef(*SHIPPED))
    print(f"  shipped-cell correlations (n={df.height}, "
          f"resolution winRate {100*float(df['won'].mean()):.1f}%):", flush=True)
    for hname in HORIZONS:
        pearson = df.select(pl.corr(f"ret{hname}", "retReal50")).item()
        spearman = df.select(pl.corr(f"ret{hname}", "retReal50",
                                     method="spearman")).item()
        print(f"    {hname}: corr(ret, retReal50) pearson={pearson:.3f} "
              f"spearman={spearman:.3f}", flush=True)


def runDir(label: str, requested: list[str] | None) -> None:
    dirs = [str(p) for p in researchData.researchDataDirs(ROOT, requested)]
    print(f"=== [{label}] dirs={dirs} ({time.time() - t0:.0f}s)", flush=True)
    entries = esw.loadEntries(dirs, refresh=False)
    print(f"entries {entries.height} ({time.time() - t0:.0f}s)", flush=True)
    tape = exitTape(dirs)
    print(f"exit tape {tape.height} prints ({time.time() - t0:.0f}s)", flush=True)
    landedAll = mo.addLanded(entries, dirs)
    graded = (mo.delayRealReturn(landedAll.filter(pl.col("landed300")))
              .with_columns(cost=pl.col("nextPrice") * (1 + SLIP))
              .with_row_index("rid"))
    for hname, delta in HORIZONS.items():
        graded = markHorizon(graded, tape, delta, hname)
        print(f"marked {hname} ({time.time() - t0:.0f}s)", flush=True)
    del tape

    whole = esw.filterCell(entries, cellDef(*SHIPPED))
    dr = esw.filterCell(graded, cellDef(*SHIPPED))
    print(f"  resolution truth (shipped $5k/≤0.35): whole-burst n={whole.height} "
          f"retReal={float(whole['retReal'].mean()):.3f} "
          f"winRate={100*float(whole['won'].mean()):.1f}% | "
          f"delay-real n={dr.height} retReal50={float(dr['retReal50'].mean()):.3f}",
          flush=True)

    rng = random.Random(7)
    allRows = []
    for u in USDS:
        for p in PRICES:
            allRows.extend(gradeCell(u, p, graded, landedAll, rng))
            print(f"done cell ${u/1000:g}k/≤{p:g} ({time.time() - t0:.0f}s)",
                  flush=True)

    star = f"${SHIPPED[0]/1000:g}k/≤{SHIPPED[1]:g}"
    for hname in HORIZONS:
        print(f"\n— [{label}] horizon {hname} (fresh ≤5d, ≤3 mkts; ★ = shipped) —")
        print(" | ".join(TBL))
        for r in allRows:
            if r["horizon"] != hname:
                continue
            mark = "★" if r["cell"] == star else ""
            print(" | ".join(str(v) if v is not None else "–" for v in
                            (f"{r['cell']}{mark}", r["n"], r["events"],
                             r["retMean"], r["winRate"], r["p5"], r["p"],
                             r["topShare"], r["verdict"])))
    seen: set[str] = set()
    print("landed300%: " + ", ".join(
        f"{r['cell']} {r['landed']}%" for r in allRows
        if not (r["cell"] in seen or seen.add(r["cell"]))))
    shippedCorrelations(graded)
    print(flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=list(DIR_SETS), default=None,
                        help="grade a single data dir (default: all three)")
    args = parser.parse_args()
    for label, requested in DIR_SETS.items():
        if args.only and label != args.only:
            continue
        runDir(label, requested)
    print(f"done ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
