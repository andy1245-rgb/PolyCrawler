"""Execution-fill stamps for every paper lane (research/executionStamps.md).

The paper books grade $100 copies at the alert row's bestAsk, but nothing
records whether the market still offered a fillable book near that ask after
the burst. This script tail-checks each lane's signals file for due-and-
unstamped alerts and pulls the live CLOB book at T+300s and T+600s, appending
one stamp row per (lane, horizon, alertTs, account, eventSlug) to
data/live/execStamps.csv — the same append-once idempotency as the lane marks.

Read-only contract: the watcher owns data/live continuously; this script only
reads signals files and events caches (missing tokens resolve via a direct
gamma /markets lookup, not by rewriting any cache).

Run: uv run python scripts/bookExecStamps.py   # stamp due alerts, one summary
     line; missing inputs -> exit 0 (safe for dailyCatchup.sh fast-lane wiring).
"""

import csv
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "data" / "live"
STAMPS = LIVE / "execStamps.csv"
gammaApi = "https://gamma-api.polymarket.com"
clobApi = "https://clob.polymarket.com"

SIGNAL_FILES = {"lane1": "signals.csv", "lane2": "signalsLane2.csv",
                "lane3": "signalsLane3.csv"}
EVENTS_CACHE = {"lane1": "events.json", "lane2": "events.json",
                "lane3": "eventsLane3.json"}
HORIZONS = (300, 600)
FLOOR_MULT = 1.5          # takeable = asks priced <= 1.5x the alert ask
FILL_TARGET_USD = 100.0   # pre-registered fill100 predicate (takeableUsd150)
CAP_PER_RUN = 60          # bounded pass; remainder re-measured next tick
API_GRACE_S = 3600        # transport failures within 1h stay unstamped (retry next tick)

FIELDNAMES = [
    "lane", "horizon", "alertTs", "account", "eventSlug", "outcome",
    "tokenId", "t0Ask", "stampTs", "stampDrivenS", "askNow", "bidNow",
    "askSize", "spreadPct", "takeableUsd0", "takeableUsd150", "fill100",
    "missReason", "suspect",
]


def parseAlertTs(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def readSignals(root: Path, lane: str) -> list[dict]:
    path = root / "data" / "live" / SIGNAL_FILES[lane]
    if not path.exists():
        return []
    for attempt in range(2):
        try:
            with path.open(newline="") as fh:
                rows = [r for r in csv.DictReader(fh)
                        if r.get("alertTs") and r.get("marketId")]
                if rows:
                    return rows
        except (OSError, csv.Error):
            pass
        if attempt == 0:
            time.sleep(1.0)
    return []


def readStampKeys(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    with path.open(newline="") as fh:
        return {tuple(r[k] for k in ("lane", "horizon", "alertTs", "account",
                                     "eventSlug"))
                for r in csv.DictReader(fh)}


def laneCacheTokens(root: Path, lane: str) -> dict:
    """mid -> {outcome: tokenId} from the lane's watcher events cache (read-only)."""
    path = root / "data" / "live" / EVENTS_CACHE[lane]
    try:
        cache = json.loads(path.read_text())
        markets = cache.get("markets") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {mid: (info.get("tokens") or {}) for mid, info in markets.items()
            if info.get("tokens")}


def gammaTokens(client: httpx.Client, mid: str, forgot: dict) -> dict:
    """Direct gamma lookup for a token id missing from cache; forgot[] memoizes misses."""
    if mid in forgot:
        return {}
    try:
        r = client.get(f"{gammaApi}/markets", params={"condition_ids": mid})
        body = r.json() if isinstance(r.json(), list) else []
        m = body[0] if body and isinstance(body[0], dict) else {}
        ids = json.loads(m.get("clobTokenIds") or "[]")
        outs = json.loads(m.get("outcomes") or "[]")
        return {str(o): str(t) for o, t in zip(outs, ids)}
    except Exception:  # noqa: BLE001 — best-effort resolve, one bad row never blocks the sweep
        forgot[mid] = {}
        return {}


def getWithRetry(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    """Watcher retry pattern: 3 GETs, 1/2/4s backoff; re-raise on final failure."""
    delay = 1.0
    for attempt in range(3):
        try:
            return client.get(url, params=params)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(delay)
            delay *= 2


def lastTradePrice(client: httpx.Client, tokenId: str) -> float | None:
    try:
        r = client.get(f"{clobApi}/last-trade-price", params={"token_id": tokenId})
        if r.status_code != 200:
            return None
        return float(r.json().get("price") or 0)
    except Exception:  # noqa: BLE001 — probe failure leaves suspect unset (default False)
        return None


def fillableUsd(asks: list[dict], ceiling: float) -> float:
    total = 0.0
    for level in asks:
        px = float(level.get("price") or 0)
        sz = float(level.get("size") or 0)
        if px <= 0 or sz <= 0:
            continue
        if px <= ceiling:
            total += px * sz
    return total


def buildStampRow(row: dict, lane: str, horizon: int, tokenId: str,
                  book: dict, gammaClosed: bool | None, noPrints: bool,
                  stampTs: datetime) -> dict:
    t0Ask = float(row.get("bestAsk") or row.get("avgPrice") or 0)
    asks = book.get("asks") or []
    bids = book.get("bids") or []
    bestAsk = bestBid = None
    for level in asks:
        px = float(level.get("price") or 0)
        sz = float(level.get("size") or 0)
        if px > 0 and sz > 0 and (bestAsk is None or px < bestAsk[0]):
            bestAsk = (px, sz)
    for level in bids:
        px = float(level.get("price") or 0)
        sz = float(level.get("size") or 0)
        if px > 0 and sz > 0 and (bestBid is None or px > bestBid[0]):
            bestBid = (px, sz)
    t0 = t0Ask
    spread = ""
    if bestAsk and bestBid:
        spread = round((bestAsk[0] - bestBid[0]) / bestAsk[0] * 100, 2)
    if bestAsk is None:
        if bids:
            missReason = "book-empty"
        elif gammaClosed:
            missReason = "book-closed"
        else:
            missReason = "dead-market"
        takeable0 = takeable150 = 0.0
    elif t0 <= 0:
        missReason = "book-empty"
        takeable0 = takeable150 = 0.0
    elif bestAsk[0] > FLOOR_MULT * t0:
        missReason = "ask-gt-1.5x"
        takeable0 = takeable150 = 0.0
    else:
        missReason = "ok"
        takeable0 = round(fillableUsd(asks, t0), 2)
        takeable150 = round(fillableUsd(asks, FLOOR_MULT * t0), 2)
    entry = parseAlertTs(row["alertTs"])
    driven = max(0.0, (stampTs - (entry + timedelta(seconds=horizon))).total_seconds())
    return {
        "lane": lane,
        "horizon": str(horizon),
        "alertTs": row["alertTs"],
        "account": row["account"],
        "eventSlug": row["eventSlug"],
        "outcome": row.get("outcome") or "",
        "tokenId": tokenId,
        "t0Ask": round(t0, 4) if t0 else "",
        "stampTs": stampTs.strftime("%Y-%m-%d %H:%M:%S"),
        "stampDrivenS": round(driven),
        "askNow": bestAsk[0] if bestAsk else "",
        "bidNow": bestBid[0] if bestBid else "",
        "askSize": bestAsk[1] if bestAsk else "",
        "spreadPct": spread,
        "takeableUsd0": takeable0,
        "takeableUsd150": takeable150,
        "fill100": "True" if takeable150 >= FILL_TARGET_USD else "False",
        "missReason": missReason,
        "suspect": "no-prints-never" if noPrints else "",
    }


def appendStamps(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if new:
            w.writeheader()
        w.writerows(rows)


def gammaClosedStatus(client: httpx.Client, mid: str, closedCache: dict) -> bool | None:
    if mid in closedCache:
        return closedCache[mid]
    try:
        r = client.get(f"{gammaApi}/markets", params={"condition_ids": mid})
        body = r.json() if isinstance(r.json(), list) else []
        m = body[0] if body and isinstance(body[0], dict) else {}
        closed = bool(m.get("closed")) or not bool(m.get("active", True))
    except Exception:  # noqa: BLE001 — closed/unresolvable distinction is not load-bearing
        closed = None
    closedCache[mid] = closed
    return closed


def runDue(root: Path, client: httpx.Client, now: datetime | None = None) -> dict:
    """Stamp every due horizon; returns (stamped per lane, unstamped api-errors)."""
    now = now or datetime.now(tz=UTC)
    stampsPath = root / "data" / "live" / "execStamps.csv"
    keys = readStampKeys(stampsPath)
    gammaForgot: dict = {}
    closedCache: dict = {}
    perLane = {lane: 0 for lane in SIGNAL_FILES}
    apiLeft = 0
    pending: list[dict] = []
    for lane in SIGNAL_FILES:
        tokensForMid = laneCacheTokens(root, lane)
        for row in readSignals(root, lane):
            entry = parseAlertTs(row["alertTs"])
            if entry is None:
                continue
            mid = row["marketId"]
            for horizon in HORIZONS:
                key = (lane, str(horizon), row["alertTs"], row["account"],
                       row["eventSlug"])
                if key in keys:
                    continue
                dueAt = entry.timestamp() + horizon
                if now.timestamp() < dueAt:
                    continue
                if len(pending) >= CAP_PER_RUN:
                    appendStamps(stampsPath, pending)
                    return {"stamped": perLane, "apiLeft": apiLeft, "capped": True}
                tokenId = tokensForMid.get(mid, {}).get((row.get("outcome") or "").strip())
                if not tokenId:
                    tokensForMid[mid] = tokensForMid.get(mid) or gammaTokens(client, mid, gammaForgot)
                    tokenId = tokensForMid.get(mid, {}).get((row.get("outcome") or "").strip())
                if not tokenId:
                    continue  # cannot resolve this alert yet; revisit next tick
                try:
                    r = getWithRetry(client, f"{clobApi}/book",
                                     params={"token_id": tokenId})
                    book = r.json()
                except Exception:  # noqa: BLE001 — retry pattern mirrored from liveWatcher.getWithRetry
                    driven = now.timestamp() - dueAt
                    if driven > API_GRACE_S:
                        rowOut = buildStampRow(row, lane, horizon, tokenId, {},
                                               None, False, now)
                        rowOut["missReason"] = "api-error"
                        rowOut["fill100"] = "False"
                        pending.append(rowOut)
                        perLane[lane] += 1
                    else:
                        apiLeft += 1
                    continue
                gammaClosed = None
                noPrints = False
                asks = book.get("asks") or []
                bids = book.get("bids") or []
                if not asks:
                    gammaClosed = gammaClosedStatus(client, mid, closedCache)
                    if not bids:
                        noPrints = lastTradePrice(client, tokenId) in (None, 0)
                pending.append(buildStampRow(row, lane, horizon, tokenId, book,
                                             gammaClosed, noPrints, now))
                keys.add(key)
                perLane[lane] += 1
    appendStamps(stampsPath, pending)
    return {"stamped": perLane, "apiLeft": apiLeft, "capped": False}


def main() -> None:
    with httpx.Client(timeout=httpx.Timeout(30.0),
                      headers={"User-Agent": "polycrawler2"},
                      follow_redirects=True) as client:
        stats = runDue(ROOT, client)
    lanes = stats["stamped"]
    total = sum(lanes.values())
    if total or stats["apiLeft"]:
        parts = " ".join(f"{lane}={n}" for lane, n in lanes.items() if n)
        tail = f" apiLeft={stats['apiLeft']}" if stats["apiLeft"] else ""
        print(f"execStamps: stamped {total} ({parts}){tail}"
              f"{' capped; rest next tick' if stats['capped'] else ''}")
    else:
        print("execStamps: nothing due")


if __name__ == "__main__":
    main()
