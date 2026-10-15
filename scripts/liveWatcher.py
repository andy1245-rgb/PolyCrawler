"""Live paper-trading watcher for the military fresh-big-bet rule.

Rule (research/militaryCategory.md): alert when an account that is <= 3 days
old with <= 3 distinct markets seen, places a >= $5k buy burst at avg price
<= 0.50 on a market belonging to a military/strike event.

Tape (2026-10-09 redesign, research/ideasResearch.md #1):
  1. RTDS push tape (scripts/rtdsTape.py): global activity/trades websocket,
     filtered client-side to the watched condition ids. Primary detection
     path — post-news bursts need low-latency pickup.
  2. /v2/trades gap-rescue poll (server-side CASH >= $5k filter, chunks of
     <= 20 condition ids): catches any >= $5k fill the socket missed while
     disconnected. Sub-$5k fills are only on the push tape; the CASH filter
     keeps the poll bounded — that is the point.
  3. Both paths dedup on (wallet, txHash, side, size, price, ts, market).
  4. every REFRESH_SECS: Gamma /events refresh of the open military universe
     (cached to disk so restarts do not refetch) + configured slugs.
  5. account state (first seen, distinct markets, bursts) is kept in a JSON
     state file, so the watcher can be restarted without losing ages.

Output: console lines + data/live/signals.csv (one row per alert).

Run:  uv run python scripts/liveWatcher.py [--once]
"""

import argparse
import csv
import json
import queue
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx

gammaApi = "https://gamma-api.polymarket.com"
dataApi = "https://data-api.polymarket.com"
REFRESH_SECS = 300
BACKFILL_SECS = 120
BURST_WINDOW_SEC = 600
RULE_MIN_USD = 5000
RULE_MAX_PRICE = 0.35
RULE_MAX_AGE_DAYS = 5
RULE_MAX_MARKETS = 3
# /v2/trades takes at most 20 distinct condition ids per call.
COND_CHUNK = 20
# Sizing: assume we can take up to this fraction above the best ask.
SIZE_SLIP = 0.10
clobApi = "https://clob.polymarket.com"
MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela", "nato",
            "syria", "yemen", "invade", "nuclear", "airspace", "blockade", "withdraw",
            "ceasefire", "strike", "war")

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "data" / "live"
STATE = LIVE / "state.json"
EVENTS_CACHE = LIVE / "events.json"
SIGNALS = LIVE / "signals.csv"


def nowIso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def loadState() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"accounts": {}, "lastTs": {}}


def saveState(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


def isMilitarySlug(slug: str) -> bool:
    return any(k in (slug or "").lower() for k in MILITARY)


def getWithRetry(client: httpx.Client, url: str, params: dict, attempts: int = 3) -> httpx.Response:
    """GET with a short exponential backoff for transient connection drops.

    httpx raises on network/protocol errors (e.g. "Server disconnected without
    sending a response") but not on 4xx/5xx status codes, so this only retries
    the former. The final failure is re-raised for the caller to log.
    """
    delay = 1.0
    for attempt in range(attempts):
        try:
            return client.get(url, params=params)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def refreshEvents(client: httpx.Client, knownSlugs: list[str]) -> dict[str, dict]:
    """marketId -> {eventSlug, question}. Open military events from Gamma + config slugs."""
    cache = json.loads(EVENTS_CACHE.read_text()) if EVENTS_CACHE.exists() else {"fetched": 0, "markets": {}}
    if time.time() - cache.get("fetched", 0) < REFRESH_SECS:
        return cache["markets"]
    markets: dict[str, dict] = dict(cache.get("markets", {}))
    slugs: set[str] = set()
    for tag in ("geopolitics", "politics", "world", "israel", "iran", "ukraine"):
        for page in (0, 100, 200):
            try:
                r = getWithRetry(client, f"{gammaApi}/events", {
                    "tag_slug": tag, "closed": "false", "order": "volume",
                    "ascending": "false", "limit": 100, "offset": page * 100})
                events = r.json() if isinstance(r.json(), list) else []
            except Exception as exc:
                print(f"[{nowIso()}] gamma refresh failed: {exc}", flush=True)
                events = []
            for ev in events:
                if isMilitarySlug(str(ev.get("slug") or "")):
                    slugs.add(str(ev["slug"]))
    slugs.update(knownSlugs)
    for slug in sorted(slugs):
        try:
            r = getWithRetry(client, f"{gammaApi}/events", {"slug": slug})
            events = r.json() if isinstance(r.json(), list) else []
        except Exception:
            continue
        for ev in events:
            for m in ev.get("markets") or []:
                mid = str(m.get("conditionId") or "")
                if mid and not m.get("closed"):
                    tokens = {}
                    try:
                        ids = json.loads(m.get("clobTokenIds") or "[]")
                        outs = json.loads(m.get("outcomes") or "[]")
                        for o, t in zip(outs, ids):
                            tokens[str(o)] = str(t)
                    except (ValueError, TypeError):
                        pass
                    markets[mid] = {"eventSlug": slug,
                                    "question": str(m.get("question") or "")[:80],
                                    "tokens": tokens,
                                    "fees": bool(m.get("feesEnabled"))}
    cache = {"fetched": time.time(), "markets": markets}
    EVENTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_CACHE.write_text(json.dumps(cache))
    print(f"[{nowIso()}] watching {len(markets)} open military markets ({len(slugs)} events)", flush=True)
    return markets


def knownSlugs() -> list[str]:
    slugs = []
    for cfg in ("configs/militaryUniverse.yaml", "configs/insiderCases.yaml"):
        try:
            for line in (ROOT / cfg).read_text().splitlines():
                t = line.strip()
                if t.startswith("- ") and "/" not in t and "0x" not in t:
                    slugs.append(t[2:].strip())
        except FileNotFoundError:
            pass
    return slugs


# Fill dedup shared by the push tape and the backfill poll (bounded memory).
SEEN = deque(maxlen=50000)
SEEN_SET: set[str] = set()


def seenBefore(key: str) -> bool:
    if key in SEEN_SET:
        return True
    SEEN.append(key)
    SEEN_SET.add(key)
    if len(SEEN_SET) > len(SEEN):  # deque evicted; drop its orphans
        SEEN_SET.intersection_update(SEEN)
    return False


def fillKey(row: dict, mid: str) -> str:
    return (f"{row['proxyWallet']}|{row.get('txnHash', '')}|{row['side']}|"
            f"{row['size']}|{row['price']}|{row['ts']}|{mid}")


def normalizeV2Trade(row: dict) -> dict | None:
    """/v2/trades row (snake_case) -> the push-tape row shape."""
    mid = str(row.get("condition_id") or "")
    wallet = str(row.get("proxy_wallet") or "").lower()
    ts = int(row.get("timestamp") or 0)
    if not mid or not wallet or ts <= 0:
        return None
    return {"mid": mid, "ts": ts,
            "proxyWallet": wallet,
            "side": str(row.get("side") or "").upper(),
            "size": float(row.get("size") or 0),
            "price": float(row.get("price") or 0),
            "outcome": str(row.get("outcome") or "?"),
            "txnHash": str(row.get("transaction_hash") or "")}


def backfillFills(client: httpx.Client, state: dict, markets: dict[str, dict]) -> None:
    """Gap-rescue poll via Data API /v2/trades with server-side CASH >= $5k
    filtering (ideasResearch.md #1): one request per 20-market chunk instead
    of parsing the whole tape. Only >= $5k fills exist here — enough to
    rescue the rule threshold after a disconnect; sub-$5k burst contributions
    are the push tape's job. New markets are served with backfill=True so
    account age stays untrusted until the one-time /activity check."""
    mids = sorted(markets)
    for i in range(0, len(mids), COND_CHUNK):
        chunk = mids[i:i + COND_CHUNK]
        lastAtStart = {m: state["lastTs"].get(m, 0) for m in chunk}
        rows: list[dict] = []
        cursor = None
        for _page in range(10):  # bound the walk; 10 x 500 rows is ample
            params = {"condition": ",".join(chunk), "limit": 500,
                      "taker_only": "false", "side": "BUY",
                      "filter_type": "CASH", "filter_amount": RULE_MIN_USD}
            if cursor:
                params["cursor"] = cursor
            try:
                r = getWithRetry(client, f"{dataApi}/v2/trades", params)
                body = r.json() if isinstance(r.json(), dict) else {}
            except Exception as exc:
                print(f"[{nowIso()}] v2/trades fetch failed ({len(chunk)} mids): {exc}", flush=True)
                body = {}
            pages = body.get("data") or []
            rows.extend(pages)
            pagination = body.get("pagination") or {}
            cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not cursor:
                break
        # watermark every market in the chunk, row or no row, so quiet
        # markets do not re-enter backfill mode every cycle. Oldest rows
        # first: account age must be computed from earlier fills before
        # later ones are evaluated.
        newest = max((int(r.get("timestamp") or 0) for r in rows), default=0)
        fetchTs = int(time.time())
        for m in chunk:
            state["lastTs"][m] = max(lastAtStart[m], newest, fetchTs if not rows else 0)
        for raw in sorted(rows, key=lambda r: int(r.get("timestamp") or 0)):
            row = normalizeV2Trade(raw)
            if not row or row["mid"] not in markets:
                continue
            if row["ts"] <= lastAtStart[row["mid"]]:
                continue
            firstPoll = row["mid"] not in lastAtStart
            if not firstPoll and seenBefore(fillKey(row, row["mid"])):
                continue
            evaluate(row, row["ts"], row["mid"], markets[row["mid"]], state,
                     backfill=firstPoll, client=client)
        time.sleep(0.1)


def verifyAccountAge(account: str, ts: int, acct: dict, client: httpx.Client) -> None:
    """One-time Data API /activity check for an account first seen in backfill.

    The fresh gate cannot trust an account's age when it first appears in a
    market's initial backfill. Query the 5-day window just before the big bet:
    if any activity row exists there, the account was already active and is
    treated as old (backfill stays set, so it can never fire); an empty window
    means its earliest activity is inside the cutoff, so it is genuinely fresh
    and the backfill flag is cleared. Failures leave the account ineligible.
    """
    acct["ageVerified"] = True
    try:
        r = getWithRetry(client, f"{dataApi}/activity", {
            "user": account, "limit": 500, "offset": 0,
            "start": ts - RULE_MAX_AGE_DAYS * 86400, "end": ts - 1})
        payload = r.json()
        if not isinstance(payload, list):
            print(f"[{nowIso()}] backfill age check bad payload {account}", flush=True)
            return
        rows = payload
    except Exception as exc:
        print(f"[{nowIso()}] backfill age check failed {account}: {exc}", flush=True)
        return
    if rows:
        print(f"[{nowIso()}] backfill account old {account}", flush=True)
        return
    acct["backfill"] = False
    print(f"[{nowIso()}] backfill account rescued (fresh) {account}", flush=True)


def evaluate(row: dict, ts: int, mid: str, info: dict, state: dict, backfill: bool,
             client: httpx.Client) -> None:
    account = str(row.get("proxyWallet") or row.get("wallet") or "").lower()
    if not account:
        return
    accounts = state["accounts"]
    acct = accounts.setdefault(account, {"firstTs": ts, "markets": {}, "bursts": {}})
    # An account first seen during a market's initial backfill may have
    # history older than the window: its age is not trustworthy, so it stays
    # gated by `backfill` until a one-time /activity check confirms its age.
    if backfill:
        acct["backfill"] = True
    markets = acct["markets"]
    outcome = str(row.get("outcome") or "?")
    outcomes = markets.setdefault(mid, [])
    if outcome not in outcomes:
        outcomes.append(outcome)
    size = float(row.get("size") or 0)
    price = float(row.get("price") or 0)
    usd = size * price
    burstKey = f"{mid}|{outcome}"
    bursts = acct["bursts"].setdefault(burstKey, {"start": ts, "usd": 0.0, "shares": 0.0})
    if ts - bursts["start"] > BURST_WINDOW_SEC:
        bursts = acct["bursts"][burstKey] = {"start": ts, "usd": 0.0, "shares": 0.0}
    bursts["usd"] += usd
    bursts["shares"] += size
    ageDays = (ts - acct["firstTs"]) / 86400
    nMarkets = len(markets)
    avg = bursts["usd"] / bursts["shares"] if bursts["shares"] else 1.0
    if (
        bursts["usd"] >= RULE_MIN_USD
        and avg <= RULE_MAX_PRICE
        and ageDays <= RULE_MAX_AGE_DAYS
        and nMarkets <= RULE_MAX_MARKETS
        and not info.get("fees", False)
    ):
        if acct.get("backfill") and not acct.get("ageVerified"):
            verifyAccountAge(account, ts, acct, client)
        if not acct.get("backfill"):
            alert(account, ts, mid, info, bursts, avg, ageDays, nMarkets, state, client, outcome)


def bookSize(client: httpx.Client, info: dict, outcome: str, burstPrice: float) -> dict:
    """Achievable size at the CLOB: total ask size priced within SIZE_SLIP of
    the insider's avg price, plus the best ask itself."""
    tokenId = (info.get("tokens") or {}).get(outcome)
    if not tokenId:
        return {}
    try:
        r = client.get(f"{clobApi}/book", params={"token_id": tokenId})
        book = r.json()
    except Exception:
        return {}
    asks = book.get("asks") or []
    best = None
    takeable = 0.0
    for level in asks:
        px = float(level.get("price") or 0)
        sz = float(level.get("size") or 0)
        if px <= 0 or sz <= 0:
            continue
        if best is None or px < best[0]:
            best = (px, sz)
        if px <= burstPrice * (1 + SIZE_SLIP):
            takeable += sz
    return {"bestAsk": best[0] if best else None, "askSize": best[1] if best else None,
            "takeableShares": round(takeable, 2)}


def alert(account: str, ts: int, mid: str, info: dict, burst: dict, avg: float,
          ageDays: float, nMarkets: int, state: dict, client: httpx.Client,
          outcome: str) -> None:
    key = f"{account}|{mid}|{int(burst['start'])}"
    seen = state.setdefault("alerts", [])
    if key in seen:
        return
    seen.append(key)
    state["alerts"] = seen[-2000:]
    book = bookSize(client, info, outcome, avg)
    when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")
    line = (f"*** SIGNAL {when} {account} {info.get('eventSlug')} | "
            f"{info.get('question')} | ${burst['usd']:,.0f} @ {avg:.3f} | "
            f"age {ageDays:.1f}d {nMarkets} mkts | "
            f"ask {book.get('bestAsk')} x{book.get('askSize')} takeable {book.get('takeableShares')}")
    print(line, flush=True)
    SIGNALS.parent.mkdir(parents=True, exist_ok=True)
    new = not SIGNALS.exists()
    with SIGNALS.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["alertTs", "account", "eventSlug", "question", "marketId",
                        "outcome", "burstUsd", "avgPrice", "ageDays", "marketsSeen",
                        "bestAsk", "askSize", "takeableShares"])
        w.writerow([nowIso(), account, info.get("eventSlug"), info.get("question"), mid,
                    outcome, round(burst["usd"], 2), round(avg, 4), round(ageDays, 2), nMarkets,
                    book.get("bestAsk"), book.get("askSize"), book.get("takeableShares")])


def main() -> None:
    from rtdsTape import RtdsTape
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="one refresh + backfill cycle, drain the tape, exit")
    args = ap.parse_args()
    state = loadState()
    slugs = knownSlugs()
    holder = {"markets": {}}          # read from the RTDS thread
    rowQ: queue.Queue = queue.Queue()
    tape = RtdsTape(lambda: set(holder["markets"].keys()),
                    lambda row, backfill: rowQ.put((row, backfill)))
    tape.start()
    with httpx.Client(timeout=httpx.Timeout(30.0), headers={"User-Agent": "polycrawler2"},
                      follow_redirects=True) as client:
        lastBackfill = 0.0
        lastSave = 0.0
        while True:
            markets = refreshEvents(client, slugs)
            holder["markets"] = markets
            if time.time() - lastBackfill >= BACKFILL_SECS:
                lastBackfill = time.time()
                backfillFills(client, state, markets)
            # drain the push tape
            while True:
                try:
                    row, backfill = rowQ.get(timeout=1.0)
                except queue.Empty:
                    break
                info = markets.get(row["mid"])
                if (not info or row["side"] != "BUY"
                        or seenBefore(fillKey(row, row["mid"]))):
                    continue
                evaluate(row, row["ts"], row["mid"], info, state,
                         backfill=backfill, client=client)
            if args.once:
                break
            if time.time() - lastSave >= 30.0:
                lastSave = time.time()
                saveState(state)
    tape.stop()


if __name__ == "__main__":
    main()
