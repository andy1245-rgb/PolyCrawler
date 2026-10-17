"""Favorite-side burst-copy grid: does a gradeable OOS cell exist anywhere?

Pre-registered in research/favoriteBursts.md BEFORE this run: the grid (burst
size $5k/$10k x burst-average price bands spanning the whole price axis
[0,0.15) .. [0.85,1.0] plus the wide favorite [0.55,0.85) and wide
sub-favorite <0.85 bands, age 0-1d and <=5d, marketsSoFar <= 3), the gates
(PASS iff n>=20 AND p5>0 AND P(>0)>=85% AND top-event share<60%; MIN_CELL=20,
INCONCLUSIVE-THIN below) and the delay-realistic convention (first BUY print
within 300s + 50bps slippage, never-landed entries DROPPED).

Thin wrapper around the existing machinery — import, never fork: the graded
prices come from entrySweep.loadEntries's fingerprinted cache
(data/entrySweep/entries_v2_*.parquet), the cell filter/eval from
entrySweep.filterCell/evaluate (1000-draw per-event pnl/cap bootstrap,
2025-06-01 half split), and the landed/delay-realistic pieces from
oosTransport.addLanded / oosTransport.delayRealReturn / oosTransport.evalCell.

Run: uv run python scripts/research/favoriteBursts.py [--data-dir data/oos]
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

# oosTransport imports entrySweep (as esw) and researchData itself; load it
# once and take both handles off it.
_spec = importlib.util.spec_from_file_location(
    "oot", ROOT / "scripts" / "research" / "oosTransport.py")
oot = importlib.util.module_from_spec(_spec)
sys.modules["oot"] = oot
_spec.loader.exec_module(oot)
esw = oot.esw
researchData = oot.researchData

MIN_USDS = [5000.0, 10000.0]
PRICE_BANDS = [  # (label, lo, hi) on the burst-average entry price
    ("p<0.15", 0.0, 0.15),
    ("0.15-0.35", 0.15, 0.35),
    ("0.35-0.55", 0.35, 0.55),
    ("0.55-0.70", 0.55, 0.70),
    ("0.70-0.85", 0.70, 0.85),
    ("p>=0.85", 0.85, 1.0),
    ("fav 0.55-0.85", 0.55, 0.85),
    ("p<0.85 w", 0.0, 0.85),
]
AGES = {"0-1d": (None, 1.0), "5d": (None, 5.0)}  # (minAge, maxAge]; day-0 kept
MARKETS = 3  # shipped fresh shape, candidate cells only
GATE_PPOS, GATE_SHARE = 0.85, 0.60
COLS = ["minUsd", "priceBand", "age", "n", "events", "winRate", "ret", "p5",
        "P>0", "share", "h1", "h2", "landed%", "drN", "drRet", "drP5",
        "drP>0", "drShare"]


def filterBand(entries: pl.DataFrame, minUsd: float, lo: float, hi: float,
               maxAge: float) -> pl.DataFrame:
    return esw.filterCell(
        entries.filter((pl.col("price") >= lo) & (pl.col("price") < hi)),
        {"minUsd": minUsd, "maxPrice": 1e9, "ageDays": maxAge,
         "marketsSoFar": MARKETS})


def winRate(df: pl.DataFrame, col: str = "retReal") -> float | None:
    return round(float((df[col] > 0).mean()), 3) if df.height else None


def renameKeys(row: dict[str, Any]) -> dict[str, Any]:
    for src, dst in (("p", "P>0"), ("eventShare", "share")):
        if src in row:
            row[dst] = row.pop(src)
    return row


def verdict(base: dict[str, Any], dr: dict[str, Any]) -> str:
    def gate(row: dict[str, Any]) -> bool:
        return (row["n"] >= esw.MIN_CELL and row["p5"] is not None
                and row["p5"] > 0 and row["P>0"] >= GATE_PPOS
                and row["share"] < GATE_SHARE)
    if base["n"] < esw.MIN_CELL:
        return "INCONCLUSIVE-THIN"
    return "PASS" if (gate(base) and gate(dr)) else "FAIL"


def evalCell(df: pl.DataFrame, rng: random.Random) -> dict[str, Any]:
    # oot.evalCell -> esw.evaluate keys: p / eventShare; renames align it with
    # the reported COLS ("P>0", "share") so the gate and the table share names.
    base = renameKeys(oot.evalCell(df, rng))
    base["winRate"] = winRate(df)
    if df.height and int(df["landed300"].sum()):
        landed = (oot.delayRealReturn(df.filter(pl.col("landed300")))
                  .with_columns(pl.col("retReal50").alias("retReal")))
        dr = renameKeys(oot.evalCell(landed, rng))
    else:
        dr = {"n": 0, "ret": None, "p5": None, "P>0": None, "share": None}
    base.update(drN=dr["n"], drRet=dr["ret"], drP5=dr["p5"],
                **{"drP>0": dr["P>0"], "drShare": dr["share"]},
                verdict=verdict(base, dr))
    return base


def gradeEntries(entries: pl.DataFrame) -> list[dict[str, Any]]:
    rng = random.Random(7)
    rows = []
    for u in MIN_USDS:
        for (band, lo, hi) in PRICE_BANDS:
            for age, (_, maxAge) in AGES.items():
                df = filterBand(entries, u, lo, hi, maxAge)
                r = evalCell(df, rng)
                r.update(minUsd=u, priceBand=band, age=age,
                         **{"landed%": round(100 * int(df["landed300"].sum()) / max(df.height, 1), 1)})
                rows.append(r)
                print(f"done {u:.0f} {band} {age} n={r['n']} ({time.time() - t0:.0f}s)",
                      flush=True)
    # control/anchor: usd >= $10k, ANY price/age/markets (status.md 9.2 cell)
    anchor = entries.filter(pl.col("usd") >= 10000.0)
    a = evalCell(anchor, rng)
    a.update(minUsd=10000.0, priceBand="anchor any", age="any",
             burstAvgRet=round(float(anchor["ret"].mean()), 3))
    rows.append(a)
    print(f"anchor $10k+ any: n={a['n']} ret(burst-avg)={a['burstAvgRet']} "
          f"retReal={a['ret']} winRate={a['winRate']} p5={a['p5']} "
          f"P>0={a['P>0']} share={a['share']} verdict={a['verdict']}", flush=True)
    return rows


def priceLadder(entries: pl.DataFrame) -> str:
    """Monotonicity view: $10k bursts, <=5d, p5/mean-ret across the six rungs."""
    rng = random.Random(700)
    lines = []
    for (band, lo, hi) in PRICE_BANDS[:6]:
        df = filterBand(entries, 10000.0, lo, hi, 5.0)
        r = evalCell(df, rng)
        lines.append(f"{band:>9}: n={r['n']:>6} ret={r['ret']} p5={r['p5']} "
                     f"P>0={r['P>0']} win={r['winRate']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.data_dir:
        dirSets = {"CLI": [str(p) for p in researchData.researchDataDirs(args.data_dir)]}
    else:
        dirSets = {
            "INS": [str(p) for p in researchData.researchDataDirs()],
            "OOS": [str(ROOT / "data" / "oos")],
            "HOLD": [str(ROOT / "data" / "oosExpansion")],
        }
    for name, dirs in dirSets.items():
        print(f"\n== {name} ({' + '.join(dirs)}) ==", flush=True)
        entries = oot.addLanded(esw.loadEntries(dirs, args.refresh), dirs)
        rows = gradeEntries(entries)
        table = pl.DataFrame([{c: r.get(c) for c in COLS if c not in ("minUsd", "priceBand", "age")}
                              | {c: r[c] for c in ("minUsd", "priceBand", "age")}
                              | {"verdict": r["verdict"]} for r in rows])
        with pl.Config(tbl_rows=70, tbl_cols=-1, fmt_str_lengths=20):
            print(table)
        print(f"\nprice-ladder ($10k, <=5d, retReal):\n{priceLadder(entries)}")
        out = ROOT / "data" / "entrySweep" / f"favoriteBursts_{name.lower()}.parquet"
        table.write_parquet(out)
        print(f"wrote {out} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
