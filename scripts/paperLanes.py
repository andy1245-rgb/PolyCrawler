"""Paper-lane engine for the parallel evidence books (research/paperLanes.md).

Lane 2 — horizon-exit book: lane-1's own alerts re-graded at the T+7d mark
(+50bps sell slippage) instead of resolution. Same trigger, same $100 copy,
zero incremental exposure; fired from liveWatcher.alert().

Lane 3 — favorite/mid burst book: per (account, marketId, outcome) bursts
>= $10k at burst-average price 0.55-0.90 on a bounded top-volume open-market
universe, marks at T+3d and T+7d. Capped at maxAlertsPerDay new signals per
UTC day (the <= $300/day paper budget).

REUSED SEMANTICS (documented per methodologyAttack.md A5 — the burst
definition below/duplicated functions mirror liveWatcher verbatim and differ
from the research gap-chained frame):
  - lane-3 burst accumulation mirrors liveWatcher.evaluate(): start-anchored
    600s window, running-prefix USD threshold, running-average price,
    marketsSeen = observed BUY legs on watched markets only;
  - the gap-rescue poll mirrors liveWatcher.backfillFills(): /v2/trades walk
    with a server-side CASH filter, per-market watermarks, oldest-first
    evaluation — only the watermark bank (lane-local), the filter amount and
    the thresholds differ;
  - the fill dedup store below is a lane-LOCAL copy of liveWatcher's bounded
    SEEN cache: a shared store would let lane-3 rows consume lane-1's dedup
    bookkeeping, which must stay byte-identical;
  - the /activity freshness probe mirrors liveWatcher.verifyAccountAge's
    one-time query (methodologyChecks.md A4). Lane 3 makes NO freshness gate;
    the flag is recorded per row and is diagnostic, never load-bearing.

Output: data/live/signalsLane2.csv, data/live/signalsLane3.csv (append +
per-lane alert dedup in state). All paths take root so tests run on tmp dirs.

Run: imported by scripts/liveWatcher.py; not standalone.
"""

import csv
import json
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

gammaApi = "https://gamma-api.polymarket.com"
dataApi = "https://data-api.polymarket.com"
REFRESH_SECS = 300
BURST_WINDOW_SEC = 600
# /activity freshness window for the lane-3 diagnostic stamp (A4 fix).
AGE_STAMP_DAYS = 5

ROOT = Path(__file__).resolve().parents[1]

_ALERT_FIELDS = ["alertTs", "account", "eventSlug", "question", "marketId",
                  "outcome", "burstUsd", "avgPrice", "ageDays", "marketsSeen",
                  "bestAsk", "askSize", "takeableShares"]
L2_FIELDNAMES = _ALERT_FIELDS + ["writtenTs"]
L3_FIELDNAMES = _ALERT_FIELDS + ["ageStamp", "freshWindow5d", "writtenTs"]

# helpers supplied by liveWatcher (fillKey / bookSize / normalizeV2Trade) so the
# lane engine reuses the watcher's functions instead of forking them.
HELPERS: dict = {}


def configure(helpers: dict) -> None:
    global HELPERS
    HELPERS = helpers


def loadConfig(path: Path | None = None) -> dict:
    """Lane config; absent/malformed file or keys => lanes disabled (safe)."""
    path = path or ROOT / "configs" / "paperLanes.yaml"
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    lane2 = raw.get("lane2") if isinstance(raw.get("lane2"), dict) else {}
    lane3 = raw.get("lane3") if isinstance(raw.get("lane3"), dict) else {}
    return {
        "lane2": {
            "enabled": bool(lane2.get("enabled", False)),
            "horizonsDays": _horizons(lane2.get("horizonsDays"), [7]),
            "sellSlippageBps": _num(lane2.get("sellSlippageBps"), 50.0),
        },
        "lane3": {
            "enabled": bool(lane3.get("enabled", False)),
            "horizonsDays": _horizons(lane3.get("horizonsDays"), [3, 7]),
            "sellSlippageBps": _num(lane3.get("sellSlippageBps"), 50.0),
            "minUsd": _num(lane3.get("minUsd"), 10000.0),
            "priceMin": _num(lane3.get("priceMin"), 0.55),
            "priceMax": _num(lane3.get("priceMax"), 0.90),
            "maxAlertsPerDay": max(1, int(_num(lane3.get("maxAlertsPerDay"), 3))),
            "skipFeeMarkets": bool(lane3.get("skipFeeMarkets", True)),
            "tags": [str(t) for t in lane3.get("tags", [])] or
                    ["politics", "geopolitics", "world", "sports", "crypto",
                     "economics", "tech", "culture", "pop-culture", "weather"],
            "maxMarkets": max(1, int(_num(lane3.get("maxMarkets"), 600))),
        },
    }


def _horizons(value, default: list[int]) -> list[int]:
    if not isinstance(value, list) or not value:
        return sorted(default)
    out = []
    for v in value:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            return sorted(default)
    return sorted({d for d in out if d > 0}) or sorted(default)


def _num(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def nowIso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")


def bank(state: dict) -> dict:
    """Lane-3 state branch; additive to state.json, lane-1 keys untouched."""
    return state.setdefault("lane3", {"accounts": {}, "lastTs": {}, "alerts": [],
                                      "daily": {}})


def readHeader(path: Path) -> list[str] | None:
    """The header already on disk, or None when there is not one yet.

    A blank first line is treated as no header, so a half-written file heals
    instead of being mistaken for a book on an older schema. ValueError covers
    UnicodeDecodeError: a book in another encoding must not kill the watcher.
    """
    if not path.exists():
        return None
    try:
        with path.open(newline="") as fh:
            header = next(csv.reader(fh), None)
    except (OSError, csv.Error, ValueError):
        return None
    return header or None


WARNED_SCHEMA: set[str] = set()


def warnSchemaOnce(path: Path, header: list[str], fieldnames: list[str]) -> None:
    missing = [name for name in fieldnames if name not in header]
    extra = [name for name in header if name not in fieldnames]
    why = (f"predates {','.join(missing)}" if missing
           else f"carries columns this writer does not know ({','.join(extra)})")
    key = f"{path}|{','.join(missing)}|{','.join(extra)}"
    if key in WARNED_SCHEMA:
        return
    WARNED_SCHEMA.add(key)
    print(f"[{nowIso()}] {path.name} {why}; rows stay in its "
          f"{len(header)}-column shape until the book is rebuilt", flush=True)


def appendCsv(path: Path, fieldnames: list[str], row: list) -> bool:
    """Append one row, fitted to the header already on disk.

    Returns True when the file is on the current schema. A book written before a
    column existed is written back in its own column order rather than gaining a
    wider row: a live book that is half one shape and half another misreads silently,
    which is worse than being a column behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    header = readHeader(path)
    byName = dict(zip(fieldnames, row))
    if header is None:
        with path.open("a", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(fieldnames)
            writer.writerow([byName.get(name, "") for name in fieldnames])
        return True
    if header == fieldnames:
        with path.open("a", newline="") as fh:
            csv.writer(fh).writerow([byName.get(name, "") for name in fieldnames])
        return True
    warnSchemaOnce(path, header, fieldnames)
    with path.open("a", newline="") as fh:
        csv.writer(fh).writerow([byName.get(name, "") for name in header])
    return False


def appendRow(root: Path, name: str, fieldnames: list[str], row: list) -> bool:
    return appendCsv(root / "data" / "live" / name, fieldnames, row)


# --- lane-2: horizon re-grade of lane-1's own alerts ---------------------------

def onAlert1(root: Path, cfg: dict, account: str, mid: str, info: dict,
             burst: dict, avg: float, ageDays: float, nMarkets: int,
             outcome: str, eventTs: str, writtenTs: str, book: dict) -> None:
    appendRow(root, "signalsLane2.csv", L2_FIELDNAMES, [
        eventTs, account, info.get("eventSlug"), info.get("question"), mid,
        outcome, round(burst["usd"], 2), round(avg, 4), round(ageDays, 2),
        nMarkets, book.get("bestAsk"), book.get("askSize"),
        book.get("takeableShares"), writtenTs])


# --- lane-3 fill dedup (lane-local store; see module docstring) ----------------

SEEN_L3 = deque(maxlen=50000)
SEEN_L3_SET: set[str] = set()


def seenBeforeL3(key: str) -> bool:
    if key in SEEN_L3_SET:
        return True
    SEEN_L3.append(key)
    SEEN_L3_SET.add(key)
    if len(SEEN_L3_SET) > len(SEEN_L3):  # deque evicted; drop its orphans
        SEEN_L3_SET.intersection_update(SEEN_L3)
    return False


# --- lane-3 market universe (bounded top-volume open markets) ------------------

def refreshLane3(client: httpx.Client, cfg: dict, root: Path | None = None) -> dict:
    """conditionId -> {eventSlug, question, tokens, fees} for the lane-3
    universe: open markets from Gamma events ordered by volume across the
    configured tag set, capped at maxMarkets (largest-volume events first).
    Cached to data/live/eventsLane3.json so restarts do not refetch."""
    root = root or ROOT
    cachePath = root / "data" / "live" / "eventsLane3.json"
    try:
        cache = json.loads(cachePath.read_text()) if cachePath.exists() else {}
    except (OSError, ValueError):
        cache = {}
    if time.time() - cache.get("fetched", 0) < REFRESH_SECS and cache.get("markets"):
        return cache["markets"]
    markets: dict[str, dict] = dict(cache.get("markets", {}))
    eventsUsed = 0
    over = False
    for tag in cfg["tags"]:
        if over:
            break
        for page in (0, 100, 200):
            try:
                r = client.get(f"{gammaApi}/events", params={
                    "tag_slug": tag, "closed": "false", "order": "volume",
                    "ascending": "false", "limit": 100, "offset": page})
                events = r.json() if isinstance(r.json(), list) else []
            except Exception as exc:
                print(f"[{nowIso()}] lane3 gamma refresh failed {tag}: {exc}", flush=True)
                continue
            for ev in events:
                slug = str(ev.get("slug") or "")
                if not slug:
                    continue
                marketsAdded = 0
                for m in ev.get("markets") or []:
                    mid = str(m.get("conditionId") or "")
                    if mid and not m.get("closed") and mid not in markets:
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
                        marketsAdded += 1
                if marketsAdded:
                    eventsUsed += 1
                if len(markets) >= cfg["maxMarkets"]:
                    over = True
                    break
            if over:
                break
    cache = {"fetched": time.time(), "markets": markets}
    cachePath.parent.mkdir(parents=True, exist_ok=True)
    cachePath.write_text(json.dumps(cache))
    print(f"[{nowIso()}] lane3 watching {len(markets)} open markets "
          f"({eventsUsed} volume events)", flush=True)
    return markets


# --- lane-3 evaluation (mirrors liveWatcher.evaluate verbatim, see docstring) --

def onTapeRow(row: dict, backfill: bool, markets3: dict, state: dict, client,
              root: Path | None = None) -> None:
    """Push-tape entry point called from liveWatcher's drain loop."""
    l3cfg = CFG["lane3"]
    if not l3cfg["enabled"]:
        return
    info = markets3.get(row["mid"])
    if not info or row["side"] != "BUY":
        return
    fillKey = HELPERS["fillKey"]
    if seenBeforeL3(fillKey(row, row["mid"])):
        return
    evalLane3(row, row["ts"], row["mid"], info, state, backfill, client, root)


def evalLane3(row: dict, ts: int, mid: str, info: dict, state: dict,
              backfill: bool, client, root: Path | None = None) -> None:
    l3cfg = CFG["lane3"]
    account = str(row.get("proxyWallet") or row.get("wallet") or "").lower()
    if not account:
        return
    l3 = bank(state)
    accounts = l3["accounts"]
    acct = accounts.setdefault(account, {"firstTs": ts, "markets": {}, "bursts": {}})
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
    avg = bursts["usd"] / bursts["shares"] if bursts["shares"] else 1.0
    if (
        bursts["usd"] >= l3cfg["minUsd"]
        and l3cfg["priceMin"] <= avg <= l3cfg["priceMax"]
        and not (l3cfg["skipFeeMarkets"] and info.get("fees", False))
    ):
        if "ageStamp" not in acct:
            clean = ageWindowClean(client, account, ts)
            acct["ageStamp"] = "verified" if clean is not None else "failed"
            acct["freshWindow5d"] = clean
        alert3(account, ts, mid, info, bursts, avg, outcome, state, client, root)


def ageWindowClean(client, account: str, ts: int, days: int = AGE_STAMP_DAYS) -> bool | None:
    """One-time /activity probe (A4): True = no activity rows in the `days`
    window before the burst; False = account was active before (not);
    None = query failed (stamp recorded as failed). Diagnostic only — never
    a gate."""
    try:
        r = client.get(f"{dataApi}/activity", params={
            "user": account, "limit": 500, "offset": 0,
            "start": ts - days * 86400, "end": ts - 1})
        payload = r.json()
    except Exception:
        print(f"[{nowIso()}] lane3 age stamp failed {account}", flush=True)
        return None
    if not isinstance(payload, list):
        print(f"[{nowIso()}] lane3 age stamp bad payload {account}", flush=True)
        return None
    return not payload


def alert3(account: str, ts: int, mid: str, info: dict, burst: dict, avg: float,
           outcome: str, state: dict, client, root: Path | None = None) -> None:
    l3 = state["lane3"]
    key = f"{account}|{mid}|{int(burst['start'])}"
    if key in l3["alerts"]:
        return
    today = datetime.now(tz=UTC).date().isoformat()
    if l3["daily"].get(today, 0) >= CFG["lane3"]["maxAlertsPerDay"]:
        return
    l3["daily"] = {d: n for d, n in l3["daily"].items() if d >= today}
    l3["daily"][today] = l3["daily"].get(today, 0) + 1
    l3["alerts"].append(key)
    l3["alerts"] = l3["alerts"][-2000:]
    book = HELPERS["bookSize"](client, info, outcome, avg)
    when = datetime.fromtimestamp(ts, tz=UTC).strftime("%m-%d %H:%M")
    acct = l3["accounts"][account]
    ageDays = (ts - acct["firstTs"]) / 86400
    line = (f"*** SIGNAL lane3 {when} {account} {info.get('eventSlug')} | "
            f"{info.get('question')} | ${burst['usd']:,.0f} @ {avg:.3f} | "
            f"age* {ageDays:.1f}d {len(acct['markets'])} mkts | "
            f"fresh5d {acct['freshWindow5d']} | "
            f"ask {book.get('bestAsk')} x{book.get('askSize')} takeable {book.get('takeableShares')}")
    print(line, flush=True)
    appendRow(root or ROOT, "signalsLane3.csv", L3_FIELDNAMES, [
        datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"), account,
        info.get("eventSlug"), info.get("question"), mid,
        outcome, round(burst["usd"], 2), round(avg, 4), round(ageDays, 2),
        len(acct["markets"]), book.get("bestAsk"), book.get("askSize"),
        book.get("takeableShares"), acct.get("ageStamp", "unverified"),
        acct.get("freshWindow5d") if acct.get("freshWindow5d") is not None else "?",
        nowIso()])


# --- lane-3 gap-rescue poll (mirrors liveWatcher.backfillFills, see docstring) --

def pollLane3(client, state: dict, markets3: dict, minUsd: float,
              root: Path | None = None) -> None:
    if not CFG["lane3"]["enabled"] or not markets3:
        return
    normalize = HELPERS["normalize"]
    fillKey = HELPERS["fillKey"]
    l3 = bank(state)
    mids = sorted(markets3)
    for i in range(0, len(mids), 20):  # /v2/trades takes <= 20 condition ids
        chunk = mids[i:i + 20]
        lastAtStart = {m: l3["lastTs"].get(m, 0) for m in chunk}
        rows: list[dict] = []
        cursor = None
        for _page in range(10):
            params = {"condition": ",".join(chunk), "limit": 500,
                      "taker_only": "false", "side": "BUY",
                      "filter_type": "CASH", "filter_amount": minUsd}
            if cursor:
                params["cursor"] = cursor
            try:
                r = client.get(f"{dataApi}/v2/trades", params=params)
                body = r.json() if isinstance(r.json(), dict) else {}
            except Exception as exc:
                print(f"[{nowIso()}] lane3 v2/trades fetch failed ({len(chunk)} mids): {exc}", flush=True)
                body = {}
            rows.extend(body.get("data") or [])
            pagination = body.get("pagination") or {}
            cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not cursor:
                break
        newest = max((int(r.get("timestamp") or 0) for r in rows), default=0)
        fetchTs = int(time.time())
        for m in chunk:
            l3["lastTs"][m] = max(lastAtStart[m], newest, fetchTs if not rows else 0)
        for raw in sorted(rows, key=lambda r: int(r.get("timestamp") or 0)):
            row = normalize(raw)
            if not row or row["mid"] not in markets3:
                continue
            if row["ts"] <= lastAtStart[row["mid"]]:
                continue
            firstPoll = row["mid"] not in lastAtStart
            if not firstPoll and seenBeforeL3(fillKey(row, row["mid"])):
                continue
            evalLane3(row, row["ts"], row["mid"], markets3[row["mid"]], state,
                      backfill=firstPoll, client=client, root=root)
        time.sleep(0.1)


# module-level carrier for the loaded config (set by liveWatcher.main); tests
# set it directly. None => every lane hook is a no-op.
CFG: dict | None = None


def setConfig(cfg: dict) -> None:
    global CFG
    CFG = cfg
