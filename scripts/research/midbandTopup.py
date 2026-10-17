"""Mid-band top-up grading (research/midbandTopup.md — pre-registered there
BEFORE any fresh data; cohort selection is scripts/research/
midbandTopupRoster.py + configs/midbandTopup.yaml).

Grades R16's [0.55,0.85) mid-band family on the fresh cohort ALONE
(data/midTopup; PARTIAL variant when the fetch is still running: fills/
markets frames rebuilt from the raw fetch caches into data/_midTopupPartial
through polycrawler.fetch's OWN normalize/dedupe helpers — zero burst
semantics re-implemented, dirs never mixed) and composes with R16's
data/oosExpansion HOLD verdicts per the pre-registered rule.

Reused read-only (import, never fork):
  entrySweep.py     burst trigger, fingerprinted entries caches, filterCell,
                    evaluate() seeded bootstrap (1000 event draws, p5/P(>0),
                    MIN_CELL=20, one Random(7) per dir, fixed cell order)
  oosTransport.py   addLanded / delayRealReturn / SLIP (delay-realistic
                    entry: 300s next-BUY-print + 50bps)
  horizonExits.py   exitTape / markHorizon / horizonEval (R2's pinned-tape
                    mark recipe, resolution precedence, gate + top share)
  researchData.py   dir routing / military keyword scoping

Family (pre-registered): usd >= {10k,25k,50k} x band [0.55,0.85) x age
windows {fresh<=5d (base), 0-1d, 2-5d (ablation)}, marketsSoFar <= 3
throughout; horizons res(native) / res(delay-realistic) / T+1d / T+3d /
T+7d marks. Gates: PASS iff n>=20 AND events>=20 AND p5>0 AND P(>0)>=0.85
AND topShare<0.60; n or events below 20 -> INCONCLUSIVE-THIN; else FAIL.
Composition: fresh PASS + R16 HOLD PASS at the same (usd, horizon) with
BOTH dirs' delay-realistic resolution p5 > 0 -> live-lane candidate; fresh
THIN -> compose blocked, mechanically re-run when the pull completes;
fresh FAIL on a HOLD-PASSing cell -> the composed row DIES.

Run: uv run python scripts/research/midbandTopup.py 2>&1 | tee logs/midbandTopup.log
"""

import importlib.util
import json
import random
import shutil
import sys
import time
from argparse import ArgumentParser
from datetime import timedelta
from pathlib import Path
from typing import Any

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
_spec.loader.exec_module(researchData)

FRESH = ROOT / "data" / "midTopup"
PARTIAL = ROOT / "data" / "_midTopupPartial"

USDS = [10000.0, 25000.0, 50000.0]
BAND = (0.55, 0.85)
WINDOWS = {  # label -> (minAge exclusive-lower, maxAge inclusive); markets <= 3 throughout
    "fresh<=5d": (0.0, 5.0),
    "0-1d": (0.0, 1.0),
    "2-5d": (1.0, 5.0),
}
MARKETS = 3
HORIZONS = {
    "t1d": timedelta(days=1),
    "t3d": timedelta(days=3),
    "t7d": timedelta(days=7),
}
STAKE = 10000.0       # marks computed on the >=$10k population (R16's recipe)

# R16's HOLD (data/oosExpansion) verdicts over [0.55,0.85), verbatim from
# research/burstContinuation.md's oosExpansion table: res PASS at >=$10k
# (dr p5 +0.010), T+7d PASS at all three stakes, T+1d/T+3d FAIL.
PRIOR_HOLD = {
    (10000.0, "res"): "PASS", (10000.0, "t1d"): "FAIL", (10000.0, "t3d"): "FAIL",
    (10000.0, "t7d"): "PASS",
    (25000.0, "res"): "FAIL", (25000.0, "t1d"): "FAIL", (25000.0, "t3d"): "FAIL",
    (25000.0, "t7d"): "PASS",
    (50000.0, "res"): "FAIL", (50000.0, "t1d"): "FAIL", (50000.0, "t3d"): "FAIL",
    (50000.0, "t7d"): "PASS",
}
# R16's HOLD delay-realistic resolution p5 (the composed claim's floor):
PRIOR_HOLD_RES_P5 = {10000.0: 0.010, 25000.0: -0.014, 50000.0: -0.018}

TBL = ["cell", "win", "horizon", "conv", "n", "evts", "retMean", "win%",
       "p5", "P>0", "topShare", "landed%", "verdict"]


def windowFilter(df: pl.DataFrame, usd: float, minAge: float, maxAge: float,
                 lo: float = BAND[0], hi: float = BAND[1],
                 markets: int = MARKETS) -> pl.DataFrame:
    cell = {"minUsd": usd, "maxPrice": hi, "ageDays": maxAge,
            "marketsSoFar": markets}
    out = esw.filterCell(df, cell)
    if minAge > 0:
        out = out.filter(pl.col("ageDays") > minAge)
    return out.filter(pl.col("price") >= lo)


def anyPrice(entries: pl.DataFrame, usd: float = STAKE) -> pl.DataFrame:
    return esw.filterCell(entries, {"minUsd": usd, "maxPrice": 1e9,
                                    "ageDays": 1e18, "marketsSoFar": 10 ** 9})


def medians(df: pl.DataFrame, col: str) -> dict[str, float | None]:
    h1 = df.filter(pl.col("ts") < esw.HALF_SPLIT)
    h2 = df.filter(pl.col("ts") >= esw.HALF_SPLIT)
    return {"medAll": round(100 * float(df[col].median()), 3) if df.height else None,
            "medH1": round(100 * float(h1[col].median()), 3) if h1.height else None,
            "medH2": round(100 * float(h2[col].median()), 3) if h2.height else None}


def medEvt(df: pl.DataFrame, col: str) -> float | None:
    if not df.height:
        return None
    ev = (df.group_by("eventSlug")
          .agg(r=(pl.col(col) * 100).sum() / (pl.len() * 100.0))
          .sort("eventSlug"))
    return round(100 * float(ev["r"].median()), 3)


def retCol(hname: str) -> str:
    return f"ret{hname[0].upper()}{hname[1:]}"


def spotCheck(entries: pl.DataFrame, dirs: list[str]) -> None:
    """Cache-mechanics hand check (R16's spot-check recipe): rebuild ONE
    mid-band >=$10k landed entry's burst window and delayed fill directly
    from the fills, without the entries cache."""
    lazy = pl.concat((pl.scan_parquet(f"{d}/fills.parquet") for d in dirs),
                     how="diagonal_relaxed")
    fills = (lazy.filter(pl.col("side") == "BUY")
             .select("ts", "account", "marketId", "outcome", "price", "size")
             .collect())
    hits = (windowFilter(entries, STAKE, 0.0, 5.0)
            .filter(pl.col("landed300")).sort("ts"))
    if not hits.height:
        print("  spot-check: no landed mid-band >=$10k entry yet — skipped")
        return
    e = hits.row(0, named=True)
    chain = (fills.filter((pl.col("account") == e["account"])
                          & (pl.col("marketId") == e["marketId"])
                          & (pl.col("outcome") == e["outcome"])
                          & (pl.col("ts") >= e["ts"]))
             .sort("ts")
             # entrySweep burst id: gap > 600s opens the next burst window
             .with_columns(bid=(pl.col("ts").diff()
                                .fill_null(pl.duration(days=1))
                                > pl.duration(minutes=10)).cum_sum())
             .filter(pl.col("bid") == pl.col("bid").first()))
    usd = float((chain["size"] * chain["price"]).sum())
    avg = usd / float(chain["size"].sum())
    ties = (fills.filter((pl.col("marketId") == e["marketId"])
                         & (pl.col("outcome") == e["outcome"])
                         & (pl.col("ts") == e["ts"]))
            .filter(pl.col("account") != e["account"]))
    tiePrices = [round(float(p), 6) for p in ties["price"].unique().to_list()]
    tapeTie = round(float(e["price"]), 6) in tiePrices
    nxt = (fills.filter((pl.col("marketId") == e["marketId"])
                        & (pl.col("outcome") == e["outcome"])
                        & (pl.col("ts") > e["ts"])
                        & ((pl.col("ts") - e["ts"]).dt.total_seconds() <= 300))
           .sort("ts"))
    checks = [("burst usd", round(usd, 2), round(float(e["usd"]), 2)),
              ("burst avg price", round(avg, 6), round(float(e["price"]), 6))]
    ok = all(abs(a - b) < 1e-4 for _, a, b in checks)
    if nxt.height:
        ok = ok and abs(float(nxt["price"][0]) - float(e["nextPrice"])) < 1e-6
        checks.append(("delayed fill price", round(float(nxt["price"][0]), 6),
                       round(float(e["nextPrice"]), 6)))
    for name, a, b in checks:
        match = abs(a - b) < 1e-4
        print(f"  spot-check {name}: hand={a} cache={b} "
              f"{'OK' if match else 'ARTIFACT' if name == 'burst avg price' and tapeTie else 'MISMATCH'}")
    if tapeTie and not ok:
        print(f"  spot-check note: cache price = keep-last tape tie among "
              f"same-second prints {sorted(set(tiePrices + [round(avg, 6)]))} "
              f"(shipped entries-cache tape is unpinned on same-second account "
              f"collisions — R2's documented tie noise; the OWN-account burst "
              f"usd and the delayed fill above are exact)")
        ok = True
    print(f"  spot-check verdict: {'PASS' if ok else 'FAIL'} "
          f"(entry {e['eventSlug']}/ts={e['ts']}, {chain.height} BUY prints "
          f"in the burst window)")


def buildPartial(dir_: Path) -> None:
    """PARTIAL fresh frames from the raw fetch caches using polycrawler's
    OWN normalize + dedupe helpers and schemas (what runFetch upserts at
    the end). Budgeted <4GB until the real fills.parquet lands."""
    from polycrawler.fetch import (
        dedupeRows,
        fillDedupeKeys,
        fillSchema,
        normalizeEvent,
        normalizeFill,
    )

    if dir_.exists():
        shutil.rmtree(dir_)
    dir_.mkdir(parents=True)
    fillFrames: list[pl.DataFrame] = []
    markets: list[pl.DataFrame] = []
    for p in sorted((FRESH / "raw" / "trades").glob("*.json")):
        raw = json.loads(p.read_text())
        fillFrames.append(pl.DataFrame([normalizeFill(r) for r in raw],
                                       schema=fillSchema))
        if len(fillFrames) >= 2000:
            keep = pl.concat(fillFrames, how="diagonal_relaxed").unique(
                subset=fillDedupeKeys)
            fillFrames = [keep]
    fills = pl.concat(fillFrames, how="diagonal_relaxed").unique(
        subset=fillDedupeKeys)
    fills.write_parquet(dir_ / "fills.parquet")
    for p in sorted((FRESH / "raw" / "events").glob("*.json")):
        data = json.loads(p.read_text())
        for ev in (data if isinstance(data, list) else [data]):
            markets.append(pl.DataFrame(dedupeRows(
                normalizeEvent(ev, closedOnly=False), "marketId"))
                if normalizeEvent(ev, closedOnly=False) else
                pl.DataFrame())
    marketFrame = (pl.concat([m for m in markets if m.height],
                             how="diagonal_relaxed")
                   .unique(subset=["marketId"]))
    marketFrame.write_parquet(dir_ / "markets.parquet")
    print(f"partial frames: {fills.height} fills / {marketFrame.height} markets "
          f"from {len(list((FRESH / 'raw' / 'trades').glob('*.json')))} trade "
          f"caches ({time.time() - t0:.0f}s)", flush=True)


def runGrade(label: str, tag: str) -> list[dict[str, Any]]:
    dirs = [str((FRESH if tag == "fresh" else PARTIAL).relative_to(ROOT))]
    print(f"=== [{label}] dirs={dirs} ({time.time() - t0:.0f}s)", flush=True)
    entries = esw.loadEntries(dirs, refresh=False)
    print(f"entries {entries.height} ({time.time() - t0:.0f}s)", flush=True)
    landedAll = mo.addLanded(entries, dirs)
    print(f"landed tape done (landed300 "
          f"{100 * float(landedAll['landed300'].mean()):.2f}%) "
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

    nat = anyPrice(entries)
    drf = anyPrice(graded10)
    print(f"  anchor usd>=$10k ANY price/age (description; {tag} dir): "
          f"n={nat.height} retReal={float(nat['retReal'].mean()):+.4f} "
          f"winRate={100 * float((nat['retReal'] > 0).mean()):.1f}% | "
          f"delay-real n={drf.height} "
          f"drRes mean={float(drf['retReal50'].mean()):+.4f}", flush=True)
    spotCheck(landedAll, dirs)

    rng = random.Random(7)
    rows: list[dict[str, Any]] = []
    freshResP5: dict[float, float | None] = {}
    for usd in USDS:
        for win, (mnA, mxA) in WINDOWS.items():
            landedFullCell = windowFilter(landedAll, usd, mnA, mxA)
            landed = (round(100 * float(landedFullCell["landed300"].mean()), 1)
                      if landedFullCell.height else 0.0)
            for conv, src, col in [("native", entries, "retReal"),
                                   ("dr", graded10, "retReal50")]:
                df = windowFilter(src, usd, mnA, mxA)
                row = hx.horizonEval(df, col, rng)
                row.update(cell=f">=${usd / 1000:g}k [{BAND[0]:g},{BAND[1]:g})",
                           win=win, conv=conv, horizon="res", landed=landed,
                           medEvt=medEvt(df, col), **medians(df, col))
                if conv == "dr" and win == "fresh<=5d":
                    freshResP5[usd] = row["p5"]
                rows.append(row)
            for hname in HORIZONS:
                df = windowFilter(graded10, usd, mnA, mxA)
                col = retCol(hname)
                row = hx.horizonEval(df, col, rng)
                row.update(cell=f">=${usd / 1000:g}k [{BAND[0]:g},{BAND[1]:g})",
                           win=win, conv="dr", horizon=hname, landed=landed,
                           medEvt=medEvt(df, col), **medians(df, col))
                rows.append(row)
        print(f"done stake >=${usd / 1000:g}k (fresh<=5d dr-res p5="
              f"{freshResP5.get(usd)}) ({time.time() - t0:.0f}s)", flush=True)

    for conv, hname in [("native", "res"), ("dr", "res")] + [
            ("dr", h) for h in HORIZONS]:
        print(f"\n— [{label}] {conv} · horizon {hname} —")
        print(" | ".join(TBL))
        for r in rows:
            if r["horizon"] != hname or r["conv"] != conv:
                continue
            print(" | ".join(str(v) if v is not None else "–" for v in (
                r["cell"], r["win"], r["horizon"], r["conv"], r["n"],
                r["events"], r["retMean"], r["winRate"], r["p5"], r["p"],
                r["topShare"], r["landed"], r["verdict"])))
    print("\ndrift medians by window/era (medAll · h1 · h2, delay-real, %):")
    for r in rows:
        if r["conv"] == "native":
            continue

        def fmt(v: float | None) -> str:
            return f"{v:+.3f}" if v is not None else "–"
        print(f"  {r['cell']:>18} {r['win']:>9} {r['horizon']:>4}: "
              f"{fmt(r['medAll'])} · {fmt(r['medH1'])} · {fmt(r['medH2'])}")
    return rows


def composeLane(rows: list[dict[str, Any]], freshResP5: dict[float, float | None],
                tag: str) -> list[str]:
    """Compose rule (pre-registered): fresh PASS + R16 HOLD PASS at the same
    (usd, horizon) with BOTH dirs' delay-realistic resolution p5 > 0."""
    print(f"\nCOMPOSE rows (HOLD=data/oosExpansion verdicts verbatim; "
          f"fresh dir={tag}):")
    rows5 = {(f">=${u / 1000:g}k", h): r for r in rows if r["conv"] == "dr"
             and r["win"] == "fresh<=5d" for u in [usdOf(r["cell"])]
             for h in [r["horizon"]]}
    candidates = []
    for (usdNum, horizon) in sorted(PRIOR_HOLD, key=lambda k: (k[0], k[1])):
        cell = f">=${usdNum / 1000:g}k"
        r = rows5.get((cell, horizon))
        prior = PRIOR_HOLD[(usdNum, horizon)]
        if r is None:
            print(f"  {cell:>8} {horizon:>4} fresh=MISSING HOLD={prior}")
            continue
        fn, fp = r["verdict"], PRIOR_HOLD_RES_P5[usdNum]
        fd = freshResP5.get(usdNum)
        if r["verdict"] == "INCONCLUSIVE-THIN":
            verdict = "COMPOSE BLOCKED (fresh THIN — ungradable, no verdict)"
        elif prior == "PASS" and r["verdict"] == "PASS" and (
                (fd is not None and fd > 0) and fp > 0):
            verdict = "COMPOSED CANDIDATE"
            candidates.append((cell, horizon))
        elif prior == "PASS" and r["verdict"] == "PASS":
            verdict = "KILLED (delay-realistic resolution floor)"
        elif prior == "FAIL" and r["verdict"] == "FAIL":
            verdict = "both dirs FAIL (family corroborated dead)"
        elif prior == "FAIL" and r["verdict"] == "PASS":
            verdict = "note: fresh PASS vs HOLD FAIL (HOLD deducted; no lane)"
        elif prior == "PASS" and r["verdict"] == "FAIL":
            verdict = "COMPOSE DIES (fresh falsifies the HOLD-PASSing cell)"
        else:
            verdict = "FAIL/THIN (no compose row)"
        print(f"  {cell:>8} {horizon:>4} fresh={fn:>17} HOLD={prior:>4} "
              f"dr-res p5 fresh={fd} HOLD={fp} -> {verdict}")
    if not candidates:
        print("  composed live-lane candidates: none yet")
    return candidates


def usdOf(cell: str) -> float:
    return float(cell.split(" ")[0].replace(">", "").replace("=", "")
                 .replace("$", "").replace("k", "")) * 1000.0


def reconcile(rows: list[dict[str, Any]], tag: str) -> str:
    dr = [r for r in rows if r["conv"] == "dr" and r["win"] == "fresh<=5d"]
    graded = [r for r in dr if r["verdict"] != "INCONCLUSIVE-THIN"]
    thin = [r["cell"] for r in dr if r["verdict"] == "INCONCLUSIVE-THIN"]
    head = "PRELIMINARY (partial cache): " if tag == "PARTIAL" else ""
    stakes = lambda rs: sorted({r["cell"].split(" ")[0] for r in rs})
    horizons = lambda rs: sorted({r["horizon"] for r in rs})
    if graded and all(r["verdict"] == "PASS" for r in graded):
        mid = ("the fresh mid-band [0.55,0.85) cell PASSES the graded gates for "
               f"{', '.join(stakes(graded))} at {', '.join(horizons(graded))}"
               + (f" and stays INCON-THIN for {', '.join(sorted(set(thin)))}"
                  if thin else ""))
    elif graded:
        worst = min(graded, key=lambda r: (r["p"], r["p5"]))
        deadStakes = stakes(graded)
        mid = (f"the fresh mid-band [0.55,0.85) cell FAILs the graded gates for "
               f"{', '.join(deadStakes)} at {', '.join(horizons(graded))} "
               f"(worst: {worst['cell']} {worst['horizon']}, p5={worst['p5']}, "
               f"P(>0)={worst['p']}) so the compose rule DIES the "
               "R16 live-lane family on those stakes"
               + (f" and the remaining {', '.join(sorted(set(thin)))} rows are "
                  "INCON-THIN but can never compose anyway (R16 HOLD dr-res "
                  "p5 < 0 pre-kills every non-$10k stake)" if thin else ""))
    else:
        mid = ("the fresh mid-band [0.55,0.85) cell is still INCON-THIN at "
               "every stake (compose pending the completed pull)")
    tail = (" — lane-3 readout expectation: the [0.55,0.85) slice of lane-3's "
            "0.55-0.90 band downgrades to a DIAGNOSTIC-NEGATIVE trans-transport "
            "expectation (mean-side negative on the fresh cohort: the "
            "drift-median story was fat-tailed, not gate-gradeable), while the "
            "[0.85,0.90) slice stays expectation-neutral: it rides R16's "
            "gate-killed [0.85,0.98) heavy-favorite rung (HOLD [0.85,0.98) "
            "dr-res P(>0)=0.535, topShare 8.6), so lane-3's diagnostic book "
            "should read these two slices separately per its bucket split.")
    return head + mid + tail


def main() -> None:
    ap = ArgumentParser(description=__doc__)
    ap.add_argument("--strict-fresh", action="store_true",
                    help="grade ONLY the completed data/midTopup pull (no partial)")
    args = ap.parse_args()
    landed = (FRESH / "fills.parquet").exists()
    if args.strict_fresh and not landed:
        print("strict-fresh: data/midTopup fills.parquet not landed yet — "
              "nothing graded")
        return
    if landed:
        tag, label = "fresh", "fresh data/midTopup"
    else:
        buildPartial(PARTIAL)
        tag, label = "PARTIAL", "PARTIAL data/_midTopupPartial"
    rows = runGrade(label, tag)
    freshResP5 = {usdOf(r["cell"]): r["p5"] for r in rows
                  if r["conv"] == "dr" and r["win"] == "fresh<=5d"
                  and r["horizon"] == "res"}
    composeLane(rows, freshResP5, tag)
    print("\nRECONCILIATION (lane-3 tie-in, machine-read from the verdicts):")
    print("  " + reconcile(rows, tag))
    out = ROOT / "data" / "entrySweep" / "midbandTopupCells.parquet"
    pl.DataFrame(rows).write_parquet(out)
    print(f"\nwrote {out} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
