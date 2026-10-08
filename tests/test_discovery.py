import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import polars as pl

from polycrawler import discovery as discoveryMod
from polycrawler import fetch as fetchMod
from polycrawler.config import DiscoveryConfig
from polycrawler.discovery import (
    activityStats,
    aggregateBets,
    collectActivity,
    resolvedMarkets,
    scoreCandidates,
    selectBestBets,
)

utc = timezone.utc
split = date(2026, 3, 1)


def ts(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=utc)


def market(marketId: str, end: datetime | None, winner: str | None) -> dict:
    return {
        "marketId": marketId,
        "eventSlug": "event",
        "question": "q",
        "tags": ["politics"],
        "endDate": end,
        "winner": winner,
        "resolvedAt": end if winner else None,
        "volumeUsd": 1000.0,
        "clobTokenIds": [],
        "outcomes": ["Yes", "No"],
    }


def fill(
    account: str,
    marketId: str,
    outcome: str,
    side: str,
    size: float,
    price: float,
    when: datetime,
) -> dict:
    return {
        "ts": when,
        "account": account,
        "marketId": marketId,
        "outcome": outcome,
        "side": side,
        "size": size,
        "price": price,
        "txHash": "0x" + account[-4:] + outcome + side,
    }


def frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    markets = pl.DataFrame(
        [
            market("m-yes", ts(2026, 1, 31, 12), "Yes"),
            market("m-late", ts(2026, 6, 1), "Yes"),
            market("m-open", ts(2026, 1, 1), None),
            market("m-tie", ts(2026, 3, 1), "No"),
        ]
    )
    fills = pl.DataFrame(
        [
            fill("0xaaa", "m-yes", "Yes", "BUY", 100, 0.2, ts(2026, 1, 2)),
            fill("0xaaa", "m-yes", "Yes", "BUY", 50, 0.4, ts(2026, 1, 5)),
            fill("0xaaa", "m-yes", "Yes", "SELL", 80, 0.9, ts(2026, 1, 6)),
            fill("0xaaa", "m-yes", "No", "BUY", 10, 0.5, ts(2026, 1, 3)),
            fill("0xaaa", "m-yes", "Yes", "BUY", 1000, 0.1, ts(2026, 3, 2)),
            fill("0xbbb", "m-late", "Yes", "BUY", 5000, 0.1, ts(2026, 1, 2)),
            fill("0xccc", "m-open", "Yes", "BUY", 5000, 0.1, ts(2026, 1, 2)),
            fill("0xddd", "m-yes", "Yes", "BUY", 10, 0.2, ts(2026, 1, 4)),
            fill("0xeee", "m-yes", "No", "BUY", 4000, 0.3, ts(2026, 1, 8)),
        ]
    )
    return markets, fills


def testAggregateBetsSumsBuysAndIgnoresSells() -> None:
    markets, fills = frames()
    bets = aggregateBets(fills, markets, split)
    yes = bets.filter(
        (pl.col("account") == "0xaaa")
        & (pl.col("marketId") == "m-yes")
        & (pl.col("outcome") == "Yes")
    )
    assert yes.height == 1
    row = yes.row(0, named=True)
    assert row["buyShares"] == 150
    assert row["buyUsd"] == 100 * 0.2 + 50 * 0.4
    assert row["avgBuyPrice"] == row["buyUsd"] / 150
    assert row["firstBuyTs"] == ts(2026, 1, 2)
    assert row["won"] is True
    no = bets.filter((pl.col("account") == "0xaaa") & (pl.col("outcome") == "No"))
    assert no.height == 1
    assert no.row(0, named=True)["won"] is False


def testResolvedAtBeatsGroupEndDate() -> None:
    grouped = market("m-grouped", ts(2026, 12, 31), "No")
    grouped["resolvedAt"] = ts(2026, 1, 9)
    resolved = resolvedMarkets(pl.DataFrame([grouped]), split)
    assert resolved["marketId"].to_list() == ["m-grouped"]


def testPointInTimeDropsFutureFillsAndUnresolvedMarkets() -> None:
    markets, fills = frames()
    bets = aggregateBets(fills, markets, split)
    accounts = set(bets["account"].to_list())
    assert "0xbbb" not in accounts
    assert "0xccc" not in accounts
    assert bets.filter(pl.col("firstBuyTs") >= datetime(2026, 3, 1, tzinfo=utc)).height == 0
    lateMarket = markets.filter(pl.col("marketId") == "m-tie")
    assert lateMarket.row(0, named=True)["endDate"] == ts(2026, 3, 1)
    assert "m-tie" not in set(bets["marketId"].to_list())
    assert "m-late" not in set(bets["marketId"].to_list())
    assert "m-open" not in set(bets["marketId"].to_list())


def testBestBetIsLargestWinningBuyAndSignalsUseActivity() -> None:
    markets, fills = frames()
    markets = pl.concat(
        [markets, pl.DataFrame([market("m-other", ts(2026, 2, 1), "Yes")])],
        how="diagonal_relaxed",
    )
    fills = pl.concat(
        [
            fills,
            pl.DataFrame([fill("0xaaa", "m-other", "Yes", "BUY", 10000, 0.5, ts(2026, 1, 20))]),
        ],
        how="diagonal_relaxed",
    )
    bets = aggregateBets(fills, markets, split)
    best = selectBestBets(bets, minBetUsd=1000)
    chosen = best.filter(pl.col("account") == "0xaaa").row(0, named=True)
    assert chosen["marketId"] == "m-other"
    assert chosen["buyUsd"] == 5000.0
    activity = pl.DataFrame(
        {
            "account": ["0xaaa", "0xeee"],
            "firstTradeTs": [ts(2026, 1, 10), ts(2025, 1, 1)],
            "marketsTraded": [3, 40],
        }
    ).with_columns(pl.col("firstTradeTs").cast(pl.Datetime("us", "UTC")))
    scored = scoreCandidates(
        best,
        activity,
        DiscoveryConfig(
            maxAccountAgeDays=14,
            maxMarketsTraded=5,
            maxBuyPrice=0.3,
            minBetUsd=1000,
            minSignals=4,
        ),
    )
    aaa = scored.filter(pl.col("account") == "0xaaa").row(0, named=True)
    assert aaa["bestMarketId"] == "m-other"
    assert aaa["isNew"] is True
    assert aaa["isFocused"] is True
    assert aaa["isLongshot"] is False
    assert aaa["isBig"] is True
    assert aaa["signalCount"] == 3
    assert aaa["suspicious"] is False
    assert aaa["profitUsd"] == 10000.0 - 5000.0
    eee = scored.filter(pl.col("account") == "0xeee")
    assert eee.height == 0


def testActivityFixtureIgnoresRedeemsAndTradesAfterSplit() -> None:
    rows = json.loads((Path(__file__).parent / "fixtures" / "activity.json").read_text())
    first, marketsTraded = activityStats(rows, date(2026, 1, 1))
    assert first == datetime.fromtimestamp(1000, tz=utc)
    assert marketsTraded == 2


def activityHandler(
    pool: list[int],
    pageSize: int,
    markets: dict[int, str] | None = None,
):
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(params)
        assert params["type"] == "TRADE"
        assert params["sortDirection"] == "ASC"
        offset = int(params.get("offset", "0"))
        end = params.get("end")
        start = params.get("start")
        stamps = list(pool)
        if end is not None:
            stamps = [stamp for stamp in stamps if stamp <= int(end)]
        if start is not None:
            stamps = [stamp for stamp in stamps if stamp >= int(start)]
        page = stamps[offset : offset + pageSize]
        rows = [
            {
                "type": "TRADE",
                "timestamp": stamp,
                "conditionId": (markets[stamp] if markets else "0xabc"),
                "side": "BUY",
                "size": 1,
                "outcome": "Yes",
                "transactionHash": f"0x{stamp}",
            }
            for stamp in page
        ]
        return httpx.Response(200, json=rows)

    return seen, handler


def testActivityWalksForwardWhenOffsetWindowIsFull(monkeypatch) -> None:
    monkeypatch.setattr(discoveryMod, "activityPageLimit", 2)
    monkeypatch.setattr(discoveryMod, "activityMaxOffset", 2)
    monkeypatch.setattr(fetchMod, "requestSleepSec", 0)
    seen, handler = activityHandler([1, 2, 3, 4, 5], 2)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = collectActivity(client, "0xabc", end=None, marketStop=30)
    assert sorted(int(row["timestamp"]) for row in rows) == [1, 2, 3, 4, 5]
    assert any(params.get("start") == "4" for params in seen)
    assert all(int(params["offset"]) <= 2 for params in seen)


def testActivityStopsOnceMarketCapIsExceeded(monkeypatch) -> None:
    monkeypatch.setattr(discoveryMod, "activityPageLimit", 2)
    monkeypatch.setattr(discoveryMod, "activityMaxOffset", 2)
    monkeypatch.setattr(fetchMod, "requestSleepSec", 0)
    markets = {stamp: f"0x{stamp}" for stamp in range(1, 9)}
    seen, handler = activityHandler(list(range(1, 9)), 2, markets)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = collectActivity(client, "0xabc", end=None, marketStop=3)
    assert len({row["conditionId"] for row in rows}) > 3
    assert len(seen) < 4
