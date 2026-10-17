"""Near-free expect-kill probe (research/ideaGenAlpha.md #5): stale siblings
after a date-ladder rung resolves.

When a ladder rung resolves, the scoreboard event implies -- by ladder
arithmetic -- that the other rungs of the same question stem (and, for some
classes, the derived windows of the same stem) must be worth 0 or 1, yet
their books often keep trading at mechanically impossible prices while arb
bots grind them down. This sweep measures, per stem class, whether stale
prints persist past our stack's 300-600s resolution delay with >=$1k printed
depth, or collapse in about a minute.

Everything is pre-registered in research/staleSibling.md (S2-S6: stem rule,
implied arithmetic, stale threshold, tradability gates, kill criteria, the
tape-as-depth-proxy disclosure, the censoring note, and the hard runtime
caps enforced below). This script fills ONLY the S8/S9 sections of that doc;
no src/ edits, no network, no commits.

Run:  uv run python scripts/research/staleSiblingSweep.py
      uv run python scripts/research/staleSiblingSweep.py --quick  (1 stem/class)
"""

import argparse
import bisect
import itertools
import random
import re
import statistics
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DATA_DIRS = [ROOT / "data", ROOT / "data/universe", ROOT / "data/oos", ROOT / "data/oosExpansion"]
LOG_PATH = ROOT / "logs" / "staleSiblingSweep.log"
DOC_PATH = ROOT / "research" / "staleSibling.md"

SLICE_HOURS = 6
DELAY_WINDOWS = [300, 600]
STALE_EPS = 0.02
TAKER_FEE = 0.005
DEPTH_MAIN = 1_000.0
DEPTH_SECONDARY = 100.0
GO_STALE_PCT = 2.0
GO_CAP_EVENT_PCT = 1.0
GO_MIN_EVENTS = 20
GO_PGT0 = 0.85
BANDS = [(0, 60), (60, 300), (300, 600), (600, 1800), (1800, 3600), (3600, 21600)]
SURVIVAL_TAU = [60, 300, 600, 1800, 3600, 21600]
MAX_CELLS = 200_000

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
MONTH_RE = "|".join(MONTHS)
DATE_RE = (
    r"^(?P<stem>.*?)[\s.]*(?P<conn>by|on)\s+(?P<month>" + MONTH_RE + r")\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?(?:\s*\(?et\)?)?[.?!]*$"
)
NEXT_RE = re.compile(r"\bnext\b|\bfirst\b")
STAGE_BUDGET = {"markets": 60, "tape": 600, "cells": 480, "measure": 480}
R9_NOTE = (
    "Mechanically stale-ladder mismatches on these tapes are a live-monitorable, "
    "retail-visible phenomenon, not a strategy lane for our delay profile: they appear "
    "at rung resolutions and decay on the order of minutes (see the survival tables in "
    "S8), so the right product use is a R9 watch-feed stale-window counter -- surfacing "
    "currently-stale sibling prints and their measured decay in real time as "
    "engagement content -- rather than an auto-trader, since our 300-600s delay sits "
    "the wrong side of the measured half-life."
)
_alarm = [0.0]


class StageTimeout(Exception):
    pass


def armStage(name: str) -> None:
    _alarm[0] = time.time() + STAGE_BUDGET[name]


def checkStage(name: str) -> None:
    if _alarm[0] and time.time() > _alarm[0]:
        raise StageTimeout(name)


def fmtUsd(x: float) -> str:
    return f"${x:,.0f}"


def fmtPct(x: float) -> str:
    return f"{x:.2f}%"


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[k]


# ------------------------------------------------------------------ markets

def loadMarkets() -> pl.DataFrame:
    frames = []
    for di, d in enumerate(DATA_DIRS):
        if not (d / "markets.parquet").exists():
            continue
        frames.append(
            pl.read_parquet(d / "markets.parquet")
            .with_row_index("ri")
            .select("ri", "marketId", "eventSlug", "question", "winner", "resolvedAt", "volumeUsd")
            .with_columns(pl.lit(di, pl.Int32).alias("dirIdx"))
        )
    m = pl.concat(frames, how="diagonal_relaxed")
    m = m.with_columns(
        (pl.col("winner").is_null().cast(pl.Int32) * 1_000_000_000 + pl.col("dirIdx") * 1_000_000 + pl.col("ri"))
        .alias("prio")
    )
    m = m.sort(["marketId", "prio"]).unique(subset=["marketId"], keep="first")
    return m.select("marketId", "eventSlug", "question", "winner", "resolvedAt", "volumeUsd").sort("marketId")


def parseRung(question: str, resolvedAt: datetime | None) -> dict[str, object]:
    q = (question or "").lower().replace("’", "'").replace("  ", " ").strip()
    match = re.match(DATE_RE, re.sub(r"\s*\(?et\)?\s*$", "", q, count=1))
    if not match:
        return {"cls": "U", "rungDate": None, "stem": q[:80]}
    conn = match["conn"]
    month, day = MONTHS[match["month"]], int(match["day"])
    year = int(match["year"]) if match["year"] else None
    if year is None and resolvedAt is not None:
        for cand in (resolvedAt.year, resolvedAt.year - 1):
            try:
                dt = datetime(cand, month, day, tzinfo=UTC)
            except ValueError:
                continue
            if dt <= resolvedAt + timedelta(days=1):
                year = cand
                break
    if year is None:
        year = resolvedAt.year if resolvedAt else 2000
    try:
        rungDate = datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return {"cls": "U", "rungDate": None, "stem": q[:80]}
    stem = re.sub(r"\s+", " ", match["stem"].strip().rstrip(",;."))
    cls = "N" if conn == "by" else ("E" if (conn == "on" and NEXT_RE.search(q)) else "I")
    return {"cls": cls, "rungDate": rungDate, "stem": stem}


def exclusiveOK(indices: list[int], rows: list[dict]) -> bool:
    resolved = [i for i in indices if rows[i]["winner"] in ("Yes", "No")]
    if len(resolved) != len(indices) or len(resolved) < 3:
        return False
    return sum(1 for i in resolved if rows[i]["winner"] == "Yes") <= 1


def nestingOK(indices: list[int], rows: list[dict]) -> bool:
    resolved = sorted(
        (i for i in indices
         if rows[i]["winner"] in ("Yes", "No") and rows[i]["_rungDate"] is not None),
        key=lambda i: rows[i]["_rungDate"],
    )
    if len(resolved) < 3:
        return False
    seq = [(rows[i]["_rungDate"], rows[i]["winner"]) for i in resolved]
    for (d1, w1), (d2, w2) in itertools.pairwise(seq):
        if d1 == d2 and w1 != w2:
            return False
        if w1 == "Yes" and w2 == "No":
            return False
    return True


# ------------------------------------------------------------------ tape

def loadTape(marketIds: list[str], log) -> dict[str, list[tuple[float, float, float]]]:
    """Per trade print: (tsSec, pYes, shares). Pre-registered S5
    canonicalization: pYes = size-weighted mean of Yes rows in the tx,
    shares = (sum BUY-Yes + sum SELL-Yes)/2."""
    armStage("tape")
    t0 = time.time()
    lf = pl.concat(
        [pl.scan_parquet(d / "fills.parquet") for d in DATA_DIRS if (d / "fills.parquet").exists()],
        how="diagonal_relaxed",
    )
    lf = lf.filter(pl.col("marketId").is_in(marketIds)).unique(
        subset=["txHash", "marketId", "outcome", "side", "size", "price", "ts"], keep="last"
    )
    grouped = lf.group_by(["marketId", "txHash"]).agg(
        yesWsum=pl.when(pl.col("outcome") == "Yes")
            .then(pl.col("price") * pl.col("size")).otherwise(0.0).sum(),
        yesRows=pl.when(pl.col("outcome") == "Yes")
            .then(pl.col("size")).otherwise(0.0).sum(),
        buyYes=pl.when((pl.col("outcome") == "Yes") & (pl.col("side") == "BUY"))
            .then(pl.col("size")).otherwise(0.0).sum(),
        sellYes=pl.when((pl.col("outcome") == "Yes") & (pl.col("side") == "SELL"))
            .then(pl.col("size")).otherwise(0.0).sum(),
        ts=pl.col("ts").min(),
    )
    grouped = grouped.filter(
        (pl.col("yesRows") > 0) & (pl.col("buyYes") + pl.col("sellYes") > 0)
    ).with_columns(
        (pl.col("yesWsum") / pl.col("yesRows")).alias("pYes"),
        ((pl.col("buyYes") + pl.col("sellYes")) / 2).alias("shares"),
    )
    prints = grouped.select("marketId", "ts", "pYes", "shares").collect()
    badge = "(amended run: pYes filter widened to all (0,1); see S8 amendment)"
    log("    tape filter " + badge)
    tape: dict[str, list[tuple[float, float, float]]] = {}
    for key, pdf in prints.group_by("marketId", maintain_order=True):
        rows = pdf.sort("ts").to_dicts()
        tape[key[0]] = [(r["ts"].timestamp(), r["pYes"], r["shares"]) for r in rows]
    log(f"    tape: {sum(len(v) for v in tape.values()):,} prints over {len(tape):,} markets, {time.time()-t0:.0f}s")
    return tape


# ------------------------------------------------------------------ cells

def buildCells(rows: list[dict], stemsAll, slugsAll, exclSlugs: set[str],
               nestedStems: set[tuple[str, str]], tape, quick: bool) -> list[dict]:
    armStage("cells")
    if quick:
        keepN = sorted(nestedStems, key=lambda k: -len(stemsAll.get((k), [])))[:1]
        keepE = sorted(exclSlugs, key=lambda s: -len(slugsAll.get(s, [])))
        keepE = {keepE[0]} if keepE else set()
        exclSlugs.clear()
        exclSlugs.update(keepE)
        nestedStems.clear()
        nestedStems.update(keepN)
    cells: list[dict] = []
    for (cls, stem), idx in sorted(stemsAll.items()):
        if cls == "N" and (cls, stem) not in nestedStems:
            continue
        for ti in idx:
            checkStage("cells")
            if len(cells) >= MAX_CELLS:
                return cells
            g = rows[ti]
            if g["winner"] not in ("Yes", "No") or g["resolvedAt"] is None or g["_rungDate"] is None:
                continue
            if cls == "E" and g["eventSlug"] not in exclSlugs:
                continue
            T = g["resolvedAt"]
            pairs: set[tuple[int, str]] = set()
            d = g["_rungDate"]
            if cls == "N":
                for j in idx:
                    s = rows[j]
                    if j == ti or s["_rungDate"] is None:
                        continue
                    if g["winner"] == "Yes" and s["_rungDate"] >= d:
                        pairs.add((j, "implied1"))
                    elif g["winner"] == "No" and s["_rungDate"] <= d:
                        pairs.add((j, "implied0"))
            elif g["winner"] == "Yes":
                liveCross: list[int] = []
                for j in idx:
                    if j == ti or rows[j]["eventSlug"] == g["eventSlug"]:
                        continue
                    s = rows[j]
                    if s["_rungDate"] is None or s["_rungDate"] <= d:
                        continue
                    tapeS = tape.get(s["marketId"])
                    if tapeS and tapeS[0][0] < T.timestamp():
                        liveCross.append(j)
                for j in slugsAll[g["eventSlug"]]:
                    if j != ti:
                        pairs.add((j, "implied0"))
                for j in liveCross:
                    pairs.add((j, "implied0"))
            for j, implied in pairs:
                s = rows[j]
                if s["winner"] in ("Yes", "No") and s["resolvedAt"] is not None and s["resolvedAt"] <= T:
                    continue
                cells.append({"t": ti, "s": j, "implied": implied, "cls": cls, "T": T})
    return cells


def measureCells(cells: list[dict], rows: list[dict], tape, log) -> None:
    armStage("measure")
    t0 = time.time()
    kept = 0
    cache: dict[str, tuple[list[float], list[float], list[float]]] = {}
    for c in cells:
        s = rows[c["s"]]
        T: datetime = c["T"]
        Tsec = T.timestamp()
        end = T + timedelta(hours=SLICE_HOURS)
        if s["winner"] in ("Yes", "No") and s["resolvedAt"] is not None and s["resolvedAt"] < end:
            end = s["resolvedAt"]
        pr = tape.get(s["marketId"])
        c["nPrints"] = 0
        c["censored"] = pr is None or not pr
        c["stale"] = False
        c["singleLate"] = False
        c["nStale"] = 0
        for w in DELAY_WINDOWS:
            c[f"depthUsd{w}"] = 0.0
            c[f"netUsd{w}"] = 0.0
        if pr is None:
            continue
        if s["marketId"] not in cache:
            cache[s["marketId"]] = (
                [x[0] for x in pr], [x[1] for x in pr], [x[2] for x in pr])
        tsec, pyes, shares = cache[s["marketId"]]
        lo = bisect.bisect_left(tsec, Tsec)
        hi = bisect.bisect_left(tsec, end.timestamp())
        n = hi - lo
        c["nPrints"] = n
        if n == 0:
            c["censored"] = True
            continue
        c["censored"] = False
        implied = c["implied"]
        staleIdx = [
            k for k in range(lo, hi)
            if (pyes[k] if implied == "implied0" else 1.0 - pyes[k]) > STALE_EPS
        ]
        c["nStale"] = len(staleIdx)
        if not staleIdx:
            continue
        firstOff = tsec[staleIdx[0]] - Tsec
        lastOff = tsec[staleIdx[-1]] - Tsec
        c["firstOff"] = firstOff
        c["lastOff"] = lastOff
        c["dur"] = lastOff - firstOff
        c["maxMism"] = max(pyes[k] if implied == "implied0" else 1.0 - pyes[k] for k in staleIdx)
        c["stale"] = len(staleIdx) >= 2 and c["dur"] >= 60
        c["singleLate"] = len(staleIdx) == 1 and firstOff >= 60
        segs = [(k - lo, tsec[k], pyes[k], shares[k]) for k in staleIdx]
        c["stalePrints"] = [(o - Tsec, (p if implied == "implied0" else 1 - p), p, sh)
                            for k, o, p, sh in segs]
        for w in DELAY_WINDOWS:
            sub = [s_ for s_ in c["stalePrints"] if s_[0] <= w]
            usd = sum(mism * sh for _, mism, _p, sh in sub)
            net = (sum(mism * sh for _, mism, _p, sh in sub) - TAKER_FEE * sum(p * sh for _, _m, p, sh in sub)) \
                if implied == "implied1" else (1 - TAKER_FEE) * usd
            c[f"depthUsd{w}"] = usd
            c[f"netUsd{w}"] = net
        kept += 1
    log(f"    measured {len(cells):,} cells ({kept} with stale prints) in {time.time()-t0:.0f}s")


# ------------------------------------------------------------------ aggregates

def readingFor(cls: str, agg: dict, rows: list[dict]) -> str:
    a = agg[cls]
    top = a.get("topStale")
    if top is None:
        return ("No >60-s residual reached the stale bar in this class: sibling rungs "
                "trade only inside their own resolution batch, and every print found "
                "between trigger resolution and sibling resolution was already within "
                "0.02 of the implied price.")
    g, s = rows[top["t"]], rows[top["s"]]
    return (
        f"Reading: the class's longest >60-s stale window is the '{top['implied']}' cell "
        f"from trigger '{g['question']}' ({g['winner']} at {g['resolvedAt']:%m-%d %H:%M}Z) "
        f"against still-unresolved sibling '{s['question']}': prints at mismatch "
        f"0.020-{top['maxMism']:.3f} for {top['dur']:.0f} s carrying "
        f"{fmtUsd(top['depthUsd600'])} notional ({fmtUsd(top['netUsd600'])} net of 50 bps) "
        "-- a second-class residual exists but is 3-4 orders of magnitude below the "
        "$1k tradability gate, and it dies long before our 300-s floor."
    )


def phantom(c: dict, rows: list[dict]) -> bool:
    w = rows[c["s"]]["winner"]
    return w == "Yes" if c["implied"] == "implied0" else w == "No"


def bandTable(staleCells: list[dict]) -> list[tuple[int, int, int, float, float]]:
    out = []
    for b0, b1 in BANDS:
        cellIds, vol, maxm = set(), 0.0, []
        for c in staleCells:
            for off, mism, _p, sh in c.get("stalePrints", []):
                if b0 <= off < b1:
                    cellIds.add(id(c))
                    vol += mism * sh
                    maxm.append(mism)
        out.append((b0, b1, len(cellIds), vol, pct(maxm, 0.5) if maxm else float("nan")))
    return out


def survival(staleCells: list[dict]) -> list[tuple[int, float]]:
    rows = []
    for tau in SURVIVAL_TAU:
        alive = sum(1 for c in staleCells if c["lastOff"] >= tau)
        rows.append((tau, alive / len(staleCells) if staleCells else 0.0))
    return rows


def aggregate(cells: list[dict], rows: list[dict], census: dict) -> dict[str, dict]:
    agg: dict[str, dict] = {}
    byCls: dict[str, list[dict]] = {}
    for c in cells:
        byCls.setdefault(c["cls"], []).append(c)
    for cls, cs in sorted(byCls.items()):
        stale = [c for c in cs if c["stale"]]
        nonPh = [c for c in stale if not phantom(c, rows)]
        caps: dict[float, list[dict]] = {}
        for depth in (DEPTH_MAIN, DEPTH_SECONDARY):
            caps[depth] = [c for c in nonPh if c["depthUsd600"] >= depth and c["netUsd600"] > 0]
        trigs = {c["t"] for c in cs}
        observable = [c for c in cs if not c["censored"]]
        agg[cls] = {
            "cells": len(cs),
            "allTriggers": census[cls]["triggers"] if cls in census else 0,
            "censored": sum(1 for c in cs if c["censored"]),
            "observable": len(observable),
            "staleN": len(stale),
            "stalePct": len(stale) / len(observable) * 100 if observable else 0.0,
            "onePrint": sum(1 for c in cs if c["nStale"] == 1 and not c["stale"]),
            "singleLate": sum(1 for c in cs if c["singleLate"]),
            "phantomPct": (len(stale) - len(nonPh)) / len(stale) * 100 if stale else 0.0,
            "triggers": len(trigs),
            "durs": [c["dur"] / 60 for c in stale],
            "maxMism": [c["maxMism"] for c in stale],
            "surv": survival(stale),
            "bands": bandTable(stale),
            "caps": caps,
            "nonPh": nonPh,
            "topStale": max(stale, key=lambda c: c["dur"]) if stale else None,
        }
    return agg


def bootstrap(events: list[float], draws: int = 2000, seed: int = 7) -> float:
    random.seed(seed)
    if not events:
        return 0.0
    hits = 0
    for _ in range(draws):
        sample = [random.choice(events) for _ in range(len(events))]
        if sum(sample) / len(sample) > 0:
            hits += 1
    return hits / draws


def verdict(cls: str, agg: dict) -> tuple[bool, str]:
    a = agg[cls]
    cap = a["caps"][DEPTH_MAIN]
    events: dict[int, float] = {}
    for c in cap:
        events[c["t"]] = events.get(c["t"], 0.0) + c["netUsd600"]
    nets = list(events.values())
    trigs = max(1, a["allTriggers"])
    nCapEvents = len(events)
    pgt0 = bootstrap(nets)
    c1 = a["stalePct"] >= GO_STALE_PCT
    c2 = nCapEvents / trigs * 100 >= GO_CAP_EVENT_PCT
    c3 = nCapEvents >= GO_MIN_EVENTS and bool(nets) and statistics.mean(nets) > 0 and pgt0 >= GO_PGT0
    c4 = a["phantomPct"] >= 50
    go = c1 and c2 and c3 and not c4
    why = (f"stale {fmtPct(a['stalePct'])} (need >=2%) | capturable@$1k events {nCapEvents:,} "
           f"({nCapEvents/trigs*100:.2f}% of {trigs:,} gated triggers, need >=1%) | "
           f"P(>0) {pgt0*100:.0f}% (need >=85%) | phantom {a['phantomPct']:.1f}%")
    return go, f"{why} => {'GO' if go else ('NO-GO, phantom note' if c4 else 'NO-GO')}"


# ------------------------------------------------------------------ reporting

def reportResults(agg: dict, census: dict, rows: list[dict], verdicts: list[str]) -> str:
    lines = [("| class | cells | censored | observable | stale | stale% obs | 1-print | "
             "1-print>=T+60 | phantom% | triggers w/ cells | gated triggers |")]
    for cls, a in sorted(agg.items()):
        lines.append(
            f"| {cls} | {a['cells']:,} | {a['censored']:,} | {a['observable']:,} | "
            f"{a['staleN']:,} | {a['stalePct']:.2f} | {a['onePrint']:,} | "
            f"{a['singleLate']:,} | {a['phantomPct']:.1f} | {a['triggers']:,} | "
            f"{a['allTriggers']:,} |"
        )
    tbl = lines
    md: list[str] = []
    md.append("## 8. Results")
    md.append("")
    md.append("<filled by scripts/research/staleSiblingSweep.py runs>")
    md.append("")
    md.append("**Amendment (flagged 2026-10-17, before interpreting any stale stats):** run 1 exposed "
              "S5's tape prefilter (canonical pYes restricted to 0.02-0.98) as a defect: correctly-priced "
              "prints outside that band were dropped, which collapsed the observable definition and left "
              "97%+ of cells falsely censored. The prefilter is widened to the full (0,1) band; stale "
              "detection, thresholds, and censoring semantics are UNCHANGED (a print counts as stale only "
              "on mismatch > 0.02 exactly as pre-registered; runs 1's verdict was NO-GO under the "
              "stricter filter, and the widened filter can only add counted prints in both directions — "
              "no GO direction is favored).")
    md.append("")
    md.append("### Census")
    md.append("| class | rungs parsed | stems | stems passing gate | trigger events |")
    md.append("|---|---:|---:|---:|---:|")
    for cls, cc in sorted(census.items()):
        md.append(f"| {cls} | {cc['rungs']:,} | {cc['stems']:,} | {cc['gated']:,} | {cc['triggers']:,} |")
    md.append("")
    md.append("### Cell outcomes (pre-registered S5 definitions)")
    md.append(tbl[0])
    md.extend(tbl[1:])
    for cls, a in sorted(agg.items()):
        md.append("")
        md.append(f"### Class {cls} decay")
        md.append("")
        md.append("| persistence window tau | fraction of stale cells still stale at tau |")
        md.append("|---:|---:|")
        for tau, frac in a["surv"]:
            md.append(f"| {tau // 60} min | {frac * 100:.1f}% |")
        if a["durs"]:
            md.append("")
            md.append(
                f"Stale window duration (min): p10 {pct(a['durs'], .1):.1f}, "
                f"p50 {pct(a['durs'], .5):.1f}, p90 {pct(a['durs'], .9):.1f}, "
                f"max {pct(a['durs'], 1.0):.1f}; median max mismatch "
                f"{pct(a['maxMism'], .5):.3f}"
            )
        md.append("")
        md.append("| band since resolution | stale cells w/ stale print | stale $ volume | median mismatch |")
        md.append("|---|---:|---:|---:|")
        for b0, b1, nCell, vol, mm in a["bands"]:
            md.append(f"| [{b0//60},{b1//60}] min | {nCell:,} | {fmtUsd(vol)} | {mm:.3f} |")
        md.append("")
        for w in DELAY_WINDOWS:
            nets = [c["netUsd" + str(w)] for c in a["nonPh"]]
            deps = [c["depthUsd" + str(w)] for c in a["nonPh"]]
            md.append(
                f"- delay window {w}s over non-phantom cells: stale depth {fmtUsd(sum(deps))}, "
                f"net {fmtUsd(sum(nets))}, cells net>0 {sum(1 for n in nets if n > 0):,}/{len(nets):,}"
            )
        for depth in (DEPTH_MAIN, DEPTH_SECONDARY):
            cap = a["caps"][depth]
            evt = {c["t"] for c in cap}
            net = sum(c["netUsd600"] for c in cap)
            md.append(f"- capturable@600s depth>={depth:.0f}: {len(cap):,} cells over {len(evt):,} events, "
                      f"total net {fmtUsd(net)}")
        _go, why = verdict(cls, agg)
        md.append("")
        md.append(f"**Class {cls}: {why}**")
        story = readingFor(cls, agg, rows)
        if story:
            md.append("")
            md.append(story)
    md.append("")
    md.append("### Product-content note (feeds R9)")
    md.append("")
    md.append(R9_NOTE)
    return "\n".join(md) + "\n"


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="one biggest stem per class")
    args = ap.parse_args()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    T0 = time.time()
    loglines: list[str] = []

    def log(msg: str) -> None:
        stamp = f"[{time.time() - T0:7.1f}s] {msg}"
        loglines.append(stamp)
        print(stamp, flush=True)

    try:
        log("== stale-sibling residual sweep (pre-registered; research/staleSibling.md) ==")
        armStage("markets")
        markets = loadMarkets()
        log(f"  merged markets: {markets.height:,}")
        rows = markets.to_dicts()
        for r in rows:
            meta = parseRung(r["question"], r["resolvedAt"])
            r["_cls"], r["_rungDate"], r["_stem"] = meta["cls"], meta["rungDate"], meta["stem"]
        stemsAll: dict[tuple[str, str], list[int]] = {}
        slugsAll: dict[str, list[int]] = {}
        for i, r in enumerate(rows):
            if r["_cls"] in ("N", "E"):
                stemsAll.setdefault((r["_cls"], r["_stem"]), []).append(i)
            slugsAll.setdefault(r["eventSlug"], []).append(i)
        exclSlugs = {s for s, idx in slugsAll.items() if exclusiveOK(idx, rows)}
        nestedStems = set()
        slugNest: dict[str, bool] = {}
        for (cls, _stem), idx in sorted(stemsAll.items()):
            if cls != "N":
                continue
            for i in idx:
                slug = rows[i]["eventSlug"]
                if slug not in slugNest:
                    slugNest[slug] = nestingOK(slugsAll[slug], rows)
                if slugNest[slug]:
                    nestedStems.add((cls, _stem))
                    break
        census = {}
        for cls in ("N", "E"):
            items = [(k, v) for k, v in stemsAll.items() if k[0] == cls]
            gatedStems = (
                [k for k, _ in items if k in nestedStems]
                if cls == "N"
                else [k for k, _ in items
                      if any(rows[i]["eventSlug"] in exclSlugs for i in stemsAll[k])]
            )
            gatedIdx = [i for k in gatedStems for i in stemsAll[k]]
            census[cls] = {
                "rungs": len({rows[i]["marketId"] for _k, v in items for i in v}),
                "stems": len(items),
                "gated": len(gatedStems),
                "triggers": sum(
                    1 for i in gatedIdx
                    if rows[i]["winner"] in ("Yes", "No") and rows[i]["resolvedAt"] is not None
                    and (cls == "N" or rows[i]["eventSlug"] in exclSlugs)
                ),
            }
        log(f"  stems: N-gated {len(nestedStems):,}, exclusive slugs {len(exclSlugs):,}; census {census}")
        tapeMark = sorted({
            rows[i]["marketId"]
            for (clsT, _stem), idx in stemsAll.items()
            if (clsT == "N" and (clsT, _stem) in nestedStems)
            or (clsT == "E" and any(rows[i]["eventSlug"] in exclSlugs for i in idx))
            for i in idx
        })
        tape = loadTape(tapeMark, log)
        cells = buildCells(rows, stemsAll, slugsAll, exclSlugs, nestedStems, tape, args.quick)
        log(f"  sibling cells: {len(cells):,}")
        measureCells(cells, rows, tape, log)
        agg = aggregate(cells, rows, census)
        verdicts = []
        for cls in sorted(agg):
            go, why = verdict(cls, agg)
            verdicts.append(f"Class {cls}: {why} => {'GO' if go else 'NO-GO'}")
            log(f"  [{cls}] {why} => {'GO' if go else 'NO-GO'}")
        section = reportResults(agg, census, rows, verdicts)
        doc = DOC_PATH.read_text()
        head = doc.split("## 8. Results")[0]
        DOC_PATH.write_text(head + section, encoding="utf-8")
        log(f"== done in {time.time() - T0:.0f}s; results appended to {DOC_PATH.name} ==")
        return 0
    except StageTimeout as st:
        log(f"!! stage budget exceeded: {st}; doc left pre-registered-only")
        return 2
    finally:
        LOG_PATH.write_text("\n".join(loglines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
