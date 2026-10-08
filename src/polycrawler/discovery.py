import json
import threading
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
