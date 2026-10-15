import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Any

import httpx
import polars as pl

from polycrawler.discovery.flagging import splitCutoff
from polycrawler.fetch import dataApi, getJson, writeJson
from polycrawler.http import cachePath

# Data API /activity silently caps limit at 500 and rejects offset > 5000
# ("max historical activity offset of 5000 exceeded"). Offsets 0,500,...,5000
# therefore cover at most 5500 rows. Request oldest-first. `end` and `start`
# are inclusive. When a window is full, pass start = newest timestamp to walk
# forward. Stop once distinct markets exceed activityMarketStop: the first
# trade is already on page one, and isFocused is false for every cap at or
# below that stop (the sensitivity grid tops out at 30).
activityPageLimit = 500
activityMaxOffset = 5000
activityMarketStop = 30
activityWorkers = 4

recreationalWords = (
    "sports",
    "esports",
    "e-sports",
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "wnba",
    "ncaa",
    "soccer",
    "football",
    "basketball",
    "baseball",
    "tennis",
    "golf",
    "ufc",
    "mma",
    "boxing",
    "cricket",
    "fifa",
    "olympics",
    "super-bowl",
    "superbowl",
    "super bowl",
    "lakers",
    "playoff",
    "world-cup",
    "world cup",
    "premier-league",
    "champions-league",
    "la-liga",
    "serie-a",
    "bundesliga",
    "formula-1",
    "formula 1",
    "grand-prix",
    "nascar",
    "gaming",
    "video-game",
    "videogame",
    "gta",
    "nintendo",
    "playstation",
    "xbox",
    "fortnite",
    "minecraft",
    "valorant",
    "dota",
    "league-of-legends",
    "counter-strike",
    "entertainment",
    "oscar",
    "grammy",
    "emmy",
    "box-office",
    "netflix",
    "eurovision",
    "mvp",
)
recreationalTags = frozenset(
    {"sports", "sport", "esports", "esport", "games", "gaming", "entertainment", "pop-culture", "music"}
)


def activityLimits() -> tuple[int, int]:
    # Tests patch these on the package, not on this module.
    import polycrawler.discovery as discovery

    return int(discovery.activityPageLimit), int(discovery.activityMaxOffset)


def activityStats(rows: list[dict[str, Any]], splitDate: date) -> tuple[datetime | None, int]:
    cutoff = splitCutoff(splitDate).timestamp()
    first: datetime | None = None
    markets: set[str] = set()
    for row in rows:
        if str(row.get("type") or "").upper() != "TRADE":
            continue
        ts = int(row["timestamp"])
        if ts >= cutoff:
            continue
        conditionId = str(row.get("conditionId") or "").lower()
        if conditionId:
            markets.add(conditionId)
        seen = datetime.fromtimestamp(ts, tz=timezone.utc)
        if first is None or seen < first:
            first = seen
    return first, len(markets)


def activityKey(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(name) or "")
        for name in ("transactionHash", "conditionId", "side", "timestamp", "size", "outcome", "type")
    )


def dedupeActivity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    out = []
    for row in rows:
        key = activityKey(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def tradedMarkets(rows: list[dict[str, Any]]) -> set[str]:
    markets: set[str] = set()
    for row in rows:
        if str(row.get("type") or "").upper() != "TRADE":
            continue
        conditionId = str(row.get("conditionId") or "").lower()
        if conditionId:
            markets.add(conditionId)
    return markets


def activityUsd(row: dict[str, Any]) -> float:
    raw = row.get("usdcSize")
    if raw not in (None, ""):
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    try:
        return float(row.get("size") or 0) * float(row.get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def isRecreational(row: dict[str, Any], tags: set[str]) -> bool:
    if tags & recreationalTags:
        return True
    text = " ".join(str(row.get(name) or "") for name in ("title", "slug", "eventSlug")).lower()
    return any(word in text for word in recreationalWords)


def recreationalShare(
    rows: list[dict[str, Any]],
    splitDate: date,
    tagsByMarket: dict[str, set[str]] | None = None,
) -> float | None:
    cutoff = splitCutoff(splitDate).timestamp()
    tagsByMarket = tagsByMarket or {}
    total = 0.0
    play = 0.0
    for row in rows:
        if str(row.get("type") or "").upper() != "TRADE":
            continue
        try:
            ts = int(row["timestamp"])
        except (TypeError, ValueError, KeyError):
            continue
        if ts >= cutoff:
            continue
        usd = activityUsd(row)
        if usd <= 0:
            continue
        total += usd
        market = str(row.get("conditionId") or "").lower()
        if isRecreational(row, tagsByMarket.get(market, set())):
            play += usd
    if total <= 0:
        return None
    return play / total


def fetchActivityPage(
    client: httpx.Client,
    wallet: str,
    end: int | None,
    start: int | None,
    offset: int,
    pageLimit: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "user": wallet,
        "limit": pageLimit,
        "offset": offset,
        "type": "TRADE",
        "sortBy": "TIMESTAMP",
        "sortDirection": "ASC",
    }
    if end is not None:
        params["end"] = end
    if start is not None:
        params["start"] = start
    page = getJson(client, f"{dataApi}/activity", params)
    if not isinstance(page, list):
        raise RuntimeError(f"unexpected activity payload for {wallet}")
    return page


def collectActivity(
    client: httpx.Client,
    wallet: str,
    end: int | None = None,
    marketStop: int = activityMarketStop,
) -> list[dict[str, Any]]:
    pageLimit, maxOffset = activityLimits()
    rows: list[dict[str, Any]] = []
    markets: set[str] = set()
    start: int | None = None
    for _depth in range(100):
        window: list[dict[str, Any]] = []
        saturated = True
        for offset in range(0, maxOffset + 1, pageLimit):
            page = fetchActivityPage(client, wallet, end, start, offset, pageLimit)
            window.extend(page)
            markets.update(tradedMarkets(page))
            if len(markets) > marketStop:
                return dedupeActivity(rows + window)
            if len(page) < pageLimit:
                saturated = False
                break
        rows.extend(window)
        if not saturated or not window:
            return dedupeActivity(rows)
        newest = max(int(row["timestamp"]) for row in window)
        if start is not None and newest <= start:
            raise RuntimeError(
                f"more than {pageLimit + maxOffset} trades at timestamp {newest} for {wallet}"
            )
        start = newest
    raise RuntimeError(f"activity pagination stopped after 100 windows for {wallet}")


def loadActivity(
    client: httpx.Client,
    wallet: str,
    dataDir: str,
    splitDate: date,
    refresh: bool,
    marketStop: int = activityMarketStop,
) -> list[dict[str, Any]]:
    path = cachePath(dataDir, "activity", wallet)
    if path.exists() and not refresh:
        payload = json.loads(path.read_text())
        if not isinstance(payload, list):
            raise RuntimeError(f"activity cache is not a list: {path}")
        return payload
    end = int(splitCutoff(splitDate).timestamp()) - 1
    rows = collectActivity(client, wallet, end, marketStop)
    writeJson(path, rows)
    return rows


def enrichActivity(
    accounts: list[str],
    dataDir: str,
    splitDate: date,
    refresh: bool,
    client: httpx.Client,
    marketStop: int = activityMarketStop,
    tagsByMarket: dict[str, set[str]] | None = None,
) -> pl.DataFrame:
    schema = {
        "account": pl.String,
        "firstTradeTs": pl.Datetime(time_unit="us", time_zone="UTC"),
        "marketsTraded": pl.Int64,
        "recreationalShare": pl.Float64,
    }
    if not accounts:
        return pl.DataFrame(schema=schema)
    total = len(accounts)
    done = 0
    lock = threading.Lock()

    def one(account: str) -> dict[str, Any]:
        nonlocal done
        rows = loadActivity(client, account, dataDir, splitDate, refresh, marketStop)
        firstTradeTs, marketsTraded = activityStats(rows, splitDate)
        with lock:
            done += 1
            if done % 100 == 0 or done == total:
                print(f"activity {done}/{total}", flush=True)
        return {
            "account": account,
            "firstTradeTs": firstTradeTs,
            "marketsTraded": marketsTraded,
            "recreationalShare": recreationalShare(rows, splitDate, tagsByMarket),
        }

    with ThreadPoolExecutor(max_workers=activityWorkers) as pool:
        stats = list(pool.map(one, accounts))
    return pl.DataFrame(stats, schema=schema)
