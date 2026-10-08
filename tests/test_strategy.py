from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from polycrawler.backtest import BacktestParams
from polycrawler.strategy import (
    BookMemory,
    netPath,
    noteLargest,
    observeBuy,
    orderShares,
    planBuy,
    recordCopy,
    takeEntry,
)

utc = timezone.utc


def ts(seconds: int = 0) -> datetime:
    return datetime(2026, 4, 1, tzinfo=utc) + timedelta(seconds=seconds)


def params(**updates) -> BacktestParams:
    base = dict(
        minNetUsd=0,
        maxEntryPrice=1,
        minEntryPrice=None,
        maxEntriesPerEvent=None,
        copyRule="all",
        sizing="mirrorPct",
        fixedUsd=100,
        mirrorPct=1,
        maxPositionUsd=None,
        maxTotalExposureUsd=None,
        exitMode="holdToResolution",
        delaySec=0,
        slippageBps=0,
    )
    base.update(updates)
    return BacktestParams.model_validate(base)


def row(
    marketId: str = "m1",
    usd: float = 100,
    price: float = 0.4,
    eventSlug: str = "event",
) -> dict:
    return {
        "accountGroup": "g",
        "account": "0xa",
        "marketId": marketId,
        "eventSlug": eventSlug,
        "outcome": "Yes",
        "usd": usd,
        "price": price,
        "size": usd / price,
    }


def test_netSharesFollowFillsAndClusterMap() -> None:
    t0 = ts(0)
    fills = pl.DataFrame(
        [
            {
                "ts": t0,
                "account": "0xA",
                "marketId": "m",
                "outcome": "Yes",
                "side": "BUY",
                "size": 10.0,
                "price": 0.4,
            },
            {
                "ts": t0 + timedelta(seconds=1),
                "account": "0xB",
                "marketId": "m",
                "outcome": "Yes",
                "side": "BUY",
                "size": 4.0,
                "price": 0.4,
            },
            {
                "ts": t0 + timedelta(seconds=2),
                "account": "0xA",
                "marketId": "m",
                "outcome": "Yes",
                "side": "SELL",
                "size": 3.0,
                "price": 0.5,
            },
            {
                "ts": t0 + timedelta(seconds=3),
                "account": "0xA",
                "marketId": "m",
                "outcome": "No",
                "side": "BUY",
                "size": 8.0,
                "price": 0.6,
            },
            {
                "ts": t0,
                "account": "0xC",
                "marketId": "m",
                "outcome": "Yes",
                "side": "BUY",
                "size": 100.0,
                "price": 0.2,
            },
            {
                "ts": t0,
                "account": "0xD",
                "marketId": "m",
                "outcome": "Yes",
                "side": "BUY",
                "size": 7.0,
                "price": 0.2,
            },
        ]
    )
    path = netPath(fills, ["0xa", "0xb", "0xd"], {"0xa": "c1", "0xb": "c1"})
    yes = path.filter((pl.col("accountGroup") == "c1") & (pl.col("outcome") == "Yes"))
    assert yes["netShares"].to_list() == pytest.approx([10, 14, 11])
    no = path.filter((pl.col("accountGroup") == "c1") & (pl.col("outcome") == "No"))
    assert no["netShares"].to_list() == pytest.approx([8])
    solo = path.filter(pl.col("account") == "0xd")
    assert solo["accountGroup"].to_list() == ["0xd"]
    assert solo["netShares"].to_list() == pytest.approx([7])
    assert path.filter(pl.col("account") == "0xc").height == 0


def _walk(steps: list[tuple[int, float, float]], knobs: BacktestParams):
    burst = None
    memory = BookMemory()
    actions = []
    for offset, size, price in steps:
        burst, fillSize = observeBuy(burst, ts(offset), size, price)
        action, shares = planBuy(burst, fillSize, "g", "m", "event", memory, knobs)
        actions.append((action, shares))
        if action == "trigger":
            burst.copying = True
    return actions


def test_triggerWaitsForRunningUsdAndLaterFillsOnlyAdd() -> None:
    knobs = params(minNetUsd=50, maxEntryPrice=1)
    actions = _walk([(0, 100, 0.2), (10, 200, 0.2), (20, 50, 0.2)], knobs)
    assert actions[0][0] == "skip"
    assert actions[1] == ("trigger", 300)
    assert actions[2] == ("add", 50)


def test_priceFilterUsesRunningAverageSoFar() -> None:
    knobs = params(minNetUsd=10, maxEntryPrice=0.5)
    actions = _walk([(0, 10, 0.8), (10, 10, 0.8), (20, 40, 0.2)], knobs)
    assert actions[0][0] == "skip"
    assert actions[1][0] == "skip"
    assert actions[2] == ("trigger", 60)


def test_planBuyIgnoresFillsThatHaveNotHappenedYet() -> None:
    knobs = params(minNetUsd=50, maxEntryPrice=1)
    early = [(0, 100, 0.2), (10, 200, 0.2)]
    assert _walk(early, knobs) == _walk(early + [(30, 1000, 0.1)], knobs)[:2]


def test_burstResetsAfterTenMinutes() -> None:
    first, _size = observeBuy(None, ts(0), 10, 0.4)
    first.copying = True
    later, _size = observeBuy(first, ts(0) + timedelta(minutes=11), 4, 0.5)
    assert later.copying is False
    assert later.usd == pytest.approx(2)
    assert later.shares == pytest.approx(4)


def test_minNetUsdFilter() -> None:
    memory = BookMemory()
    knobs = params(minNetUsd=500)
    assert takeEntry(row(usd=499), memory, knobs) is False
    assert takeEntry(row(usd=500), memory, knobs) is True


def test_entryPriceFilters() -> None:
    knobs = params(maxEntryPrice=0.5, minEntryPrice=0.2)
    assert takeEntry(row(price=0.19, usd=10), BookMemory(), knobs) is False
    assert takeEntry(row(price=0.51, usd=10), BookMemory(), knobs) is False
    assert takeEntry(row(price=0.2, usd=10), BookMemory(), knobs) is True
    assert takeEntry(row(price=0.5, usd=10), BookMemory(), knobs) is True
    openPrice = params(minEntryPrice=None, maxEntryPrice=1)
    assert takeEntry(row(price=0.05, usd=10), BookMemory(), openPrice) is True


def test_largestPerEventIsPointInTime() -> None:
    memory = BookMemory()
    knobs = params(copyRule="largestPerEvent")
    assert takeEntry(row("m1", usd=100), memory, knobs) is True
    recordCopy(row("m1", usd=100), memory)
    assert takeEntry(row("m2", usd=100), memory, knobs) is False
    assert takeEntry(row("m3", usd=40), memory, knobs) is False
    assert takeEntry(row("m4", usd=150), memory, knobs) is True
    other = BookMemory()
    assert takeEntry(row("m1", usd=200), other, knobs) is True
    assert takeEntry(row("m2", usd=80), other, knobs) is False
    assert noteLargest(10, "g", "event", BookMemory()) is True


def test_largestIsPerGroup() -> None:
    memory = BookMemory()
    knobs = params(copyRule="largestPerEvent")
    first = row("m1", usd=100)
    second = row("m2", usd=50)
    second["accountGroup"] = "other"
    assert takeEntry(first, memory, knobs) is True
    assert takeEntry(second, memory, knobs) is True


def test_maxEntriesPerEventCapsNewMarkets() -> None:
    memory = BookMemory()
    knobs = params(maxEntriesPerEvent=1)
    assert takeEntry(row("m1"), memory, knobs) is True
    recordCopy(row("m1"), memory)
    assert takeEntry(row("m1", usd=20), memory, knobs) is True
    assert takeEntry(row("m2"), memory, knobs) is False
    otherEvent = row("m3", eventSlug="other")
    assert takeEntry(otherEvent, memory, knobs) is True


def test_orderSharesCapsPositionAndExposure() -> None:
    mirror = params(sizing="mirrorPct", mirrorPct=1, maxPositionUsd=100)
    assert orderShares(1000, 0.5, mirror, 0) == pytest.approx(200)
    fixed = params(sizing="fixed", fixedUsd=100, maxPositionUsd=1000)
    assert orderShares(10, 0.25, fixed, 0) == pytest.approx(400)
    room = params(sizing="fixed", fixedUsd=100, maxPositionUsd=None, maxTotalExposureUsd=100)
    assert orderShares(10, 0.5, room, 80) == pytest.approx(40)
    assert orderShares(10, 0.5, room, 100) == 0
    assert orderShares(10, None, mirror, 0) == 0
    assert orderShares(1000, 0.5, mirror, 0, positionUsd=80) == pytest.approx(40)
