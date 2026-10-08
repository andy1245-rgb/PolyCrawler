import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from polycrawler.config import Config, FetchConfig
from polycrawler.http import HttpSession, cachePath, writeJson

__all__ = ["cachePath", "writeJson"]

gammaApi = "https://gamma-api.polymarket.com"
dataApi = "https://data-api.polymarket.com"
# Data API /trades silently caps `limit` at 10000 and rejects offset > 10000
# ("max historical trades offset of 10000 exceeded"). Two pages therefore cover
# at most 20000 rows. `takerOnly` defaults to true (taker leg only);
# takerOnly=false is required to include maker fills. Results are newest-first.
# When a window is full, pass inclusive `end` = oldest timestamp to walk
# backward. If one second still fills 20000 rows, split with side=BUY/SELL.
tradePageLimit = 10000
tradeMaxOffset = 10000
eventPageSize = 100
requestSleepSec = 0.25
userAgent = "polycrawler2"

marketSchema = {
    "marketId": pl.String,
    "eventSlug": pl.String,
    "question": pl.String,
    "tags": pl.List(pl.String),
    "endDate": pl.Datetime(time_unit="us", time_zone="UTC"),
    "winner": pl.String,
    "resolvedAt": pl.Datetime(time_unit="us", time_zone="UTC"),
    "volumeUsd": pl.Float64,
    "clobTokenIds": pl.List(pl.String),
    "outcomes": pl.List(pl.String),
}
fillSchema = {
    "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
    "account": pl.String,
    "marketId": pl.String,
    "outcome": pl.String,
    "side": pl.String,
    "size": pl.Float64,
    "price": pl.Float64,
    "txHash": pl.String,
}
marketDedupeKeys = ["marketId"]
fillDedupeKeys = ["txHash", "account", "marketId", "outcome", "side", "size", "price", "ts"]


@dataclass
class FetchSummary:
    markets: int
    fills: int
    accounts: int


def runFetch(
    config: Config,
    eventSlugs: list[str] | None = None,
    refresh: bool = False,
) -> FetchSummary:
    slugs = list(eventSlugs) if eventSlugs else list(config.fetch.eventSlugs)
    dataDir = config.fetch.dataDir
    with httpx.Client(
        timeout=httpx.Timeout(60.0),
        headers={"User-Agent": userAgent},
        follow_redirects=True,
    ) as client:
        markets = fetchMarkets(config.fetch, slugs, dataDir, refresh, client)
        fills = fetchFills([row["marketId"] for row in markets], dataDir, refresh, client)
    dataPath = Path(dataDir)
    upsertTable(dataPath / "markets.parquet", markets, marketSchema, marketDedupeKeys, ["marketId"])
    upsertTable(dataPath / "fills.parquet", fills, fillSchema, fillDedupeKeys, ["ts", "txHash"])
    accounts = len({row["account"] for row in fills})
    return FetchSummary(markets=len(markets), fills=len(fills), accounts=accounts)


def fetchMarkets(
    fetch: FetchConfig,
    eventSlugs: list[str],
    dataDir: str,
    refresh: bool,
    client: httpx.Client,
) -> list[dict[str, Any]]:
    if eventSlugs:
        events = [fetchEventBySlug(client, slug, dataDir, refresh) for slug in eventSlugs]
        rows: list[dict[str, Any]] = []
        for event in events:
            rows.extend(normalizeEvent(event, closedOnly=False))
        return dedupeRows(rows, "marketId")

    rows = []
    for tag in fetch.marketTags:
        for event in fetchEventsByTag(client, fetch, tag, dataDir, refresh):
            for market in normalizeEvent(event, closedOnly=fetch.closedOnly):
                if marketPasses(fetch, market):
                    rows.append(market)
    return dedupeRows(rows, "marketId")


def fetchFills(
    marketIds: list[str],
    dataDir: str,
    refresh: bool,
    client: httpx.Client,
) -> list[dict[str, Any]]:
    fills: list[dict[str, Any]] = []
    for marketId in dict.fromkeys(marketIds):
        path = cachePath(dataDir, "trades", marketId)
        if path.exists() and not refresh:
            raw = json.loads(path.read_text())
        else:
            raw = collectTrades(client, marketId)
            writeJson(path, raw)
        fills.extend(normalizeFill(row) for row in raw)
    return dedupeFills(fills)


def normalizeEvent(event: dict[str, Any], closedOnly: bool) -> list[dict[str, Any]]:
    eventSlug = str(event.get("slug") or "")
    tags = tagSlugs(event.get("tags"))
    rows = []
    for market in event.get("markets") or []:
        if not market.get("conditionId"):
            continue
        if closedOnly and market.get("closed") is False:
            continue
        rows.append(normalizeMarket(market, eventSlug, tags))
    return rows


def normalizeMarket(market: dict[str, Any], eventSlug: str, tags: list[str]) -> dict[str, Any]:
    outcomes = parseJsonList(market.get("outcomes"))
    prices = parseJsonList(market.get("outcomePrices"))
    volume = market.get("volumeNum")
    if volume is None:
        volume = market.get("volume")
    winner = winnerFrom(outcomes, prices)
    # endDate is often the whole event's end, not when this market resolved.
    resolvedAt = parseTime(market.get("umaEndDate") or market.get("closedTime")) if winner else None
    return {
        "marketId": str(market["conditionId"]).lower(),
        "eventSlug": eventSlug,
        "question": str(market.get("question") or ""),
        "tags": list(tags),
        "endDate": parseTime(market.get("endDate")),
        "winner": winner,
        "resolvedAt": resolvedAt,
        "volumeUsd": float(volume or 0),
        "clobTokenIds": parseJsonList(market.get("clobTokenIds")),
        "outcomes": outcomes,
    }


def normalizeFill(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc),
        "account": str(row["proxyWallet"]).lower(),
        "marketId": str(row["conditionId"]).lower(),
        "outcome": str(row.get("outcome") or ""),
        "side": str(row["side"]).upper(),
        "size": float(row["size"]),
        "price": float(row["price"]),
        "txHash": str(row["transactionHash"]).lower(),
    }


def winnerFrom(outcomes: list[str], prices: list[str]) -> str | None:
    winners = []
    for name, price in zip(outcomes, prices):
        try:
            number = float(price)
        except (TypeError, ValueError):
            continue
        if number == 1.0:
            winners.append(name)
    if len(winners) == 1:
        return winners[0]
    return None


def parseJsonList(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [str(parsed)]
    return [str(value)]


def tagSlugs(tags: Any) -> list[str]:
    if not tags:
        return []
    slugs = []
    for tag in tags:
        if isinstance(tag, str):
            slugs.append(tag)
        elif isinstance(tag, dict):
            slug = tag.get("slug") or tag.get("label")
            if slug:
                slugs.append(str(slug))
    return slugs


def marketPasses(fetch: FetchConfig, market: dict[str, Any]) -> bool:
    if market["volumeUsd"] < fetch.minMarketVolumeUsd:
        return False
    endDate: datetime | None = market["endDate"]
    if endDate is not None and endDate.date() < fetch.fromDate:
        return False
    return True


def parseTime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def collectTrades(
    client: httpx.Client,
    marketId: str,
    end: int | None = None,
    side: str | None = None,
    depth: int = 0,
) -> list[dict[str, Any]]:
    if depth > 100:
        raise RuntimeError(f"trade pagination stopped after 100 windows for {marketId}")
    rows, saturated = fetchTradeWindow(client, marketId, end, side)
    if not rows or not saturated:
        return rows
    oldest = min(int(row["timestamp"]) for row in rows)
    if end is not None and oldest >= end:
        if side is None:
            buy = collectTrades(client, marketId, oldest, "BUY", depth + 1)
            sell = collectTrades(client, marketId, oldest, "SELL", depth + 1)
            return rows + buy + sell
        raise RuntimeError(
            f"more than {tradePageLimit + tradeMaxOffset} {side} trades "
            f"at timestamp {oldest} for {marketId}"
        )
    return rows + collectTrades(client, marketId, oldest, side, depth + 1)


def fetchTradeWindow(
    client: httpx.Client,
    marketId: str,
    end: int | None,
    side: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    for offset in (0, tradeMaxOffset):
        params: dict[str, Any] = {
            "market": marketId,
            "limit": tradePageLimit,
            "offset": offset,
            "takerOnly": "false",
        }
        if end is not None:
            params["end"] = end
        if side is not None:
            params["side"] = side
        page = getJson(client, f"{dataApi}/trades", params)
        if not isinstance(page, list):
            raise RuntimeError(f"unexpected trades payload for {marketId}")
        rows.extend(page)
        if len(page) < tradePageLimit:
            return rows, False
    return rows, True


def fetchEventBySlug(client: httpx.Client, slug: str, dataDir: str, refresh: bool) -> dict[str, Any]:
    path = cachePath(dataDir, "events", f"slug__{slug}")
    if path.exists() and not refresh:
        payload = json.loads(path.read_text())
    else:
        payload = getJson(client, f"{gammaApi}/events", {"slug": slug})
        writeJson(path, payload)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"event not found: {slug}")
    return payload[0]


def fetchEventsByTag(
    client: httpx.Client,
    fetch: FetchConfig,
    tag: str,
    dataDir: str,
    refresh: bool,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    offset = 0
    while True:
        key = f"tag__{tag}__{int(fetch.minMarketVolumeUsd)}__{fetch.fromDate.isoformat()}__{offset}"
        path = cachePath(dataDir, "events", key)
        if path.exists() and not refresh:
            page = json.loads(path.read_text())
        else:
            # /markets?tag_slug= ignores the tag. /events applies it.
            params: dict[str, Any] = {
                "tag_slug": tag,
                "order": "volume",
                "ascending": False,
                "volume_min": str(fetch.minMarketVolumeUsd),
                "end_date_min": fetch.fromDate.isoformat(),
                "limit": eventPageSize,
                "offset": offset,
            }
            if fetch.closedOnly:
                params["closed"] = "true"
            page = getJson(client, f"{gammaApi}/events", params)
            writeJson(path, page)
        if not isinstance(page, list) or not page:
            break
        events.extend(page)
        if len(page) < eventPageSize:
            break
        offset += eventPageSize
    return events


_sessions: dict[int, HttpSession] = {}


def sessionFor(client: httpx.Client) -> HttpSession:
    # requestSleepSec is the legacy per-call pause. 0 disables the limiter so tests stay instant.
    rate = 0.0 if requestSleepSec <= 0 else 1.0 / requestSleepSec
    found = _sessions.get(id(client))
    if found is None or found.client is not client or found.defaultRate != rate:
        found = HttpSession(client=client, defaultRate=rate)
        _sessions[id(client)] = found
    return found


def getJson(client: httpx.Client, url: str, params: dict[str, Any]) -> Any:
    return sessionFor(client).getJson(url, params)


def dedupeRows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    out = []
    for row in rows:
        if row[key] in seen:
            continue
        seen.add(row[key])
        out.append(row)
    return out


def dedupeFills(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out = []
    for row in rows:
        key = tuple(row[name] for name in fillDedupeKeys)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# keccak256("Transfer(address,address,uint256)")
transferTopic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
alchemyHost = "polygon-mainnet.g.alchemy.com"


def loadApiKey(name: str) -> str:
    found = os.environ.get(name, "").strip()
    if found:
        return found
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            if text.startswith("export "):
                text = text[len("export ") :]
            key, value = text.split("=", 1)
            if key.strip() == name:
                cleaned = value.strip().strip('"').strip("'")
                if cleaned:
                    return cleaned
    return ""


def alchemyUrl(key: str) -> str:
    return f"https://{alchemyHost}/v2/{key}"


def topicAddress(address: str) -> str:
    return "0x" + address.lower().removeprefix("0x").zfill(64)


def transferLogFilter(
    token: str,
    recipients: list[str],
    fromBlock: int,
    toBlock: int,
) -> dict[str, Any]:
    # topic2 is the indexed recipient. An array there is OR, so one call covers many wallets.
    return {
        "address": token.lower(),
        "fromBlock": hex(fromBlock),
        "toBlock": hex(toBlock),
        "topics": [transferTopic, None, [topicAddress(item) for item in recipients]],
    }


def decodeTransferLog(log: dict[str, Any], decimals: int = 6) -> dict[str, Any] | None:
    topics = log.get("topics") or []
    if len(topics) < 3 or not log.get("data"):
        return None
    return {
        "token": str(log.get("address") or "").lower(),
        "fromAddr": "0x" + str(topics[1])[-40:],
        "toAddr": "0x" + str(topics[2])[-40:],
        "amountUsd": int(str(log["data"]), 16) / (10**decimals),
        "txHash": str(log.get("transactionHash") or "").lower(),
        "block": int(str(log.get("blockNumber") or "0"), 16),
    }


def fetchErc20Transfers(
    session: HttpSession,
    rpcUrl: str,
    token: str,
    recipients: list[str],
    fromBlock: int,
    toBlock: int,
    addressBatch: int = 40,
    blockSpan: int = 2000,
    rpcBatch: int = 8,
) -> list[dict[str, Any]]:
    """Batched eth_getLogs: recipient sets OR'd in topic2, several ranges per HTTP call."""
    calls: list[dict[str, Any]] = []
    span = max(1, blockSpan)
    width = max(1, addressBatch)
    for start in range(fromBlock, toBlock + 1, span):
        end = min(toBlock, start + span - 1)
        for offset in range(0, len(recipients), width):
            chunk = recipients[offset : offset + width]
            if chunk:
                calls.append(transferLogFilter(token, chunk, start, end))
    found: list[dict[str, Any]] = []
    step = max(1, rpcBatch)
    for offset in range(0, len(calls), step):
        batch = calls[offset : offset + step]
        payload = [
            {"jsonrpc": "2.0", "id": index, "method": "eth_getLogs", "params": [call]}
            for index, call in enumerate(batch)
        ]
        response = session.postJson(rpcUrl, payload)
        rows = response if isinstance(response, list) else [response]
        byId = {item.get("id"): item for item in rows if isinstance(item, dict)}
        for index in range(len(batch)):
            item = byId.get(index, {})
            if item.get("error"):
                message = str(item["error"].get("message") if isinstance(item["error"], dict) else item["error"])
                raise RuntimeError(f"eth_getLogs failed: {message[:200]}")
            for log in item.get("result") or []:
                if isinstance(log, dict):
                    parsed = decodeTransferLog(log)
                    if parsed is not None:
                        found.append(parsed)
    return found


def alchemyBlockNumber(session: HttpSession, rpcUrl: str) -> int | None:
    payload = session.postJson(
        rpcUrl,
        {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
    )
    if not isinstance(payload, dict) or payload.get("error") or not payload.get("result"):
        return None
    return int(str(payload["result"]), 16)


def upsertTable(
    path: Path,
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType],
    keys: list[str],
    sortBy: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame(rows, schema=schema)
    if path.exists():
        existing = pl.read_parquet(path)
        frame = pl.concat([existing, frame], how="vertical")
    if frame.height:
        frame = frame.unique(subset=keys, keep="last").sort(sortBy)
    frame.write_parquet(path)
