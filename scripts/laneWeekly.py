"""One-command weekly review of ALL paper lanes (1/2/3) — plain-text report.

Read-only aggregation of what already exists:
  data/live/signals{,Lane2,Lane3}.csv   per-lane alert book (configs/paperLanes.yaml.src)
  data/live/laneCloses.csv              realized mark closes (paperLaneMarks.py)
  data/live/laneMarks.csv               daily open snapshots (paperLaneMarks.py)
  data/live/openPositions.csv           lane-1 open book (paperMarkToMarket.py)

Lane 3 is additionally split by burst-average price into the half-open band
buckets [0.55,0.85) and [0.85,0.90) (research/paperLanes.md bucket rule); the
narrow bucket is R16's surviving cell family (research/burstContinuation.md)
and is what lane-3's live data should be graded against instead of the wider
0.55–0.90 book.

The gate thresholds below are transcribed VERBATIM from
research/paperLanes.md §"Pre-registered gates (written before any lane data
exists)" — pinned to the doc, never moved to fit data.

Run:  uv run python scripts/laneWeekly.py
Cron: none — manual weekly review. Read-only, no state, no writes.
"""

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SIGNAL_FILES = {"lane1": "signals.csv", "lane2": "signalsLane2.csv",
                "lane3": "signalsLane3.csv"}

# Pre-registered gate thresholds (research/paperLanes.md, "Pre-registered gates"
# section — fixed before any lane data existed; do not move from data).
LANE2_MIN_CLOSES = 8          # ">=8 closes exist by the Nov 14 readout"
LANE2_PASS_MEAN = 20.0        # PASS iff mean >= +$20 AND winRate >= 25%
LANE2_PASS_WR = 0.25
LANE2_FAIL_MEAN = -27.0       # FAIL iff mean <= -$27 OR winRate <= 15%
LANE2_FAIL_WR = 0.15
LANE3_MIN_CLOSES = 20         # MIN_CELL = 20 (T+7d closes)
LANE3_KILL_MEAN = 0.0         # kill iff mean <= $0 AND winRate <= 55%
LANE3_KILL_WR = 0.55
LANE3_PROMO_WR = 0.65         # promotion iff mean > $0 AND winRate >= 65%
READOUT_DATE = date(2026, 11, 14)  # the Nov 14 readout named in the doc

# Lane-3 band buckets (research/paperLanes.md bucket rule; half-open intervals).
BAND_MID = (0.55, 0.85)       # R16's surviving cell family
BAND_HIGH = (0.85, 0.90)
BUCKET_MID = "mid [0.55,0.85)"
BUCKET_HIGH = "high [0.85,0.90)"
BUCKET_UNKNOWN = "unmatched signal"


def readCsvRows(path: Path) -> list[dict]:
    """Fail-soft CSV read: missing/corrupt/empty file -> []."""
    if not path.exists():
        return []
    try:
        with path.open(newline="") as fh:
            return [r for r in csv.DictReader(fh)
                    if any((r.get(k) or "").strip() for k in ("alertTs", "date"))]
    except (OSError, csv.Error, ValueError):
        return []


def bucket3(price: float) -> str:
    """Half-open lane-3 band buckets; the 0.85 edge lands in [0.85,0.90)."""
    if BAND_MID[0] <= price < BAND_MID[1]:
        return BUCKET_MID
    if BAND_HIGH[0] <= price < BAND_HIGH[1]:
        return BUCKET_HIGH
    return BUCKET_UNKNOWN


def stats(rows: list[dict]) -> tuple[int, float, float]:
    """(n, mean pnl per close, winRate) over close rows."""
    if not rows:
        return 0, 0.0, 0.0
    pnl = [float(r["pnl"]) for r in rows]
    return (len(pnl), sum(pnl) / len(pnl),
            sum(1 for p in pnl if p > 0) / len(pnl))


def gate2(n: int, mean: float, wr: float) -> str:
    """Pre-registered lane-2 gate (research/paperLanes.md): PASS iff mean >=
    +$20 AND winRate >= 25%; FAIL iff mean <= -$27 OR winRate <= 15%."""
    if n < LANE2_MIN_CLOSES:
        return f"INCONCLUSIVE-THIN (n={n} < {LANE2_MIN_CLOSES})"
    if mean <= LANE2_FAIL_MEAN or wr <= LANE2_FAIL_WR:
        return f"FAIL (mean ${mean:+.2f}/copy, winRate {wr:.0%})"
    if mean >= LANE2_PASS_MEAN and wr >= LANE2_PASS_WR:
        return f"PASS (mean ${mean:+.2f}/copy, winRate {wr:.0%})"
    return f"INCONCLUSIVE (mean ${mean:+.2f}/copy, winRate {wr:.0%}: between bands)"


def gate3(n: int, mean: float, wr: float) -> str:
    """Pre-registered lane-3 gate (research/paperLanes.md): kill iff mean <= $0
    AND winRate <= 55%; promotion signal iff mean > $0 AND winRate >= 65%."""
    if n < LANE3_MIN_CLOSES:
        return f"INCONCLUSIVE-THIN (n={n} < {LANE3_MIN_CLOSES})"
    if mean <= LANE3_KILL_MEAN and wr <= LANE3_KILL_WR:
        return f"KILL (mean ${mean:+.2f}/copy <= 0, winRate {wr:.0%} <= 55%)"
    if mean > LANE3_KILL_MEAN and wr >= LANE3_PROMO_WR:
        return f"PROMOTION SIGNAL (mean ${mean:+.2f}/copy, winRate {wr:.0%})"
    return f"INCONCLUSIVE (mean ${mean:+.2f}/copy, winRate {wr:.0%}: between bands)"


def lanes7Closes(closes: list[dict]) -> dict[str, list[dict]]:
    """Split laneCloses.csv rows by lane, keeping only decision-grade T+7d."""
    out: dict[str, list[dict]] = {}
    for r in closes:
        if r.get("horizon") == "7":
            out.setdefault(r["lane"], []).append(r)
    return out


def avgPriceIndex(path: Path) -> dict[tuple, str]:
    """(alertTs, account, eventSlug) -> avgPrice; first signal row wins."""
    idx: dict[tuple, str] = {}
    for r in readCsvRows(path):
        key = (r.get("alertTs"), r.get("account"), r.get("eventSlug"))
        idx.setdefault(key, r.get("avgPrice") or "")
    return idx


def bucketSplit(t7: list[dict], prices: dict[tuple, str]) -> dict[str, list[dict]]:
    """Bucket lane-3 T+7d closes by the alert's avgPrice."""
    split: dict[str, list[dict]] = {
        BUCKET_MID: [], BUCKET_HIGH: [], BUCKET_UNKNOWN: []}
    for r in t7:
        key = (r.get("alertTs"), r.get("account"), r.get("eventSlug"))
        p = prices.get(key)
        split[bucket3(float(p)) if p else BUCKET_UNKNOWN].append(r)
    return split


def bucketLines(split: dict[str, list[dict]]) -> list[str]:
    """Lane-3 band-bucket stats over T+7d closes (closable rows only)."""
    lines = []
    for name in (BUCKET_MID, BUCKET_HIGH, BUCKET_UNKNOWN):
        rows = split[name]
        n, mean, wr = stats(rows)
        extra = ""
        if name == BUCKET_MID:
            if n >= LANE3_MIN_CLOSES:
                extra = f" — {gate3(n, mean, wr)} (R16-cell reference read)"
            else:
                extra = (f" — needs {LANE3_MIN_CLOSES - n} more narrow-band "
                         f"T+7d closes to the >={LANE3_MIN_CLOSES} floor")
        lines.append(f"    {name}: n={n} mean={mean:+.2f}/copy winRate={wr:.0%}{extra}")
    return lines


def buildReport(root: Path) -> list[str]:
    lines = [f"== lane weekly readout — readout {READOUT_DATE.isoformat()} =="]
    live = root / "data" / "live"
    closes = readCsvRows(live / "laneCloses.csv")
    marks = readCsvRows(live / "laneMarks.csv")
    byLaneT7 = lanes7Closes(closes)
    prices = avgPriceIndex(live / "signalsLane3.csv")

    hasData = {"lane1": False, "lane2": False, "lane3": False}
    for lane in ("lane1", "lane2", "lane3"):
        rows = readCsvRows(live / SIGNAL_FILES[lane])
        if not rows:
            lines.append(f"{lane}: no data yet")
            continue
        hasData[lane] = True
        dates = [r["alertTs"][:10] for r in rows if r.get("alertTs")]
        laneCloses = [r for r in closes if r["lane"] == lane]
        realized = "0.00" if not laneCloses else f"{sum(float(r['pnl']) for r in laneCloses):+,.2f}"
        nCloses = len(laneCloses)
        if lane == "lane1":
            book = readCsvRows(live / "openPositions.csv")
            unreal = sum(float(r["openPnl"]) for r in book)
            snapN = len(book)
            snapWhen = f" @valued {max(r['valuedAt'][:10] for r in book)}" if book else ""
        else:
            snapRows = [r for r in marks if r["lane"] == lane]
            unreal, snapN, snapWhen = 0.0, 0, ""
            if snapRows:
                latest = max(r["date"] for r in snapRows)
                latestRows = [r for r in snapRows if r["date"] == latest]
                unreal = sum(float(r["openPnl"]) for r in latestRows)
                snapN = len(latestRows)
                snapWhen = f" @{latest}"
        name = {"lane1": "lane1 (resolution book)",
                "lane2": "lane2 (horizon-exit book)",
                "lane3": "lane3 (favorite/mid burst book)"}[lane]
        lines.append(name)
        lines.append(f"  rows={len(rows)} first={min(dates)} last={max(dates)}")
        lines.append(f"  closes={nCloses} realized=${realized}")
        lines.append(f"  unrealized=${unreal:+,.2f} ({snapN} open rows{snapWhen})")
        if lane == "lane2":
            n, mean, wr = stats(byLaneT7.get(lane, []))
            lines.append(f"  gate (T+7d, pre-registered): {gate2(n, mean, wr)}")
        if lane == "lane3":
            t7 = byLaneT7.get(lane, [])
            n, mean, wr = stats(t7)
            lines.append(f"  gate (T+7d, whole 0.55-0.90 book): {gate3(n, mean, wr)}")
            lines.append("  band buckets (T+7d closes, split by avgPrice):")
            lines.extend(bucketLines(bucketSplit(t7, prices)))

    lane2N = len(byLaneT7.get("lane2", []))
    lane3N = len(byLaneT7.get("lane3", []))
    lines.append("next decision date: 2026-11-14 readout (research/paperLanes.md)")
    if hasData["lane2"] and lane2N < LANE2_MIN_CLOSES:
        lines.append(f"  lane2: needs {LANE2_MIN_CLOSES - lane2N} more closes "
                     f"to the >={LANE2_MIN_CLOSES} gradeable floor")
    if hasData["lane3"] and lane3N < LANE3_MIN_CLOSES:
        lines.append(f"  lane3: needs {LANE3_MIN_CLOSES - lane3N} more T+7d "
                     f"closes to the >={LANE3_MIN_CLOSES} MIN_CELL floor")
    return lines


def main() -> None:
    for line in buildReport(ROOT):
        print(line)


if __name__ == "__main__":
    main()
