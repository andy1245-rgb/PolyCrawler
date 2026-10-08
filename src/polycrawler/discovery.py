import hashlib
import json
import os
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from polycrawler.config import Config, DiscoveryConfig
from polycrawler.fetch import cachePath, dataApi, getJson, userAgent, writeJson

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
candidateSoftCap = 3000
candidatePriceCap = 0.7

suspiciousSchema = {
    "account": pl.String,
    "bestMarketId": pl.String,
    "bestOutcome": pl.String,
    "buyUsd": pl.Float64,
    "avgBuyPrice": pl.Float64,
    "firstBuyTs": pl.Datetime(time_unit="us", time_zone="UTC"),
    "firstTradeTs": pl.Datetime(time_unit="us", time_zone="UTC"),
    "accountAgeDays": pl.Float64,
    "marketsTraded": pl.Int64,
    "isNew": pl.Boolean,
    "isFocused": pl.Boolean,
    "isLongshot": pl.Boolean,
    "isBig": pl.Boolean,
    "signalCount": pl.Int64,
    "suspicious": pl.Boolean,
    "profitUsd": pl.Float64,
}

# Event slugs that count as "case markets in the data" for labeled recall.
caseEventSlugs = {
    "iran-feb28": {
        "us-strikes-iran-by",
        "us-next-strikes-iran-on-843",
        "usisrael-strikes-iran-by",
        "khamenei-out-as-supreme-leader-of-iran-by-february-28",
        "khamenei-out-as-supreme-leader-of-iran-by-march-31",
        "us-x-iran-ceasefire-by",
        "will-the-iranian-regime-fall-by-march-31",
        "israel-strike-on-iran-on",
    },
    "iran-cluster": {
        "us-strikes-iran-by",
        "us-next-strikes-iran-on-843",
        "usisrael-strikes-iran-by",
        "khamenei-out-as-supreme-leader-of-iran-by-february-28",
        "khamenei-out-as-supreme-leader-of-iran-by-march-31",
        "us-x-iran-ceasefire-by",
        "will-the-iranian-regime-fall-by-march-31",
        "israel-strike-on-iran-on",
    },
    "venezuela-maduro": {
        "maduro-out-in-2025",
        "us-forces-in-venezuela-by",
        "will-the-us-invade-venezuela-in-2025",
        "trump-invokes-war-powers-against-venezuela-by",
        "us-operation-to-capture-maduro-in-2025",
    },
}


@dataclass
class DiscoverResult:
    candidates: int
    suspicious: int
    prefilterNote: str | None
    frame: pl.DataFrame


@dataclass
class LabelRow:
    wallet: str
    case: str
    caseInData: bool
    candidate: bool
    suspicious: bool
    signals: str


def splitCutoff(splitDate: date) -> datetime:
    return datetime(splitDate.year, splitDate.month, splitDate.day, tzinfo=timezone.utc)


def resolvedMarkets(markets: pl.DataFrame, splitDate: date) -> pl.DataFrame:
    cutoff = splitCutoff(splitDate)
    resolvedAt = pl.coalesce("resolvedAt", "endDate")
    return markets.filter(
        pl.col("winner").is_not_null() & resolvedAt.is_not_null() & (resolvedAt < cutoff)
    )


def aggregateBets(
    fills: pl.DataFrame,
    markets: pl.DataFrame,
    splitDate: date,
) -> pl.DataFrame:
    cutoff = splitCutoff(splitDate)
    resolved = resolvedMarkets(markets, splitDate).select(["marketId", "winner"])
    buys = fills.filter((pl.col("side") == "BUY") & (pl.col("ts") < cutoff))
    buys = buys.join(resolved, on="marketId", how="inner")
    if buys.height == 0:
        return pl.DataFrame(
            schema={
                "account": pl.String,
                "marketId": pl.String,
                "outcome": pl.String,
                "buyUsd": pl.Float64,
                "buyShares": pl.Float64,
                "avgBuyPrice": pl.Float64,
                "firstBuyTs": pl.Datetime(time_unit="us", time_zone="UTC"),
                "winner": pl.String,
                "won": pl.Boolean,
            }
        )
    return (
        buys.group_by(["account", "marketId", "outcome"])
        .agg(
            (pl.col("size") * pl.col("price")).sum().alias("buyUsd"),
            pl.col("size").sum().alias("buyShares"),
            pl.col("ts").min().alias("firstBuyTs"),
            pl.col("winner").first().alias("winner"),
        )
        .with_columns(
            (pl.col("buyUsd") / pl.col("buyShares")).alias("avgBuyPrice"),
            (pl.col("outcome") == pl.col("winner")).alias("won"),
        )
    )


def selectBestBets(
    bets: pl.DataFrame,
    minBetUsd: float,
    maxAvgBuyPrice: float | None = None,
) -> pl.DataFrame:
    winning = bets.filter(
        pl.col("won")
        & pl.col("buyShares").is_not_null()
        & (pl.col("buyShares") > 0)
        & pl.col("avgBuyPrice").is_not_null()
    )
    qualified = winning.filter(pl.col("buyUsd") >= minBetUsd)
    if maxAvgBuyPrice is not None:
        qualified = qualified.filter(pl.col("avgBuyPrice") <= maxAvgBuyPrice)
    if qualified.height == 0:
        return winning.clear()
    accounts = qualified.select("account").unique()
    pool = winning.join(accounts, on="account", how="semi")
    return (
        pool.with_columns((pl.col("buyShares") - pl.col("buyUsd")).alias("betProfit"))
        .sort(
            ["betProfit", "firstBuyTs", "marketId", "outcome"],
            descending=[True, False, False, False],
        )
        .unique(subset=["account"], keep="first")
        .drop("betProfit")
    )


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
        for name in (
            "transactionHash",
            "conditionId",
            "side",
            "timestamp",
            "size",
            "outcome",
            "type",
        )
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


def fetchActivityPage(
    client: httpx.Client,
    wallet: str,
    end: int | None,
    start: int | None,
    offset: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "user": wallet,
        "limit": activityPageLimit,
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
    rows: list[dict[str, Any]] = []
    markets: set[str] = set()
    start: int | None = None
    for _depth in range(100):
        window: list[dict[str, Any]] = []
        saturated = True
        for offset in range(0, activityMaxOffset + 1, activityPageLimit):
            page = fetchActivityPage(client, wallet, end, start, offset)
            window.extend(page)
            markets.update(tradedMarkets(page))
            if len(markets) > marketStop:
                return dedupeActivity(rows + window)
            if len(page) < activityPageLimit:
                saturated = False
                break
        rows.extend(window)
        if not saturated or not window:
            return dedupeActivity(rows)
        newest = max(int(row["timestamp"]) for row in window)
        if start is not None and newest <= start:
            raise RuntimeError(
                f"more than {activityPageLimit + activityMaxOffset} trades "
                f"at timestamp {newest} for {wallet}"
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


def withSignals(frame: pl.DataFrame, discovery: DiscoveryConfig) -> pl.DataFrame:
    age = (pl.col("firstBuyTs") - pl.col("firstTradeTs")).dt.total_seconds() / 86400.0
    scored = frame.with_columns(
        accountAgeDays=age,
        isNew=(age <= discovery.maxAccountAgeDays).fill_null(False),
        isFocused=pl.col("marketsTraded") <= discovery.maxMarketsTraded,
        isLongshot=pl.col("avgBuyPrice") <= discovery.maxBuyPrice,
        isBig=pl.col("buyUsd") >= discovery.minBetUsd,
    )
    scored = scored.with_columns(
        signalCount=(
            pl.col("isNew").cast(pl.Int64)
            + pl.col("isFocused").cast(pl.Int64)
            + pl.col("isLongshot").cast(pl.Int64)
            + pl.col("isBig").cast(pl.Int64)
        )
    )
    return scored.with_columns(suspicious=pl.col("signalCount") >= discovery.minSignals)


def scoreCandidates(
    best: pl.DataFrame,
    activity: pl.DataFrame,
    discovery: DiscoveryConfig,
) -> pl.DataFrame:
    if best.height == 0:
        return pl.DataFrame(schema=suspiciousSchema)
    joined = best.join(activity, on="account", how="left").with_columns(
        pl.col("marketsTraded").fill_null(0)
    )
    scored = withSignals(joined, discovery).with_columns(
        profitUsd=pl.col("buyShares") - pl.col("buyUsd")
    )
    return (
        scored.rename({"marketId": "bestMarketId", "outcome": "bestOutcome"})
        .select(list(suspiciousSchema))
        .sort(["suspicious", "signalCount", "buyUsd"], descending=[True, True, True])
    )


def enrichActivity(
    accounts: list[str],
    dataDir: str,
    splitDate: date,
    refresh: bool,
    client: httpx.Client,
    marketStop: int = activityMarketStop,
) -> pl.DataFrame:
    schema = {
        "account": pl.String,
        "firstTradeTs": pl.Datetime(time_unit="us", time_zone="UTC"),
        "marketsTraded": pl.Int64,
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
        }

    with ThreadPoolExecutor(max_workers=activityWorkers) as pool:
        stats = list(pool.map(one, accounts))
    return pl.DataFrame(stats, schema=schema)


def runDiscover(
    config: Config,
    refresh: bool = False,
    client: httpx.Client | None = None,
) -> DiscoverResult:
    dataDir = config.fetch.dataDir
    markets = pl.read_parquet(Path(dataDir) / "markets.parquet")
    fills = pl.read_parquet(Path(dataDir) / "fills.parquet")
    bets = aggregateBets(fills, markets, config.splitDate)
    best = selectBestBets(bets, config.discovery.minBetUsd)
    note = None
    if best.height > candidateSoftCap:
        narrowed = selectBestBets(bets, config.discovery.minBetUsd, candidatePriceCap)
        note = (
            f"prefilter also requires a winning bet with avgBuyPrice<={candidatePriceCap} "
            f"({best.height} candidates > {candidateSoftCap}; now {narrowed.height})"
        )
        best = narrowed
    ownClient = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": userAgent},
            follow_redirects=True,
        )
    try:
        activity = enrichActivity(
            best["account"].to_list(),
            dataDir,
            config.splitDate,
            refresh,
            client,
            max(config.discovery.maxMarketsTraded, activityMarketStop),
        )
    finally:
        if ownClient:
            client.close()
    frame = scoreCandidates(best, activity, config.discovery)
    path = Path(dataDir) / "suspicious.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)
    suspicious = int(frame.filter(pl.col("suspicious")).height) if frame.height else 0
    return DiscoverResult(
        candidates=frame.height,
        suspicious=suspicious,
        prefilterNote=note,
        frame=frame,
    )


def signalText(row: dict[str, Any] | None) -> str:
    if row is None:
        return "-"
    names = [
        name
        for name, flag in (
            ("new", row["isNew"]),
            ("focused", row["isFocused"]),
            ("longshot", row["isLongshot"]),
            ("big", row["isBig"]),
        )
        if flag
    ]
    return f"{row['signalCount']} {' '.join(names)}".strip()


def labelRows(
    markets: pl.DataFrame,
    scored: pl.DataFrame,
    labelsPath: str | Path,
) -> list[LabelRow]:
    labels = pl.read_csv(labelsPath)
    present = set(markets["eventSlug"].drop_nulls().to_list())
    byAccount = {row["account"]: row for row in scored.iter_rows(named=True)}
    rows: list[LabelRow] = []
    for rec in labels.iter_rows(named=True):
        wallet = str(rec["wallet"]).lower()
        case = str(rec["case"])
        events = caseEventSlugs.get(case, set())
        hit = byAccount.get(wallet)
        rows.append(
            LabelRow(
                wallet=wallet,
                case=case,
                caseInData=bool(events & present),
                candidate=hit is not None,
                suspicious=bool(hit["suspicious"]) if hit else False,
                signals=signalText(hit),
            )
        )
    return rows


def labelRecall(rows: list[LabelRow]) -> tuple[int, int]:
    eligible = [row for row in rows if row.caseInData]
    flagged = [row for row in eligible if row.suspicious]
    return len(flagged), len(eligible)


etherscanApi = "https://api.etherscan.io/v2/api"
etherscanChainId = 137
etherscanPageSize = 1000
# Etherscan's result window stops at 10_000 rows (10 pages of 1000).
etherscanMaxPages = 10

# Collateral seen funding these accounts: USDC.e (main deposit), native USDC,
# pUSD (V2), and Tether's Polygon USDT (symbol USDT0).
collateralSymbols = {
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC.e",
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": "USDC",
    "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb": "pUSD",
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": "USDT0",
}
collateralTokens = frozenset(collateralSymbols)

# Trades and redeems move collateral through these. They are not funders.
polymarketContracts = {
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e": "ctfExchangeV1",
    "0xc5d563a36ae78145c45a50134d48a1215220f80a": "negRiskExchangeV1",
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296": "negRiskAdapter",
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045": "conditionalTokens",
    "0xab45c5a4b0c941a2f231c04c3f49182e1a254052": "proxyFactory",
    "0xaacfeea03eb1561c4e67d661e40682bd20e3541b": "safeFactory",
    "0xe111180000d2663c0091e4f400237545b87b996b": "ctfExchangeV2",
    "0xe2222d279d744050d28e00520010520000310f59": "negRiskExchangeV2",
    "0x006f54f7f9a22e0000cc2ab60031000000ae9fef": "positionManager",
    "0x12121212006e4cd160d18e3f00711da5c3372600": "routerV2",
    "0x1000008dd9001b968442c1000017eae6e0da00ba": "binaryModule",
    "0x200000900045e3b6259600682756002200028933": "negRiskModule",
    "0x30000034706c7d8e12009dab006be20000c031a8": "combinatorialModule",
    "0xe3333700ca9d93003f00f0f71f8515005f6c00aa": "exchangeV3",
    "0xa1200000d0002264c9a1698e001292d00e1b00af": "autoRedeemer",
    "0x93070a847efef7f70739046a929d47a521f5b8ee": "collateralOnramp",
    "0x2957922eb93258b93368531d39facca3b4dc5854": "collateralOfframp",
    "0xebc2459ec962869ca4c0bd1e06368272732bcb08": "permissionedRamp",
    "0xada100db00ca00073811820692005400218fce1f": "ctfCollateralAdapter",
    "0xada2005600dec949baf300f4c6120000bdb6eaab": "negRiskCtfCollateralAdapter",
    "0x00000000000fb5c9adea0298d729a0cb3823cc07": "depositWalletFactory",
    "0x7a18edfe055488a3128f01f563e5b479d92ffc3a": "depositWalletBeacon",
    "0xd216153c06e857cd7f72665e0af1d7d82172f494": "relayHub",
}

fundingSchema = {
    "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
    "fromAddr": pl.String,
    "toAddr": pl.String,
    "amountUsd": pl.Float64,
    "txHash": pl.String,
}
parentsSchema = {
    "parent": pl.String,
    "clusterId": pl.String,
    "accountCount": pl.Int64,
    "suspiciousCount": pl.Int64,
    "totalProfitUsd": pl.Float64,
    "firstSeen": pl.Datetime(time_unit="us", time_zone="UTC"),
    "linkTypes": pl.String,
}
clusterAccountSchema = {
    "clusterId": pl.String,
    "account": pl.String,
    "linkType": pl.String,
}


@dataclass(frozen=True)
class TransferRow:
    ts: int
    fromAddr: str
    toAddr: str
    amountUsd: float
    txHash: str


@dataclass
class EtherscanStats:
    fetched: int = 0
    cached: int = 0


@dataclass(frozen=True)
class HubInfo:
    address: str
    counterparties: int
    accounts: int


@dataclass
class FundingResult:
    traced: int
    hubs: list[HubInfo]
    clusters: int
    fetched: int
    cached: int
    collateralCounts: dict[str, int]
    otherTokens: list[tuple[str, int]]
    parents: pl.DataFrame
    members: pl.DataFrame
    fundingRows: int = 0
    skippedPolymarket: int = 0


def loadEtherscanKey() -> str:
    found = os.environ.get("ETHERSCAN_API_KEY", "").strip()
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
            if key.strip() == "ETHERSCAN_API_KEY":
                cleaned = value.strip().strip('"').strip("'")
                if cleaned:
                    return cleaned
    raise RuntimeError("ETHERSCAN_API_KEY is not set")


def redactSecret(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def etherscanCacheKey(params: dict[str, Any]) -> str:
    action = str(params.get("action") or "call")
    address = str(params.get("address") or "none").lower()
    extra = [
        f"{key}-{params[key]}"
        for key in sorted(params)
        if key not in {"module", "action", "address"}
    ]
    tail = "_".join(extra)
    if len(tail) > 140:
        tail = hashlib.sha256(tail.encode()).hexdigest()[:20]
    return f"{action}_{address}_{tail}" if tail else f"{action}_{address}"


def rateLimited(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    result = payload.get("result")
    text = f"{payload.get('message') or ''} {result if isinstance(result, str) else ''}".lower()
    return "rate limit" in text or "max rate" in text


def payloadUsable(params: dict[str, Any], payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    if params.get("action") == "eth_getCode":
        return isinstance(result, str) and result.startswith("0x")
    if isinstance(result, list):
        return True
    text = f"{payload.get('message') or ''} {result or ''}".lower()
    return "no transactions" in text or "no records" in text


def etherscanCall(
    client: httpx.Client,
    dataDir: str,
    params: dict[str, Any],
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> dict[str, Any]:
    path = cachePath(dataDir, "etherscan", etherscanCacheKey(params))
    if path.exists() and not refresh:
        cached = json.loads(path.read_text())
        if not isinstance(cached, dict):
            raise RuntimeError(f"etherscan cache is not an object: {path.name}")
        stats.cached += 1
        return cached
    query = {"chainid": etherscanChainId, **params, "apikey": apiKey}
    delay = 1.0
    last = "etherscan request failed"
    for _attempt in range(6):
        try:
            payload = getJson(client, etherscanApi, query)
        except (RuntimeError, httpx.TimeoutException, httpx.TransportError) as exc:
            last = redactSecret(str(exc), apiKey)
            time.sleep(delay)
            delay *= 2
            continue
        if not isinstance(payload, dict):
            last = "etherscan returned a non-object"
            time.sleep(delay)
            delay *= 2
            continue
        if rateLimited(payload):
            last = "etherscan rate limit"
            time.sleep(delay)
            delay *= 2
            continue
        if not payloadUsable(params, payload):
            message = payload.get("message") or payload.get("result") or ""
            if isinstance(message, str) and "invalid api key" in message.lower():
                raise RuntimeError("etherscan rejected the API key")
            raise RuntimeError(f"etherscan {params.get('action')} failed: {str(message)[:160]}")
        stats.fetched += 1
        writeJson(path, payload)
        return payload
    raise RuntimeError(last)


def tokenRows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    return []


def isEoa(payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    if not isinstance(result, str) or not result.startswith("0x"):
        message = str(payload.get("message") or result or "")[:160]
        raise RuntimeError(f"etherscan getcode failed: {message}")
    body = result[2:]
    return body == "" or set(body) <= {"0"}


def tokenAmount(row: dict[str, Any]) -> float:
    raw = row.get("tokenDecimal")
    decimals = int(raw) if raw not in (None, "") else 6
    return int(row.get("value") or 0) / (10**decimals)


def parseCollateral(row: dict[str, Any], minFundingUsd: float) -> TransferRow | None:
    token = str(row.get("contractAddress") or "").lower()
    if token not in collateralTokens:
        return None
    src = str(row.get("from") or "").lower()
    dst = str(row.get("to") or "").lower()
    if not src or not dst or src == dst:
        return None
    if src in polymarketContracts or dst in polymarketContracts:
        return None
    amount = tokenAmount(row)
    if amount < minFundingUsd:
        return None
    return TransferRow(
        ts=int(row["timeStamp"]),
        fromAddr=src,
        toAddr=dst,
        amountUsd=amount,
        txHash=str(row.get("hash") or "").lower(),
    )


def collateralCounterparties(address: str, rows: list[dict[str, Any]]) -> int:
    # Spam airdrops come from many token contracts. Count stablecoin
    # counterparties only, or a normal wallet looks like a hub.
    address = address.lower()
    others: set[str] = set()
    for row in rows:
        token = str(row.get("contractAddress") or "").lower()
        if token not in collateralTokens:
            continue
        src = str(row.get("from") or "").lower()
        dst = str(row.get("to") or "").lower()
        if src == address and dst and dst != address:
            others.add(dst)
        elif dst == address and src and src != address:
            others.add(src)
    return len(others)


def hubAddresses(samples: dict[str, list[dict[str, Any]]], minimum: int) -> dict[str, int]:
    found: dict[str, int] = {}
    for address, rows in samples.items():
        count = collateralCounterparties(address, rows)
        if count >= minimum:
            found[address.lower()] = count
    return found


def hubFromSample(
    descCount: int,
    ascCount: int,
    pageFull: bool,
    isContract: bool,
    minimum: int,
    codeChars: int = 0,
) -> bool:
    # Newest-page counterparties miss routers whose recent flow sits on a few
    # pools. A full page plus real bytecode is a router; the ~125-byte funding
    # clones in this tape are not.
    if max(descCount, ascCount) >= minimum:
        return True
    return pageFull and isContract and codeChars > 1000


def fetchTokenPage(
    client: httpx.Client,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
    sort: str,
    page: int,
) -> list[dict[str, Any]]:
    payload = etherscanCall(
        client,
        dataDir,
        {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": page,
            "offset": etherscanPageSize,
            "sort": sort,
        },
        refresh,
        apiKey,
        stats,
    )
    return tokenRows(payload)


def fetchTokenHistory(
    client: httpx.Client,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, etherscanMaxPages + 1):
        batch = fetchTokenPage(client, dataDir, address, refresh, apiKey, stats, "asc", page)
        rows.extend(batch)
        if len(batch) < etherscanPageSize:
            break
    return rows


def fetchProbe(
    client: httpx.Client,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> list[dict[str, Any]]:
    # Newest-first page: a deposit solver or hot wallet shows many counterparties here.
    return fetchTokenPage(client, dataDir, address, refresh, apiKey, stats, "desc", 1)


def classifyProbe(
    client: httpx.Client,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
    descRows: list[dict[str, Any]],
    minimum: int,
) -> int | None:
    descCount = collateralCounterparties(address, descRows)
    ascCount = 0
    pageFull = len(descRows) >= etherscanPageSize
    if descCount < minimum and pageFull:
        ascRows = fetchTokenPage(client, dataDir, address, refresh, apiKey, stats, "asc", 1)
        ascCount = collateralCounterparties(address, ascRows)
    isContract = False
    codeChars = 0
    if pageFull and max(descCount, ascCount) < minimum:
        payload = codePayload(client, dataDir, address, refresh, apiKey, stats)
        isContract = not isEoa(payload)
        codeChars = len(str(payload.get("result") or ""))
    if not hubFromSample(descCount, ascCount, pageFull, isContract, minimum, codeChars):
        return None
    return max(descCount, ascCount)


def codePayload(
    client: httpx.Client,
    dataDir: str,
    address: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
) -> dict[str, Any]:
    return etherscanCall(
        client,
        dataDir,
        {
            "module": "proxy",
            "action": "eth_getCode",
            "address": address,
            "tag": "latest",
        },
        refresh,
        apiKey,
        stats,
    )


def buildFundingClusters(
    accounts: set[str],
    suspicious: set[str],
    transfers: list[TransferRow],
    blocked: set[str],
    eoaFunders: set[str],
    grandparents: dict[str, set[str]],
    profits: dict[str, float],
    splitTs: int,
    minSuspiciousAccounts: int,
    fundingHops: int,
    minFundingUsd: float,
    fundedByParent: dict[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accounts = {account.lower() for account in accounts}
    suspicious = {account.lower() for account in suspicious} & accounts
    blocked = {account.lower() for account in blocked}
    eoaFunders = {account.lower() for account in eoaFunders}
    grandparents = {
        funder.lower(): {item.lower() for item in sources}
        for funder, sources in grandparents.items()
    }
    funded = {
        parent.lower(): {account.lower() for account in recipients}
        for parent, recipients in (fundedByParent or {}).items()
    }
    usable = [
        row
        for row in transfers
        if row.amountUsd >= minFundingUsd
        and row.fromAddr != row.toAddr
        and row.ts < splitTs
        and row.fromAddr not in blocked
        and row.toAddr not in blocked
    ]
    uf = {account: account for account in accounts}
    linkOf: dict[str, set[str]] = {account: set() for account in accounts}

    def find(account: str) -> str:
        root = account
        while uf[root] != root:
            root = uf[root]
        while uf[account] != root:
            nxt = uf[account]
            uf[account] = root
            account = nxt
        return root

    def union(left: str, right: str, kind: str) -> None:
        leftRoot = find(left)
        rightRoot = find(right)
        if leftRoot != rightRoot:
            if leftRoot < rightRoot:
                uf[rightRoot] = leftRoot
            else:
                uf[leftRoot] = rightRoot
        linkOf[left].add(kind)
        linkOf[right].add(kind)

    byFunder: dict[str, set[str]] = defaultdict(set)
    byCashOut: dict[str, set[str]] = defaultdict(set)
    for row in usable:
        if row.toAddr in accounts and row.fromAddr not in blocked:
            byFunder[row.fromAddr].add(row.toAddr)
        if row.fromAddr in accounts and row.toAddr not in accounts and row.toAddr not in blocked:
            byCashOut[row.toAddr].add(row.fromAddr)
        if row.fromAddr in accounts and row.toAddr in accounts:
            union(row.fromAddr, row.toAddr, "direct")

    def linkGroup(group: set[str], kind: str) -> None:
        members = sorted(account for account in group if account in accounts)
        if len(members) < 2:
            return
        for other in members[1:]:
            union(members[0], other, kind)

    for group in byFunder.values():
        linkGroup(group, "sharedFunder")
    for group in byCashOut.values():
        linkGroup(group, "sharedCashOut")

    reached: dict[str, set[str]] = defaultdict(set)
    if fundingHops >= 2:
        for funder, group in byFunder.items():
            if funder not in eoaFunders:
                continue
            for grand in grandparents.get(funder, ()):
                if grand in blocked or grand == funder:
                    continue
                for account in group:
                    if account in accounts:
                        reached[grand].add(account)
        for group in reached.values():
            linkGroup(group, "hop")

    components: dict[str, list[str]] = defaultdict(list)
    for account in accounts:
        components[find(account)].append(account)

    parentRows: list[dict[str, Any]] = []
    memberRows: list[dict[str, Any]] = []
    for group in components.values():
        component = set(group)
        sus = sorted(account for account in component if account in suspicious)
        if len(sus) < minSuspiciousAccounts:
            continue
        scores: dict[str, set[str]] = defaultdict(set)
        for funder, fundedAccounts in byFunder.items():
            if funder in blocked:
                continue
            hit = {
                account
                for account in fundedAccounts
                if account in component and account in suspicious
            }
            if hit:
                scores[funder] |= hit
        if fundingHops >= 2:
            for grand, fundedAccounts in reached.items():
                if grand in blocked:
                    continue
                hit = {
                    account
                    for account in fundedAccounts
                    if account in component and account in suspicious
                }
                if hit:
                    scores[grand] |= hit
        bestAddr = None
        bestCount = 0
        for addr, hit in scores.items():
            count = len(hit)
            if count < 2:
                continue
            if bestAddr is None or count > bestCount or (count == bestCount and addr < bestAddr):
                bestAddr = addr
                bestCount = count
        clusterId = min(component)
        parent = bestAddr if bestAddr is not None else f"component:{clusterId}"
        times = [
            row.ts
            for row in usable
            if row.fromAddr in component or row.toAddr in component
        ]
        kinds = {kind for account in component for kind in linkOf[account]}
        present = set(component)
        extras: list[str] = []
        if not parent.startswith("component:"):
            for account in sorted(funded.get(parent, ())):
                if account in present or account in blocked or account == parent:
                    continue
                extras.append(account)
                present.add(account)
        parentRows.append(
            {
                "parent": parent,
                "clusterId": clusterId,
                "accountCount": len(component) + len(extras),
                "suspiciousCount": len(sus),
                "totalProfitUsd": sum(profits.get(account, 0.0) for account in sus),
                "firstSeen": min(times) if times else None,
                "linkTypes": ",".join(sorted(kinds)),
            }
        )
        for account in sorted(component):
            memberRows.append(
                {
                    "clusterId": clusterId,
                    "account": account,
                    "linkType": ",".join(sorted(linkOf[account])),
                }
            )
        for account in extras:
            memberRows.append(
                {"clusterId": clusterId, "account": account, "linkType": "funded"}
            )
    return parentRows, memberRows


def fundingFrame(rows: list[TransferRow]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=fundingSchema)
    frame = pl.DataFrame(
        {
            "ts": [datetime.fromtimestamp(row.ts, tz=timezone.utc) for row in rows],
            "fromAddr": [row.fromAddr for row in rows],
            "toAddr": [row.toAddr for row in rows],
            "amountUsd": [row.amountUsd for row in rows],
            "txHash": [row.txHash for row in rows],
        },
        schema=fundingSchema,
    )
    return frame.unique(subset=["txHash", "fromAddr", "toAddr", "amountUsd"]).sort("ts")


def parentsFrame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=parentsSchema)
    return pl.DataFrame(
        {
            "parent": [row["parent"] for row in rows],
            "clusterId": [row["clusterId"] for row in rows],
            "accountCount": [row["accountCount"] for row in rows],
            "suspiciousCount": [row["suspiciousCount"] for row in rows],
            "totalProfitUsd": [row["totalProfitUsd"] for row in rows],
            "firstSeen": [
                datetime.fromtimestamp(row["firstSeen"], tz=timezone.utc)
                if row["firstSeen"] is not None
                else None
                for row in rows
            ],
            "linkTypes": [row["linkTypes"] for row in rows],
        },
        schema=parentsSchema,
    ).sort(["suspiciousCount", "totalProfitUsd", "parent"], descending=[True, True, False])


def membersFrame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=clusterAccountSchema)
    return pl.DataFrame(rows, schema=clusterAccountSchema).sort(["clusterId", "account"])


def noteOtherToken(row: dict[str, Any], account: str, minFundingUsd: float, counter: Counter[str]) -> None:
    token = str(row.get("contractAddress") or "").lower()
    if token in collateralTokens or token in polymarketContracts:
        return
    if str(row.get("to") or "").lower() != account:
        return
    if str(row.get("tokenDecimal") or "") != "6":
        return
    amount = tokenAmount(row)
    if amount < minFundingUsd or amount > 10_000_000:
        return
    symbol = str(row.get("tokenSymbol") or token[:10])
    counter[f"{symbol}:{token}"] += 1


def polymarketHit(row: dict[str, Any]) -> bool:
    token = str(row.get("contractAddress") or "").lower()
    if token not in collateralTokens:
        return False
    src = str(row.get("from") or "").lower()
    dst = str(row.get("to") or "").lower()
    return src in polymarketContracts or dst in polymarketContracts


def runFunding(
    config: Config,
    refresh: bool = False,
    extraAccounts: list[str] | None = None,
    client: httpx.Client | None = None,
) -> FundingResult:
    dataDir = config.fetch.dataDir
    frame = pl.read_parquet(Path(dataDir) / "suspicious.parquet")
    suspicious = {account.lower() for account in frame.filter(pl.col("suspicious"))["account"].to_list()}
    profits = {
        str(row["account"]).lower(): float(row["profitUsd"] or 0.0)
        for row in frame.select(["account", "profitUsd"]).iter_rows(named=True)
    }
    traced = set(suspicious)
    for account in extraAccounts or []:
        traced.add(account.lower())
    splitTs = int(splitCutoff(config.splitDate).timestamp())
    minimum = config.discovery.minFundingUsd
    apiKey = loadEtherscanKey()
    stats = EtherscanStats()
    ownClient = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": userAgent},
            follow_redirects=True,
        )
    transfers: list[TransferRow] = []
    seen: set[tuple[Any, ...]] = set()
    collateralCounts: Counter[str] = Counter()
    otherTokens: Counter[str] = Counter()
    skippedPolymarket = 0
    ordered = sorted(traced)
    try:
        for index, account in enumerate(ordered, start=1):
            if index == 1 or index % 25 == 0 or index == len(ordered):
                print(f"funding {index}/{len(ordered)}", flush=True)
            raw = fetchTokenHistory(client, dataDir, account, refresh, apiKey, stats)
            for row in raw:
                if polymarketHit(row):
                    skippedPolymarket += 1
                noteOtherToken(row, account, minimum, otherTokens)
                parsed = parseCollateral(row, minimum)
                if parsed is None:
                    continue
                key = (parsed.txHash, parsed.fromAddr, parsed.toAddr, parsed.amountUsd, parsed.ts)
                if key in seen:
                    continue
                seen.add(key)
                token = str(row.get("contractAddress") or "").lower()
                collateralCounts[collateralSymbols[token]] += 1
                transfers.append(parsed)

        funders, cashOuts = counterpartiesBeforeSplit(transfers, traced, splitTs)
        probeTargets = set(funders) | {addr for addr, group in cashOuts.items() if len(group) >= 2}
        probeTargets -= traced
        probeTargets -= {addr.lower() for addr in config.discovery.excludedFunders}
        probes: dict[str, list[dict[str, Any]]] = {}
        targets = sorted(probeTargets)
        for index, address in enumerate(targets, start=1):
            if index == 1 or index % 25 == 0 or index == len(targets):
                print(f"hub probe {index}/{len(targets)}", flush=True)
            probes[address] = fetchProbe(client, dataDir, address, refresh, apiKey, stats)
        counted: dict[str, int] = {}
        for address, rows in probes.items():
            count = classifyProbe(
                client,
                dataDir,
                address,
                refresh,
                apiKey,
                stats,
                rows,
                config.discovery.hubMinCounterparties,
            )
            if count is not None:
                counted[address] = count
        hubs = set(counted)
        excluded = {addr.lower() for addr in config.discovery.excludedFunders}
        eoaFunders: set[str] = set()
        grandparents: dict[str, set[str]] = {}
        if config.discovery.fundingHops >= 2:
            eoaFunders, grandparents, extraHubs = hopSources(
                client,
                dataDir,
                refresh,
                apiKey,
                stats,
                funders,
                hubs,
                excluded,
                probes,
                minimum,
                config.discovery.hubMinCounterparties,
            )
            for address, count in extraHubs.items():
                counted.setdefault(address, count)
            hubs |= set(extraHubs)
        blocked = hubs | excluded | set(polymarketContracts)
        parentRows, memberRows = buildFundingClusters(
            accounts=traced,
            suspicious=suspicious,
            transfers=transfers,
            blocked=blocked,
            eoaFunders=eoaFunders,
            grandparents=grandparents,
            profits=profits,
            splitTs=splitTs,
            minSuspiciousAccounts=config.discovery.minSuspiciousAccounts,
            fundingHops=config.discovery.fundingHops,
            minFundingUsd=minimum,
        )
        fundedByParent: dict[str, set[str]] = {}
        for row in parentRows:
            parent = row["parent"]
            if parent.startswith("component:"):
                continue
            history = fetchTokenHistory(client, dataDir, parent, refresh, apiKey, stats)
            fundedByParent[parent] = {
                item
                for item in outgoingRecipients(parent, history, minimum)
                if item not in blocked and item != parent
            }
        if fundedByParent:
            parentRows, memberRows = buildFundingClusters(
                accounts=traced,
                suspicious=suspicious,
                transfers=transfers,
                blocked=blocked,
                eoaFunders=eoaFunders,
                grandparents=grandparents,
                profits=profits,
                splitTs=splitTs,
                minSuspiciousAccounts=config.discovery.minSuspiciousAccounts,
                fundingHops=config.discovery.fundingHops,
                minFundingUsd=minimum,
                fundedByParent=fundedByParent,
            )
    finally:
        if ownClient:
            client.close()

    touch: dict[str, set[str]] = defaultdict(set)
    for row in transfers:
        if row.ts >= splitTs:
            continue
        if row.fromAddr in hubs and row.toAddr in traced:
            touch[row.fromAddr].add(row.toAddr)
        if row.toAddr in hubs and row.fromAddr in traced:
            touch[row.toAddr].add(row.fromAddr)
    hubList = [
        HubInfo(address=address, counterparties=count, accounts=len(touch.get(address, ())))
        for address, count in sorted(counted.items(), key=lambda item: (-item[1], item[0]))
    ]
    funding = fundingFrame(transfers)
    parents = parentsFrame(parentRows)
    members = membersFrame(memberRows)
    out = Path(dataDir)
    out.mkdir(parents=True, exist_ok=True)
    funding.write_parquet(out / "funding.parquet")
    parents.write_parquet(out / "parents.parquet")
    members.write_parquet(out / "clusterAccounts.parquet")
    return FundingResult(
        traced=len(traced),
        hubs=hubList,
        clusters=parents.height,
        fetched=stats.fetched,
        cached=stats.cached,
        collateralCounts=dict(collateralCounts),
        otherTokens=otherTokens.most_common(8),
        parents=parents,
        members=members,
        fundingRows=funding.height,
        skippedPolymarket=skippedPolymarket,
    )


def counterpartiesBeforeSplit(
    transfers: list[TransferRow],
    traced: set[str],
    splitTs: int,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    funders: dict[str, set[str]] = defaultdict(set)
    cashOuts: dict[str, set[str]] = defaultdict(set)
    for row in transfers:
        if row.ts >= splitTs:
            continue
        if row.toAddr in traced and row.fromAddr not in traced:
            funders[row.fromAddr].add(row.toAddr)
        if row.fromAddr in traced and row.toAddr not in traced:
            cashOuts[row.toAddr].add(row.fromAddr)
    return funders, cashOuts


def outgoingRecipients(address: str, rows: list[dict[str, Any]], minFundingUsd: float) -> set[str]:
    found: set[str] = set()
    for row in rows:
        parsed = parseCollateral(row, minFundingUsd)
        if parsed is not None and parsed.fromAddr == address:
            found.add(parsed.toAddr)
    return found


def incomingFunders(address: str, rows: list[dict[str, Any]], minFundingUsd: float) -> set[str]:
    found: set[str] = set()
    for row in rows:
        parsed = parseCollateral(row, minFundingUsd)
        if parsed is not None and parsed.toAddr == address:
            found.add(parsed.fromAddr)
    return found


def hopSources(
    client: httpx.Client,
    dataDir: str,
    refresh: bool,
    apiKey: str,
    stats: EtherscanStats,
    funders: dict[str, set[str]],
    hubs: set[str],
    excluded: set[str],
    probes: dict[str, list[dict[str, Any]]],
    minFundingUsd: float,
    hubMinimum: int,
) -> tuple[set[str], dict[str, set[str]], dict[str, int]]:
    blocked = hubs | excluded
    eoaFunders: set[str] = set()
    grandparents: dict[str, set[str]] = {}
    reached: dict[str, set[str]] = defaultdict(set)
    candidates = sorted(addr for addr in funders if addr not in blocked)
    for index, funder in enumerate(candidates, start=1):
        if index == 1 or index % 25 == 0 or index == len(candidates):
            print(f"funder code {index}/{len(candidates)}", flush=True)
        payload = codePayload(client, dataDir, funder, refresh, apiKey, stats)
        if not isEoa(payload):
            continue
        eoaFunders.add(funder)
        sources = incomingFunders(funder, probes.get(funder, []), minFundingUsd)
        grandparents[funder] = sources
        for source in sources:
            reached[source].update(funders[funder])
    extraSamples: dict[str, list[dict[str, Any]]] = {}
    for source, group in reached.items():
        if len(group) < 2 or source in probes or source in blocked:
            continue
        extraSamples[source] = fetchProbe(client, dataDir, source, refresh, apiKey, stats)
    extraHubs: dict[str, int] = {}
    for source, rows in extraSamples.items():
        count = classifyProbe(
            client, dataDir, source, refresh, apiKey, stats, rows, hubMinimum
        )
        if count is not None:
            extraHubs[source] = count
    if extraHubs:
        grandparents = {
            funder: {source for source in sources if source not in extraHubs and source not in blocked}
            for funder, sources in grandparents.items()
        }
    return eoaFunders, grandparents, extraHubs
