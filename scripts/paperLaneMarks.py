"""Mark-close the lane-2/3 paper books at their horizons (research/paperLanes.md).

Lane 2 closes every lane-1 alert at the T+7d mark (+50bps sell slippage);
lane 3 closes at T+3d and T+7d (T+7d decision-grade, T+3d early warning).
A close is a MARK close, never a resolution wait — unless the market resolved
before the close instant, in which case resolution value takes precedence
(1.0/0.0 per share, no slippage). Sizing reuses paperMarkToMarket.copySpend
verbatim ($100-capped copy at the alert's bestAsk / avgPrice fallback).

Outputs (append + idempotent):
  data/live/laneCloses.csv — one row per (lane, horizon, alertTs, account,
                             eventSlug); realized marked-exit P&L.
  data/live/laneMarks.csv  — daily open snapshots per (lane, date, alertTs,
                             account, eventSlug); the lane trajectory rows.
Prints per-lane realized P&L and the pre-registered gate verdicts.

Run:  uv run python scripts/paperLaneMarks.py            # close due + snapshots
      uv run python scripts/paperLaneMarks.py --report   # gate verdicts only
Cron: operator-wired into dailyCatchup.sh (see the end of the run report).
"""

import argparse
import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import paperLanes
import paperMarkToMarket as pmtm

gammaApi = "https://gamma-api.polymarket.com"
ROOT = paperLanes.ROOT
CLOSES = ROOT / "data" / "live" / "laneCloses.csv"
MARKS = ROOT / "data" / "live" / "laneMarks.csv"

CLOSE_FIELDNAMES = [
    "lane", "horizon", "alertTs", "account", "eventSlug", "copiedOutcome",
    "entry", "closeTs", "closeDate", "closeType", "closePrice", "markAtClose",
    "slippageBps", "spend", "shares", "won", "pnl",
]
SNAP_FIELDNAMES = [
    "date", "lane", "alertTs", "account", "eventSlug", "copiedOutcome",
    "avgPrice", "entry", "mark", "openPnl", "spend", "shares", "valuedAt",
]

# Pre-registered gate thresholds (research/paperLanes.md — fixed before data):
# lane 2 anchors: in-sample T+7d +$73.9/copy, win% 29.9; holdout T+7d -$27.4, win% 15.3.
L2_MIN_CLOSES = 8
L2_PASS_MEAN = 20.0
L2_PASS_WR = 0.25
L2_FAIL_MEAN = -27.0
L2_FAIL_WR = 0.15
# lane 3 (T+7d only): MIN_CELL 20; kill/promo bands per doc.
L3_MIN_CLOSES = 20
L3_KILL_MEAN = 0.0
L3_KILL_WR = 0.55
L3_PROMO_WR = 0.65

SIGNAL_FILES = {"lane2": "signalsLane2.csv", "lane3": "signalsLane3.csv"}


def parseAlertTs(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def entryTs(row: dict) -> datetime | None:
    """T+0 of the paper position: when the alert was detected and could have been
    copied. That is writtenTs when the book records it. alertTs is the event time,
    so anchoring a T+3d/T+7d horizon on it would close a burst replayed days late at
    the price of the day it was noticed. Falls back to alertTs on older books."""
    raw = (row.get("writtenTs") or row.get("alertTs") or "").strip()
    if not raw:
        return None
    try:
        return parseAlertTs(raw)
    except (ValueError, TypeError):
        return None


def summary(closes: list[dict]) -> tuple[int, float, float]:
    """(n, mean pnl per close, winRate) over lane closes with a horizon."""
    if not closes:
        return 0, 0.0, 0.0
    pnl = [float(r["pnl"]) for r in closes]
    return len(pnl), sum(pnl) / len(pnl), sum(1 for p in pnl if p > 0) / len(pnl)


def verdict2(n: int, mean: float, wr: float) -> str:
    """Pre-registered lane-2 gate (T+7d closes only)."""
    if n < L2_MIN_CLOSES:
        return f"INCONCLUSIVE-THIN (n={n} < {L2_MIN_CLOSES})"
    if mean <= L2_FAIL_MEAN or wr <= L2_FAIL_WR:
        return (f"FAIL (mean {mean:+.2f}/copy vs {-L2_FAIL_MEAN:.0f} holdout anchor, "
                f"winRate {wr:.0%} vs {L2_FAIL_WR:.0%})")
    if mean >= L2_PASS_MEAN and wr >= L2_PASS_WR:
        return f"PASS (mean {mean:+.2f}/copy, winRate {wr:.0%}) — live tape prices in-sample-like"
    return f"INCONCLUSIVE (mean {mean:+.2f}/copy, winRate {wr:.0%}: between bands)"


def verdict3(n: int, mean: float, wr: float) -> str:
    """Pre-registered lane-3 kill/promotion bands (T+7d closes only)."""
    if n < L3_MIN_CLOSES:
        return f"INCONCLUSIVE-THIN (n={n} < {L3_MIN_CLOSES})"
    if mean <= L3_KILL_MEAN and wr <= L3_KILL_WR:
        return (f"KILL (mean {mean:+.2f}/copy <= 0, winRate {wr:.0%} <= "
                f"{L3_KILL_WR:.0%}) — post-burst continuation dead on live events")
    if mean > L3_KILL_MEAN and wr >= L3_PROMO_WR:
        return f"PROMOTION SIGNAL (mean {mean:+.2f}/copy, winRate {wr:.0%})"
    return f"INCONCLUSIVE (mean {mean:+.2f}/copy, winRate {wr:.0%}: between bands)"


def fetchMarket(client: httpx.Client, mid: str) -> dict | None:
    try:
        r = client.get(f"{gammaApi}/markets", params={"condition_ids": mid})
        return (r.json() or [None])[0]
    except Exception as exc:
        print(f"gamma failed {mid[:12]}: {exc}")
        return None


def outcomeValues(m: dict) -> tuple[list[str], list[float]] | None:
    try:
        outs = json.loads(m.get("outcomes") or "[]")
        prices = json.loads(m.get("outcomePrices") or "[]")
    except (ValueError, TypeError):
        return None
    if not outs or len(prices) != len(outs):
        return None
    return outs, [float(p) for p in prices]


def closePosition(row: dict, lane: str, horizon: int, market: dict,
                  slippageBps: float, closeTs: datetime) -> dict | None:
    """Realize one marked exit. Returns the laneCloses.csv row shape."""
    entry = float(row["bestAsk"] or row["avgPrice"] or 0)
    if entry <= 0:
        return None
    spend, shares = pmtm.copySpend(row)
    copied = (row.get("outcome") or "").strip()
    if not copied:
        return None
    outs = prices = None
    if market:
        parsed = outcomeValues(market)
        if parsed:
            outs, prices = parsed
    if market and market.get("closed") and outs and copied in outs:
        winner = outs[prices.index(max(prices))]
        won = copied == winner
        exitValue = 1.0 if won else 0.0
        closeType = "resolution"
        markAtClose = exitValue
    elif outs and copied in outs:
        mark = prices[outs.index(copied)]
        won = ""  # a mark exit is not a resolution; winRate() uses pnl > 0
        exitValue = mark * (1 - slippageBps / 10000)
        closeType = "mark"
        markAtClose = mark
    else:
        return None
    return {
        "lane": lane,
        "horizon": horizon,
        "alertTs": row["alertTs"],
        "account": row["account"],
        "eventSlug": row["eventSlug"],
        "copiedOutcome": copied,
        "entry": round(entry, 4),
        "closeTs": closeTs.isoformat(timespec="seconds"),
        "closeDate": closeTs.date().isoformat(),
        "closeType": closeType,
        "closePrice": round(exitValue, 4),
        "markAtClose": round(markAtClose, 4),
        "slippageBps": slippageBps,
        "spend": round(spend, 2),
        "shares": round(shares, 2),
        "won": won,
        "pnl": round(shares * exitValue - spend, 2),
    }


def snapshotRow(row: dict, lane: str, market: dict, mark: float,
                closeTs: datetime) -> dict:
    entry = float(row["bestAsk"] or row["avgPrice"] or 0)
    spend, shares = pmtm.copySpend(row)
    return {
        "date": closeTs.date().isoformat(),
        "lane": lane,
        "alertTs": row["alertTs"],
        "account": row["account"],
        "eventSlug": row["eventSlug"],
        "copiedOutcome": (row.get("outcome") or "").strip(),
        "avgPrice": row.get("avgPrice") or "",
        "entry": round(entry, 4),
        "mark": mark,
        "openPnl": round(shares * mark - spend, 2),
        "spend": round(spend, 2),
        "shares": round(shares, 2),
        "valuedAt": closeTs.isoformat(timespec="seconds"),
    }


def readKeys(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    with path.open(newline="") as fh:
        return {tuple(r[k] for k in ("lane", "horizon", "alertTs", "account", "eventSlug"))
                for r in csv.DictReader(fh)}


def readSnapshotKeys(path: Path, today: str) -> set[tuple]:
    if not path.exists():
        return set()
    with path.open(newline="") as fh:
        return {tuple(r[k] for k in ("lane", "date", "alertTs", "account", "eventSlug"))
                for r in csv.DictReader(fh) if r.get("date") == today}


def appendRows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        if new:
            w.writeheader()
        w.writerows(rows)


def runLane(lane: str, cfgLane: dict, now: datetime, marketCache: dict,
            client: httpx.Client, closeKeys: set, snapKeys: set) -> tuple[list, list]:
    """Close every due horizon for the lane; snapshot the still-open book once today."""
    sigPath = ROOT / "data" / "live" / SIGNAL_FILES[lane]
    if not sigPath.exists():
        return [], []
    closes: list = []
    snaps: list = []
    slip = float(cfgLane["sellSlippageBps"])
    with sigPath.open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if r.get("alertTs") and (float(r["bestAsk"] or r["avgPrice"] or 0) > 0)]
    for row in rows:
        entry = entryTs(row)
        if entry is None:
            continue
        horizons = sorted({int(h) for h in cfgLane["horizonsDays"]})
        done = []
        for horizon in horizons:
            closeKey = (lane, str(horizon), row["alertTs"], row["account"],
                        row["eventSlug"])
            if closeKey in closeKeys:
                done.append(horizon)
                continue
            if now < entry + timedelta(days=horizon):
                continue
            mid = row["marketId"]
            if mid not in marketCache:
                marketCache[mid] = fetchMarket(client, mid)
            market = marketCache[mid]
            if market is None:
                continue
            out = closePosition(row, lane, horizon, market, slip, now)
            if out is None:
                continue
            closeKeys.add(closeKey)
            closes.append(out)
            done.append(horizon)
        if len(done) == len(horizons):
            continue  # every horizon closed = position no longer open
        snapKey = (lane, now.date().isoformat(), row["alertTs"], row["account"],
                   row["eventSlug"])
        if snapKey in snapKeys:
            continue
        mid = row["marketId"]
        if mid not in marketCache:
            marketCache[mid] = fetchMarket(client, mid)
        market = marketCache[mid]
        if market is None or market.get("closed"):
            continue
        parsed = outcomeValues(market)
        if not parsed:
            continue
        outs, prices = parsed
        copied = (row.get("outcome") or "").strip()
        if copied not in outs:
            continue
        mark = prices[outs.index(copied)]
        snaps.append(snapshotRow(row, lane, market, round(mark, 4), now))
        snapKeys.add(snapKey)
    return closes, snaps


def report() -> None:
    """Print the pre-registered gate verdicts from laneCloses.csv alone."""
    cfg = paperLanes.loadConfig()
    closes: dict[str, list[dict]] = {"lane2": [], "lane3": []}
    if CLOSES.exists():
        with CLOSES.open(newline="") as fh:
            for r in csv.DictReader(fh):
                if r["lane"] in closes:
                    closes[r["lane"]].append(r)
    for lane in ("lane2", "lane3"):
        laneCfg = cfg[lane]
        if not laneCfg["enabled"]:
            print(f"{lane}: disabled")
            continue
        horizon = max(laneCfg["horizonsDays"])
        rows = [r for r in closes[lane] if str(horizon) == str(r["horizon"])]
        n, mean, wr = summary(rows)
        verdict = verdict2(n, mean, wr) if lane == "lane2" else verdict3(n, mean, wr)
        realized = sum(float(r["pnl"]) for r in closes[lane])
        print(f"{lane} T+{horizon}d: n={n} mean={mean:+.2f}/copy winRate={wr:.0%} "
              f"realized(closes.csv)=${realized:+,.2f}")
        print(f"{lane} gate: {verdict}")


def run(client: httpx.Client) -> None:
    cfg = paperLanes.loadConfig()
    now = datetime.now(tz=UTC)
    closeKeys = readKeys(CLOSES)
    marketCache: dict[str, dict | None] = {}
    totalCloses = totalSnaps = 0
    for lane in ("lane2", "lane3"):
        if not cfg[lane]["enabled"]:
            continue
        snapKeys = readSnapshotKeys(MARKS, now.date().isoformat())
        closes, snaps = runLane(lane, cfg[lane], now, marketCache, client,
                                closeKeys, snapKeys)
        appendRows(CLOSES, CLOSE_FIELDNAMES, closes)
        appendRows(MARKS, SNAP_FIELDNAMES, snaps)
        totalCloses += len(closes)
        totalSnaps += len(snaps)
        pnl = sum(float(r["pnl"]) for r in closes)
        if closes or snaps:
            print(f"{lane}: {len(closes)} closed (pnl ${pnl:+,.2f}), "
                  f"{len(snaps)} open snapshots")
    if totalCloses or totalSnaps:
        print(f"lanes: {totalCloses} closes, {totalSnaps} snapshots")
    report()


def main() -> None:
    ap = argparse.ArgumentParser(description="mark-close lane-2/3 paper books")
    ap.add_argument("--report", action="store_true", help="print gate verdicts only")
    args = ap.parse_args()
    if args.report:
        report()
        return
    with httpx.Client(timeout=30.0, headers={"User-Agent": "polycrawler2"}) as client:
        run(client)


if __name__ == "__main__":
    main()
