"""Which insider buys to copy, and how many shares.

Net shares are tracked per (account group, market, outcome). An account group is
the account itself, or a cluster id when a cluster map is supplied. Buys are handled
one fill at a time: a 10-minute burst resets from its own first fill, and price
filters use the size-weighted average of buys already seen in that burst, including
the fill being processed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

import polars as pl

burstWindow = timedelta(minutes=10)


@dataclass
class BookMemory:
    largestUsd: dict[tuple[str, str], float] = field(default_factory=dict)
    copiedMarkets: dict[tuple[str, str], set[str]] = field(default_factory=dict)


@dataclass
class Burst:
    start: datetime
    usd: float = 0.0
    shares: float = 0.0
    copying: bool = False


def eventKey(eventSlug: str | None, marketId: str) -> str:
    if eventSlug:
        return eventSlug
    return marketId


def normalizeClusterMap(clusterMap: dict[str, str] | None) -> dict[str, str] | None:
    if not clusterMap:
        return None
    return {account.lower(): clusterId for account, clusterId in clusterMap.items()}


def withGroup(frame: pl.DataFrame, clusterMap: dict[str, str] | None) -> pl.DataFrame:
    frame = frame.with_columns(pl.col("account").str.to_lowercase().alias("account"))
    mapping = normalizeClusterMap(clusterMap)
    if not mapping:
        return frame.with_columns(pl.col("account").alias("accountGroup"))
    keys = sorted(mapping)
    groups = pl.DataFrame(
        {"account": keys, "accountGroup": [mapping[key] for key in keys]}
    )
    return frame.join(groups, on="account", how="left").with_columns(
        pl.coalesce("accountGroup", "account").alias("accountGroup")
    )


def netPath(
    fills: pl.DataFrame,
    accountsToCopy: Sequence[str],
    clusterMap: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Signed shares after each fill, in time order."""
    schema = {
        "rowId": pl.UInt32,
        "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
        "account": pl.String,
        "accountGroup": pl.String,
        "marketId": pl.String,
        "outcome": pl.String,
        "side": pl.String,
        "size": pl.Float64,
        "price": pl.Float64,
        "netShares": pl.Float64,
    }
    wanted = {account.lower() for account in accountsToCopy}
    if fills.height == 0 or not wanted:
        return pl.DataFrame(schema=schema)
    frame = fills.filter(
        pl.col("account").str.to_lowercase().is_in(list(wanted))
        & pl.col("side").is_in(["BUY", "SELL"])
        & (pl.col("size") > 0)
        & pl.col("price").is_not_null()
    )
    if frame.height == 0:
        return pl.DataFrame(schema=schema)
    frame = withGroup(frame, clusterMap).sort(
        ["ts", "account", "marketId", "outcome", "side", "size", "price"]
    )
    frame = frame.with_row_index("rowId")
    signed = pl.when(pl.col("side") == "BUY").then(pl.col("size")).otherwise(-pl.col("size"))
    return frame.with_columns(
        signed.cum_sum()
        .over(["accountGroup", "marketId", "outcome"], order_by="rowId")
        .alias("netShares")
    ).select(list(schema))


def observeBuy(burst: Burst | None, ts: datetime, size: float, price: float) -> tuple[Burst, float]:
    """Add one buy to the open burst, or start a new one after 10 minutes."""
    if burst is None or ts > burst.start + burstWindow:
        burst = Burst(start=ts)
    burst.usd += size * price
    burst.shares += size
    return burst, size


def planBuy(
    burst: Burst,
    fillSize: float,
    group: str,
    marketId: str,
    eventSlug: str | None,
    memory: BookMemory,
    params,
) -> tuple[str, float]:
    """`trigger` copies the shares seen so far; `add` copies only this fill."""
    if burst.copying:
        if params.sizing == "mirrorPct":
            return "add", fillSize
        return "skip", 0.0
    row = {
        "accountGroup": group,
        "marketId": marketId,
        "eventSlug": eventSlug,
        "usd": burst.usd,
        "price": burst.usd / burst.shares,
    }
    if not takeEntry(row, memory, params):
        return "skip", 0.0
    return "trigger", burst.shares


def noteLargest(usd: float, group: str, key: str, memory: BookMemory) -> bool:
    """True when this buy is strictly the largest seen so far. The first buy counts."""
    prior = memory.largestUsd.get((group, key))
    if prior is None or usd > prior:
        memory.largestUsd[(group, key)] = usd
        return True
    return False


def takeEntry(row: dict, memory: BookMemory, params) -> bool:
    """Filters for one candidate. Call in time order. Does not record the copy."""
    group = row["accountGroup"]
    key = eventKey(row.get("eventSlug"), row["marketId"])
    usd = float(row["usd"])
    price = float(row["price"])
    if params.copyRule == "largestPerEvent" and not noteLargest(usd, group, key, memory):
        return False
    if usd < params.minNetUsd:
        return False
    if price > params.maxEntryPrice:
        return False
    if params.minEntryPrice is not None and price < params.minEntryPrice:
        return False
    if params.maxEntriesPerEvent is not None:
        have = memory.copiedMarkets.get((group, key), set())
        if row["marketId"] not in have and len(have) >= params.maxEntriesPerEvent:
            return False
    return True


def recordCopy(row: dict, memory: BookMemory) -> None:
    group = row["accountGroup"]
    key = eventKey(row.get("eventSlug"), row["marketId"])
    memory.copiedMarkets.setdefault((group, key), set()).add(row["marketId"])


def orderShares(
    theirSize: float,
    ourPrice: float | None,
    params,
    openExposure: float,
    positionUsd: float = 0.0,
) -> float:
    """Shares to buy. Zero when there is no price or no room under the caps."""
    if ourPrice is None or ourPrice <= 0 or theirSize <= 0:
        return 0.0
    if params.sizing == "fixed":
        usd = float(params.fixedUsd)
    else:
        usd = float(theirSize) * float(params.mirrorPct) * float(ourPrice)
    if params.maxPositionUsd is not None:
        room = float(params.maxPositionUsd) - positionUsd
        if room <= 0:
            return 0.0
        usd = min(usd, room)
    if params.maxTotalExposureUsd is not None:
        room = float(params.maxTotalExposureUsd) - openExposure
        if room <= 0:
            return 0.0
        usd = min(usd, room)
    if usd <= 0:
        return 0.0
    return usd / float(ourPrice)
