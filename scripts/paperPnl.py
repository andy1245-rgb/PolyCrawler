"""Close out fired watcher signals into paper P&L.

Reads data/live/signals.csv, fetches each signal market's resolution from
Gamma, and values the paper copy:
  entry = bestAsk from the alert (falls back to avgPrice)
  payout = $1 per share if the copied outcome won, else 0
  size   = min($100, takeableShares x entry) capped by $100 budget
Appends results to data/live/paperPnl.csv and prints a summary. Safe to run
repeatedly: signals already in paperPnl.csv are skipped.

Run:  uv run python scripts/paperPnl.py
Cron: daily (see cron_create).
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
BUDGET = 100.0


def main() -> None:
    if not SIGNALS.exists():
        print("no signals yet")
        return
    done = set()
    if PNL.exists():
        with PNL.open() as fh:
            for row in csv.DictReader(fh):
                done.add(row["alertTs"])
    rows = []
    with SIGNALS.open() as fh:
        for row in csv.DictReader(fh):
            if row["alertTs"] in done:
                continue
            rows.append(row)
    if not rows:
        print(f"all {len(done)} signals already closed")
        return
    out = []
    with httpx.Client(timeout=30.0, headers={"User-Agent": "polycrawler2"}) as client:
        for row in rows:
            condId = row["marketId"]
            try:
                r = client.get(f"{gammaApi}/markets", params={"condition_ids": condId})
                m = (r.json() or [None])[0]
            except Exception as exc:
                print(f"gamma failed {condId[:12]}: {exc}")
                continue
            if not m:
                print(f"market not found {condId[:12]}")
                continue
            if not m.get("closed"):
                continue  # unresolved; try next run
            try:
                outs = json.loads(m.get("outcomes") or "[]")
                prices = json.loads(m.get("outcomePrices") or "[]")
            except (ValueError, TypeError):
                continue
            winner = outs[prices.index(max(prices, key=float))] if outs and prices else None
            entry = float(row["bestAsk"] or row["avgPrice"] or 0)
            if entry <= 0:
                continue
            takeable = float(row["takeableShares"] or 0)
            spend = min(BUDGET, takeable * entry) if takeable else BUDGET
            shares = spend / entry
            # We copied the insider's outcome, recorded in the alert.
            copied = (row.get("outcome") or "").strip()
            if not copied:
                continue  # legacy row without outcome; unvaluable
            won = copied == (winner or "")
            pnl = shares * 1.0 - spend if won else -spend
            out.append({
                "alertTs": row["alertTs"],
                "account": row["account"],
                "eventSlug": row["eventSlug"],
                "question": row["question"],
                "copiedOutcome": copied,
                "marketWinner": winner or "",
                "entry": round(entry, 4),
                "spend": round(spend, 2),
                "shares": round(shares, 2),
                "won": won,
                "pnl": round(pnl, 2),
                "resolvedAt": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            })
    if not out:
        print("no new resolved signals")
        return
    newFile = not PNL.exists()
    with PNL.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        if newFile:
            w.writeheader()
        w.writerows(out)
    tot = sum(r["pnl"] for r in out)
    wins = sum(1 for r in out if r["won"])
    print(f"closed {len(out)} signals: {wins} won, paper P&L ${tot:+,.2f}")


if __name__ == "__main__":
    main()
