"""Mark open paper positions to market.

Open positions = signals.csv rows not yet realized in paperPnl.csv whose
market is still live. Fetches the current Gamma price of the copied outcome
and values each position at the mark price, writing the full open book to
data/live/openPositions.csv each run. Prints realized + unrealized P&L and
the gate status so the daily report shows live performance before markets
resolve.

Run:  uv run python scripts/paperMarkToMarket.py
Cron: daily (see dailyCatchup.sh).
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

gammaApi = "https://gamma-api.polymarket.com"
ROOT = Path(__file__).resolve().parents[1]
SIGNALS = ROOT / "data" / "live" / "signals.csv"
PNL = ROOT / "data" / "live" / "paperPnl.csv"
OPEN = ROOT / "data" / "live" / "openPositions.csv"
BUDGET = 100.0

FIELDNAMES = [
    "alertTs", "account", "eventSlug", "question", "copiedOutcome",
    "burstUsd", "avgPrice", "ageDays", "marketsSeen", "askSize",
    "entry", "mark", "spread", "spend", "shares", "openPnl", "marketEnd",
    "valuedAt",
]


def copySpend(row: dict) -> tuple[float, float]:
    """Spend and share count for the $100-capped copy of one signal."""
    entry = float(row["bestAsk"] or row["avgPrice"] or 0)
    if entry <= 0:
        return 0.0, 0.0
    takeable = float(row["takeableShares"] or 0)
    spend = min(BUDGET, takeable * entry) if takeable else BUDGET
    return spend, spend / entry


def openPnl(row: dict, mark: float) -> tuple[float, float, float, float]:
    """(entry, spend, shares, pnl) for one open position at the mark price."""
    entry = float(row["bestAsk"] or row["avgPrice"] or 0)
    spend, shares = copySpend(row)
    return entry, spend, shares, shares * mark - spend


def realizedSummary() -> dict:
    out = {"closed": 0, "pnl": 0.0, "wins": 0}
    if not PNL.exists():
        return out
    with PNL.open() as fh:
        for row in csv.DictReader(fh):
            out["closed"] += 1
            out["pnl"] += float(row["pnl"])
            out["wins"] += 1 if row["won"] in ("True", "true", "1") else 0
    return out


def gateStatus(firstAlertTs: str | None, closedCount: int) -> str:
    if not firstAlertTs:
        return "gate: no signals yet"
    started = datetime.fromisoformat(firstAlertTs[:16])
    weeks = round((datetime.now(started.tzinfo) - started).days / 7, 2)
    firstDone = weeks >= 4.0
    return (
        f"gate: {closedCount}/30 closed signals, {weeks}/4 weeks "
        f"({'time clause met' if firstDone else 'time clause in progress'})"
    )


def main() -> None:
    if not SIGNALS.exists():
        print("no signals yet")
        return
    done = set()
    if PNL.exists():
        with PNL.open() as fh:
            for row in csv.DictReader(fh):
                done.add(row["alertTs"])
    openRows = []
    allRows = list(csv.DictReader(SIGNALS.open()))
    with httpx.Client(timeout=30.0, headers={"User-Agent": "polycrawler2"}) as client:
        for row in allRows:
            if row["alertTs"] in done:
                continue
            entry = float(row["bestAsk"] or row["avgPrice"] or 0)
            if entry <= 0:
                continue
            try:
                r = client.get(f"{gammaApi}/markets", params={"condition_ids": row["marketId"]})
                m = (r.json() or [None])[0]
            except Exception as exc:
                print(f"gamma failed {row['marketId'][:12]}: {exc}")
                continue
            if not m or m.get("closed"):
                continue  # resolved (or gone); paperPnl.py / next run owns it
            try:
                outs = json.loads(m.get("outcomes") or "[]")
                prices = json.loads(m.get("outcomePrices") or "[]")
            except (ValueError, TypeError):
                continue
            copied = (row.get("outcome") or "").strip()
            if copied not in outs:
                continue
            mark = float(prices[outs.index(copied)])
            _, spend, shares, pnl = openPnl(row, mark)
            openRows.append({
                "alertTs": row["alertTs"],
                "account": row["account"],
                "eventSlug": row["eventSlug"],
                "question": row["question"],
                "copiedOutcome": copied,
                "burstUsd": row.get("burstUsd") or "",
                "avgPrice": row.get("avgPrice") or "",
                "ageDays": row.get("ageDays") or "",
                "marketsSeen": row.get("marketsSeen") or "",
                "askSize": row.get("askSize") or "",
                "entry": round(entry, 4),
                "mark": mark,
                "spread": round(mark - entry, 4),
                "spend": round(spend, 2),
                "shares": round(shares, 2),
                "openPnl": round(pnl, 2),
                "marketEnd": str(m.get("endDate") or "")[:10],
                "valuedAt": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            })
    with OPEN.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(openRows)
    unrealized = sum(r["openPnl"] for r in openRows)
    committed = sum(r["spend"] for r in openRows)
    marked = sum(r["shares"] * r["mark"] for r in openRows)
    real = realizedSummary()
    firstTs = allRows[0]["alertTs"] if allRows else None
    print(
        f"open {len(openRows)}: cost ${committed:,.2f}, marks ${marked:,.2f} "
        f"(unrealized ${unrealized:+,.2f})"
    )
    print(
        f"realized {real['closed']} closed: {real['wins']} won, "
        f"realized P&L ${real['pnl']:+,.2f}"
    )
    print(gateStatus(firstTs, real["closed"]))


if __name__ == "__main__":
    main()
