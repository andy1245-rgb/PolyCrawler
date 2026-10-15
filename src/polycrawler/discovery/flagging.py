from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from polycrawler.config import DiscoveryConfig

candidateSoftCap = 3000
candidatePriceCap = 0.7

signalSchema = {
    "account": pl.String,
    "bestMarketId": pl.String,
    "bestOutcome": pl.String,
    "buyUsd": pl.Float64,
    "avgBuyPrice": pl.Float64,
    "firstBuyTs": pl.Datetime(time_unit="us", time_zone="UTC"),
    "firstTradeTs": pl.Datetime(time_unit="us", time_zone="UTC"),
    "leadHours": pl.Float64,
    "accountAgeDays": pl.Float64,
    "marketsTraded": pl.Int64,
    "isNew": pl.Boolean,
    "isFocused": pl.Boolean,
    "isLongshot": pl.Boolean,
    "isBig": pl.Boolean,
    "isLate": pl.Boolean,
    "signalCount": pl.Int64,
    "suspicious": pl.Boolean,
    "profitUsd": pl.Float64,
}
featureSchema = {
    "ladderPrecision": pl.Float64,
    "losingLadderBets": pl.Int64,
    "leadHours": pl.Float64,
    "recreationalShare": pl.Float64,
    "coTradeClusterId": pl.String,
    "coTradeClusterSize": pl.Int64,
}
suspiciousSchema = {**signalSchema, **featureSchema}

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
    resolved = resolvedMarkets(markets, splitDate).select(
        ["marketId", "winner", pl.coalesce("resolvedAt", "endDate").alias("resolvedTs")]
    )
    buys = fills.filter((pl.col("side") == "BUY") & (pl.col("ts") < cutoff))
    buys = buys.join(resolved, on="marketId", how="inner")
    schema = {
        "account": pl.String,
        "marketId": pl.String,
        "outcome": pl.String,
        "buyUsd": pl.Float64,
        "buyShares": pl.Float64,
        "avgBuyPrice": pl.Float64,
        "firstBuyTs": pl.Datetime(time_unit="us", time_zone="UTC"),
        "resolvedTs": pl.Datetime(time_unit="us", time_zone="UTC"),
        "winner": pl.String,
        "won": pl.Boolean,
    }
    if buys.height == 0:
        return pl.DataFrame(schema=schema)
    return (
        buys.group_by(["account", "marketId", "outcome"])
        .agg(
            (pl.col("size") * pl.col("price")).sum().alias("buyUsd"),
            pl.col("size").sum().alias("buyShares"),
            pl.col("ts").min().alias("firstBuyTs"),
            pl.col("resolvedTs").first().alias("resolvedTs"),
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


def withSignals(frame: pl.DataFrame, discovery: DiscoveryConfig) -> pl.DataFrame:
    age = (pl.col("firstBuyTs") - pl.col("firstTradeTs")).dt.total_seconds() / 86400.0
    lead = (pl.col("resolvedTs") - pl.col("firstBuyTs")).dt.total_seconds() / 3600.0
    late = (
        pl.lit(True)
        if discovery.maxFlagLeadHours is None
        else (lead <= discovery.maxFlagLeadHours).fill_null(False)
    )
    scored = frame.with_columns(
        accountAgeDays=age,
        leadHours=lead,
        isNew=(age <= discovery.maxAccountAgeDays).fill_null(False),
        isFocused=pl.col("marketsTraded") <= discovery.maxMarketsTraded,
        isLongshot=pl.col("avgBuyPrice") <= discovery.maxBuyPrice,
        isBig=pl.col("buyUsd") >= discovery.minBetUsd,
        isLate=late,
    )
    scored = scored.with_columns(
        signalCount=(
            pl.col("isNew").cast(pl.Int64)
            + pl.col("isFocused").cast(pl.Int64)
            + pl.col("isLongshot").cast(pl.Int64)
            + pl.col("isBig").cast(pl.Int64)
        )
    ).with_columns(
        # Hard gate, not a signal: on date-ladder events speculators also buy
        # the winning date late, so counting isLate just inflates the pool.
        # As a gate it cuts the long-lead speculators while every labeled
        # insider kept late=True (research/leadGate.md).
        suspicious=pl.col("signalCount") >= discovery.minSignals,
    )
    if discovery.maxFlagLeadHours is not None:
        scored = scored.with_columns(suspicious=pl.col("suspicious") & pl.col("isLate"))
    return scored


def scoreCandidates(
    best: pl.DataFrame,
    activity: pl.DataFrame,
    discovery: DiscoveryConfig,
) -> pl.DataFrame:
    if best.height == 0:
        return pl.DataFrame(schema=signalSchema)
    joined = best.join(activity, on="account", how="left").with_columns(
        pl.col("marketsTraded").fill_null(0)
    )
    scored = withSignals(joined, discovery).with_columns(
        profitUsd=pl.col("buyShares") - pl.col("buyUsd")
    )
    return (
        scored.rename({"marketId": "bestMarketId", "outcome": "bestOutcome"})
        .select(list(signalSchema))
        .sort(["suspicious", "signalCount", "buyUsd"], descending=[True, True, True])
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
            ("late", row["isLate"]),
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


def betFeatures(
    fills: pl.DataFrame,
    markets: pl.DataFrame,
    bets: pl.DataFrame,
    best: pl.DataFrame,
    splitDate: date,
) -> pl.DataFrame:
    """Point-in-time ladder stats for the flag bet. Resolution time is resolvedAt, else endDate."""
    empty = pl.DataFrame(
        schema={
            "account": pl.String,
            "ladderPrecision": pl.Float64,
            "losingLadderBets": pl.Int64,
            "leadHours": pl.Float64,
        }
    )
    if best.height == 0:
        return empty
    cutoff = splitCutoff(splitDate)
    info = markets.select(
        "marketId",
        "eventSlug",
        pl.coalesce("resolvedAt", "endDate").alias("resolvedTs"),
    )
    accounts = best["account"].unique()
    buys = fills.filter(
        (pl.col("side") == "BUY") & (pl.col("ts") < cutoff) & pl.col("account").is_in(accounts)
    )
    usd = (
        buys.group_by(["account", "marketId"])
        .agg((pl.col("size") * pl.col("price")).sum().alias("marketUsd"))
        .join(info.select("marketId", "eventSlug"), on="marketId", how="left")
    )
    eventUsd = usd.group_by(["account", "eventSlug"]).agg(pl.col("marketUsd").sum().alias("eventUsd"))
    flag = best.select(
        "account",
        pl.col("marketId").alias("bestMarketId"),
        pl.col("firstBuyTs").alias("flagTs"),
    ).join(info, left_on="bestMarketId", right_on="marketId", how="left")
    flag = flag.join(
        usd.select("account", pl.col("marketId").alias("bestMarketId"), "marketUsd"),
        on=["account", "bestMarketId"],
        how="left",
    ).join(eventUsd, on=["account", "eventSlug"], how="left")
    flag = flag.with_columns(
        pl.when(pl.col("eventUsd") > 0)
        .then(pl.col("marketUsd") / pl.col("eventUsd"))
        .otherwise(None)
        .alias("ladderPrecision"),
        ((pl.col("resolvedTs") - pl.col("flagTs")).dt.total_seconds() / 3600.0).alias("leadHours"),
    )
    losing = (
        bets.filter(~pl.col("won"))
        .join(info.select("marketId", "eventSlug"), on="marketId", how="left")
        .join(flag.select("account", "eventSlug", "flagTs"), on=["account", "eventSlug"], how="inner")
        .filter(pl.col("firstBuyTs") < pl.col("flagTs"))
        .group_by("account")
        .agg(pl.len().alias("losingLadderBets"))
    )
    return (
        flag.join(losing, on="account", how="left")
        .with_columns(pl.col("losingLadderBets").fill_null(0).cast(pl.Int64))
        .select("account", "ladderPrecision", "losingLadderBets", "leadHours")
    )
