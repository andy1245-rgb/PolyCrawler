"""Post-burst continuation, short-horizon marks: does the control-cell drift
(the in-sample control-cell pattern: big bursts at ANY price mostly follow
through — status.md §9.2, ret +1.1% / winRate 90.9% / n=16,896 on HOLD) exist
LIVE as a short-horizon trade on the favorite/mid price bands?

Pre-registered in research/burstContinuation.md BEFORE any grading. Thin
wrapper — everything is reused read-only:

  entrySweep.py     burst trigger, fingerprinted entries caches,
                    filterCell, evaluate() seeded bootstrap (1000 event
                    draws, p5/P(>0), MIN_CELL=20)
  oosTransport.py   delay-realistic entry: landed300 next-BUY-print join and
                    nextPrice*(1+50bps) cost (addLanded / delayRealReturn)
  horizonExits.py   exit-tape marking (R2's recipe verbatim): exitTape
                    (pinned any-side print tape), markHorizon (asof forward
                    / backward / entry-carry marks with resolution
                    precedence), horizonEval (the composed gate + seeded
                    bootstrap per horizon), topEventShare
  researchData.py   researchDataDirs dir routing

Grid (pre-registered): usd >= {10k, 25k, 50k} x price bands
[0.15,0.35) / [0.35,0.55) / [0.55,0.85) / [0.85,0.98) — half-open, on the
cache's burst opening-print price — NO age / marketsSoFar gate (this
re-states the control cell, not the falsified fresh-account copy shape).
Horizons (fixed a priori): resolution (native cache retReal AND
delay-realistic retReal50) + marks at T+1h / T+6h / T+1d / T+3d / T+7d on
the delay-realistic frame (R2's exact mark recipe, sell-side 50bps,
resolution precedence). Dirs graded SEPARATELY: in-sample
[data, data/universe] (reference), OOS [data/oos], fresh holdout
[data/oosExpansion] (deciding). A live-lane candidate must PASS the composed
gate on BOTH OOS dirs separately at the same (usd, band, horizon) triple,
with delay-realistic resolution p5 > 0 on both.

Run: uv run python scripts/research/burstContinuation.py 2>&1 | tee logs/burstContinuation.log
"""

import argparse
import importlib.util
import random
import sys
import time
from datetime import timedelta
from pathlib import Path

import polars as pl

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "esw", ROOT / "scripts" / "research" / "entrySweep.py")
esw = importlib.util.module_from_spec(_spec)
sys.modules["esw"] = esw
_spec.loader.exec_module(esw)  # loadEntries / filterCell / MIN_CELL / HALF_SPLIT

_spec = importlib.util.spec_from_file_location(
    "mo", ROOT / "scripts" / "research" / "oosTransport.py")
mo = importlib.util.module_from_spec(_spec)
sys.modules["mo"] = mo
_spec.loader.exec_module(mo)  # addLanded / delayRealReturn / SLIP

_spec = importlib.util.spec_from_file_location(
    "hx", ROOT / "scripts" / "research" / "horizonExits.py")
hx = importlib.util.module_from_spec(_spec)
sys.modules["hx"] = hx
_spec.loader.exec_module(hx)  # exitTape / markHorizon / horizonEval

_spec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_spec)
sys.modules["researchData"] = researchData
_spec.loader.exec_module(researchData)  # researchDataDirs

USDS = [10000.0, 25000.0, 50000.0]
BANDS = [(0.15, 0.35), (0.35, 0.55), (0.55, 0.85), (0.85, 0.98)]
HORIZONS = {
    "t1h": timedelta(hours=1),
    "t6h": timedelta(hours=6),
    "t1d": timedelta(days=1),
    "t3d": timedelta(days=3),
    "t7d": timedelta(days=7),
}
STAKE = 10000.0  # marks computed on the largest grid stake's population only
DIR_SETS = {
    "in-sample": None,          # researchDataDirs() -> [data, data/universe]
    "oos": ["data/oos"],
    "oosExpansion": ["data/oosExpansion"],
}
ANCHOR_PRIOR = {  # shipped control cell (usd >= $10k, ANY price/age/markets)
    "in-sample": (17761, 0.006, 0.818),
    "oos": (331, 0.048, 0.94),
    "oosExpansion": (16896, 0.011, 0.909),
}
TBL = ["cell", "conv", "horizon", "n", "evts", "retMean", "medAll", "medEvt",
       "win%", "p5", "P>0", "topShare", "landed%", "verdict"]


def bandFilter(df: pl.DataFrame, usd: float, lo: float, hi: float) -> pl.DataFrame:
    """esw.filterCell with the age / marketsSoFar caps switched off (this
    test re-states the control cell, not the fresh-account copy shape), plus
    the half-open [lo, hi) price band. hi = 1e9 = ANY price (the anchor)."""
    cell = {"minUsd": usd, "maxPrice": hi, "ageDays": 1e18, "marketsSoFar": 10 ** 9}
    out = esw.filterCell(df, cell)
    if lo > 0:
        out = out.filter(pl.col("price") >= lo)
    return out


def retCol(hname: str) -> str:
    return f"ret{hname[0].upper()}{hname[1:]}"


def pct(v: float | None, digits: int = 4) -> float | None:
    return round(100 * float(v), digits) if v is not None else None


def medians(df: pl.DataFrame, col: str) -> dict[str, float | None]:
    h1df = df.filter(pl.col("ts") < esw.HALF_SPLIT)
    h2df = df.filter(pl.col("ts") >= esw.HALF_SPLIT)
    return {"medAll": pct(df[col].median()),
            "medH1": pct(h1df[col].median()),
            "medH2": pct(h2df[col].median())}


def medEvt(df: pl.DataFrame, col: str) -> float | None:
    ev = (df.group_by("eventSlug").agg(r=(pl.col(col) * 100).sum()
                                       / (pl.len() * 100.0))
          .sort("eventSlug"))
    return pct(ev["r"].median(), 3)


def gradeCell(dfNative: pl.DataFrame, dfDr: pl.DataFrame,
              landedFull: pl.DataFrame, usd: float, lo: float, hi: float,
              rng: random.Random) -> list[dict]:
    landedFullCell = bandFilter(landedFull, usd, lo, hi)
    landed = (round(100 * float(landedFullCell["landed300"].mean()), 1)
              if landedFullCell.height else 0.0)
    label = f"≥${usd/1000:g}k [{lo:g},{hi:g})"
    rows = []
    for conv, df, col in [("native", dfNative, "retReal"),
                          ("dr", dfDr, "retReal50")]:
        row = hx.horizonEval(df, col, rng)
        row.update(cell=label, conv=conv, horizon="res", landed=landed,
                   medEvt=medEvt(df, col), **medians(df, col))
        rows.append(row)
    for hname in HORIZONS:
        col = retCol(hname)
        row = hx.horizonEval(dfDr, col, rng)
        row.update(cell=label, conv="dr", horizon=hname, landed=landed,
                   medEvt=medEvt(dfDr, col), **medians(dfDr, col))
        rows.append(row)
    return rows


def anchorCheck(entries: pl.DataFrame, graded10: pl.DataFrame, label: str) -> None:
    nat = bandFilter(entries, STAKE, 0.0, 1e9)
    drf = bandFilter(graded10, STAKE, 0.0, 1e9)
    prior = ANCHOR_PRIOR[label]
    print(f"  anchor usd≥$10k ANY price: n={nat.height} "
          f"retReal={float(nat['retReal'].mean()):+.3f} "
          f"winRate={100*float((nat['retReal']>0).mean()):.1f}% "
          f"(prior n={prior[0]} / {prior[1]:+.3f} / {100*prior[2]:.1f}% | "
          f"Δn {nat.height - prior[0]:+d} | dr n={drf.height} "
          f"drRes P(>0)={100*float((drf['retReal50']>0).mean()):.1f}% | "
          f"{time.time() - t0:.0f}s)", flush=True)


def runDir(label: str, requested: list[str] | None) -> list[dict]:
    dirs = [str(p) for p in researchData.researchDataDirs(ROOT, requested)]
    print(f"=== [{label}] dirs={dirs} ({time.time() - t0:.0f}s)", flush=True)
    entries = esw.loadEntries(dirs, refresh=False)
    print(f"entries {entries.height} ({time.time() - t0:.0f}s)", flush=True)
    landedAll = mo.addLanded(entries, dirs)
    print(f"landed tape done "
          f"(landed300 {100*float(landedAll['landed300'].mean()):.2f}%) "
          f"({time.time() - t0:.0f}s)", flush=True)
    graded10 = (mo.delayRealReturn(landedAll.filter(pl.col("landed300"))
                                   .filter(pl.col("usd") >= STAKE))
                .with_columns(cost=pl.col("nextPrice") * (1 + mo.SLIP))
                .with_row_index("rid"))
    tape = hx.exitTape(dirs)
    print(f"exit tape {tape.height} prints ({time.time() - t0:.0f}s)", flush=True)
    for hname, delta in HORIZONS.items():
        graded10 = hx.markHorizon(graded10, tape, delta,
                                  f"{hname[0].upper()}{hname[1:]}")
        print(f"marked {hname} ({time.time() - t0:.0f}s)", flush=True)
    del tape
    anchorCheck(entries, graded10, label)

    rng = random.Random(7)
    rows = []
    for usd in USDS:
        for lo, hi in BANDS:
            rows.extend(gradeCell(bandFilter(entries, usd, lo, hi),
                                  bandFilter(graded10, usd, lo, hi),
                                  landedAll, usd, lo, hi, rng))
            print(f"done cell ≥${usd/1000:g}k [{lo:g},{hi:g}) "
                  f"({time.time() - t0:.0f}s)", flush=True)

    for conv, hname in [("native", "res"), ("dr", "res")] + [
            ("dr", h) for h in HORIZONS]:
        print(f"\n— [{label}] {conv} · horizon {hname} —")
        print(" | ".join(TBL))
        for r in rows:
            if r["horizon"] != hname or r["conv"] != conv:
                continue
            print(" | ".join(str(v) if v is not None else "–" for v in (
                r["cell"], r["conv"], r["horizon"], r["n"], r["events"],
                r["retMean"], r["medAll"], r["medEvt"], r["winRate"], r["p5"],
                r["p"], r["topShare"], r["landed"], r["verdict"])))
    print("\ndrift medians by dir/era (medAll · h1-half · h2-half, delay-real):")
    for r in rows:
        if r["conv"] == "native":
            continue

        def f(v: float | None) -> str:
            return f"{v:+.3f}" if v is not None else "–"
        print(f"  {r['cell']:>22} {r['horizon']:>4}: {f(r['medAll'])} · "
              f"{f(r['medH1'])} · {f(r['medH2'])}")
    return rows


def composedLane(rowsByDir: dict[str, list[dict]]) -> None:
    """Live-lane candidates: composed-gate PASS on BOTH OOS dirs separately,
    same (usd, band, horizon), delay-realistic resolution p5 > 0 on both."""
    def key(r: dict) -> str:
        return f"{r['cell']}|{r['horizon']}"

    oosDr = {key(r): r for r in rowsByDir.get("oos", []) if r["conv"] == "dr"}
    holdDr = {key(r): r for r in rowsByDir.get("oosExpansion", [])
              if r["conv"] == "dr"}
    resP5 = {r["cell"]: r["p5"] for r in rowsByDir.get("oosExpansion", [])
             if r["conv"] == "dr" and r["horizon"] == "res"}
    resP5oos = {r["cell"]: r["p5"] for r in rowsByDir.get("oos", [])
                if r["conv"] == "dr" and r["horizon"] == "res"}
    print("\ncomposed live-lane candidates "
          "(PASS both OOS dirs × same horizon × dr-res p5>0 both):", flush=True)
    lanes = []
    for k, r in holdDr.items():
        if r["horizon"] == "res":
            continue
        o = oosDr.get(k)
        if (o and r["verdict"] == "PASS" and o["verdict"] == "PASS"
                and resP5.get(k) is not None and resP5[k] > 0
                and resP5oos.get(k) is not None and resP5oos[k] > 0):
            lanes.append(k)
    if lanes:
        for k in sorted(lanes):
            print(f"  {k}", flush=True)
    else:
        print("  none — no (burstUsd, price band, horizon) triple passes "
              "both OOS dirs", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=list(DIR_SETS), default=None,
                        help="grade a single data dir (default: all three)")
    args = parser.parse_args()
    rowsByDir: dict[str, list[dict]] = {}
    for label, requested in DIR_SETS.items():
        if args.only and label != args.only:
            continue
        rowsByDir[label] = runDir(label, requested)
    composedLane(rowsByDir)
    out = ROOT / "data" / "entrySweep" / "burstContinuationCells.parquet"
    pl.DataFrame([r for rows in rowsByDir.values() for r in rows]).write_parquet(out)
    print(f"\nwrote {out} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
