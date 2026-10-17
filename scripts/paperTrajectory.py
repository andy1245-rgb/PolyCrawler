"""Build a weekly paper-book trajectory from the daily open-position marks.

paperMarkToMarket overwrites data/live/openPositions.csv each run, so the
unrealized-P&L history is lost. This script appends one row per open position
to data/live/trajectory.csv after each mark run, keyed by UTC date, so the
4-week paper gate can be graded on a trend (per-day totals) instead of a
single point. Appends are idempotent: a position is recorded at most once per
date. --report prints the per-date aggregation for manual weekly review.

Run:  uv run python scripts/paperTrajectory.py            # append today's marks
      uv run python scripts/paperTrajectory.py --report   # per-date trend print
Cron: deferred (see paperTrajectory wiring notes).
"""

import argparse
import csv
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPEN = ROOT / "data" / "live" / "openPositions.csv"
TRAJECTORY = ROOT / "data" / "live" / "trajectory.csv"

FIELDNAMES = [
    "date", "alertTs", "account", "eventSlug", "copiedOutcome", "burstUsd",
    "avgPrice", "entry", "mark", "openPnl", "spend", "shares", "valuedAt",
]


def readOpenRows(root: Path) -> list[dict]:
    """Read openPositions.csv, retrying once if the mark run is mid-write."""
    path = root / "data" / "live" / "openPositions.csv"
    if not path.exists():
        return []
    for attempt in range(2):
        try:
            with path.open(newline="") as fh:
                rows = [r for r in csv.DictReader(fh) if r.get("alertTs")]
            if rows:
                return rows
        except (OSError, csv.Error):
            pass
        if attempt == 0:
            time.sleep(1.0)
    return []


def appendTrajectory(root: Path) -> tuple[int, int]:
    """Append today's open positions to trajectory.csv; (appended, skipped)."""
    openRows = readOpenRows(root)
    if not openRows:
        return 0, 0
    today = datetime.now(tz=UTC).date().isoformat()
    trajPath = root / "data" / "live" / "trajectory.csv"
    seen = set()
    if trajPath.exists():
        with trajPath.open(newline="") as fh:
            for row in csv.DictReader(fh):
                seen.add((row["date"], row["alertTs"], row["account"], row["eventSlug"]))
    appended = skipped = 0
    with trajPath.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if not seen and not trajPath.stat().st_size:
            w.writeheader()
        for r in openRows:
            key = (today, r["alertTs"], (r.get("account") or "")[:10], r["eventSlug"])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            w.writerow({
                "date": today,
                "alertTs": r["alertTs"],
                "account": key[2],
                "eventSlug": r["eventSlug"],
                "copiedOutcome": r.get("copiedOutcome") or "",
                "burstUsd": r.get("burstUsd") or "",
                "avgPrice": r.get("avgPrice") or "",
                "entry": r.get("entry") or "",
                "mark": r.get("mark") or "",
                "openPnl": r.get("openPnl") or "",
                "spend": r.get("spend") or "",
                "shares": r.get("shares") or "",
                "valuedAt": r.get("valuedAt") or "",
            })
            appended += 1
    return appended, skipped


def report(root: Path) -> None:
    """Print one line per date in trajectory.csv: n positions and total pnl."""
    path = root / "data" / "live" / "trajectory.csv"
    if not path.exists():
        print("no trajectory yet")
        return
    perDate: dict[str, tuple[int, float]] = {}
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                pnl = float(row["openPnl"])
            except (KeyError, ValueError):
                pnl = 0.0
            n, tot = perDate.get(row["date"], (0, 0.0))
            perDate[row["date"]] = (n + 1, tot + pnl)
    for date in sorted(perDate):
        n, tot = perDate[date]
        print(f"{date} n={n} pnl={tot:+.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Append/aggregate the paper trajectory.")
    ap.add_argument("--report", action="store_true", help="print per-date trend only")
    args = ap.parse_args()
    if args.report:
        report(ROOT)
        return
    appended, skipped = appendTrajectory(ROOT)
    if appended or skipped:
        print(f"trajectory: {appended} appended, {skipped} already recorded")
    # missing/empty openPositions: exit 0 quietly


if __name__ == "__main__":
    main()
