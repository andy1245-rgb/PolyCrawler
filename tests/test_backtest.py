import json
from datetime import date, datetime, timedelta, timezone

import polars as pl
import pytest

from polycrawler.backtest import (
    BacktestParams,
    loadMarketFills,
    paramsHash,
    rollingWindows,
    runBacktest,
    runRolling,
)
from polycrawler.sweep import loadSweep, runSweep

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


def marketsFrame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def oneMarket(
    marketId: str = "m",
    eventSlug: str = "event",
    winner: str | None = "Yes",
    resolvedAt: datetime | None = None,
) -> dict:
    return {
        "marketId": marketId,
        "eventSlug": eventSlug,
        "question": marketId,
        "winner": winner,
        "resolvedAt": resolvedAt if resolvedAt is not None else ts(10**6),
        "outcomes": ["Yes", "No"],
    }


def buy(
    account: str,
    marketId: str,
    size: float,
    price: float,
    seconds: int,
    outcome: str = "Yes",
    side: str = "BUY",
) -> dict:
    return {
        "ts": ts(seconds),
        "account": account,
        "marketId": marketId,
        "outcome": outcome,
        "side": side,
        "size": size,
        "price": price,
    }


def test_resolutionSettlesAtOneOrZero() -> None:
    markets = marketsFrame(
        [
            oneMarket("win", "big", "Yes", ts(500)),
            oneMarket("lose", "small", "No", ts(800)),
        ]
    )
    fills = pl.DataFrame(
        [
            buy("0xa", "win", 10, 0.25, 0),
            buy("0xa", "lose", 10, 0.5, 10),
        ]
    )
    result = runBacktest(fills, markets, ["0xa"], params(), ts(0), ts(1000))
    byMarket = {row["marketId"]: row for row in result.trades.iter_rows(named=True)}
    assert byMarket["win"]["exitReason"] == "resolution"
    assert byMarket["win"]["pnl"] == pytest.approx(7.5)
    assert byMarket["lose"]["pnl"] == pytest.approx(-5)
    assert result.summary["totalPnl"] == pytest.approx(2.5)
    assert result.summary["capitalDeployed"] == pytest.approx(7.5)
    assert result.summary["returnOnDeployed"] == pytest.approx(2.5 / 7.5)
    assert result.summary["winRate"] == pytest.approx(0.5)
    assert result.summary["maxDrawdown"] == pytest.approx(5)
    assert result.summary["topEvent"] == "big"
    assert result.summary["pnlWithoutTopEvent"] == pytest.approx(-5)
    assert result.summary["topEventPnlShare"] == pytest.approx(7.5 / 2.5)
    assert result.summary["returnWithoutTopEvent"] == pytest.approx(-1)
    assert result.summary["medianEventReturn"] == pytest.approx(1)
    assert result.summary["eventCount"] == 2
    assert result.summary["markedCount"] == 0


def test_delayUsesTapeAfterTheBuy() -> None:
    markets = marketsFrame([oneMarket("m", "event", "Yes", ts(5000))])
    fills = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.40, 0),
            buy("0xb", "m", 1, 0.50, 45),
        ]
    )
    immediate = runBacktest(fills, markets, ["0xa"], params(delaySec=0), ts(0), ts(10**5))
    delayed = runBacktest(fills, markets, ["0xa"], params(delaySec=60), ts(0), ts(10**5))
    assert immediate.trades["entryPrice"][0] == pytest.approx(0.40)
    assert delayed.trades["entryPrice"][0] == pytest.approx(0.50)
    assert immediate.summary["totalPnl"] == pytest.approx(6)
    assert delayed.summary["totalPnl"] == pytest.approx(5)


def test_slippageRaisesTheBuy() -> None:
    markets = marketsFrame([oneMarket()])
    fills = pl.DataFrame([buy("0xa", "m", 10, 0.40, 0)])
    result = runBacktest(fills, markets, ["0xa"], params(slippageBps=50), ts(0), ts(10**6))
    assert result.trades["entryPrice"][0] == pytest.approx(0.40 * 1.005)
    assert result.trades["pnl"][0] == pytest.approx(10 * (1 - 0.40 * 1.005))


def test_followClusterExitsWhenNetFallsAndHoldDoesNot() -> None:
    markets = marketsFrame([oneMarket("m", "event", "Yes", ts(5000))])
    fills = pl.DataFrame(
        [
            buy("0xa", "m", 200, 0.40, 0),
            buy("0xa", "m", 200, 0.60, 100, side="SELL"),
        ]
    )
    followed = runBacktest(
        fills,
        markets,
        ["0xa"],
        params(minNetUsd=50, exitMode="followCluster"),
        ts(0),
        ts(10**5),
    )
    held = runBacktest(
        fills,
        markets,
        ["0xa"],
        params(minNetUsd=50, exitMode="holdToResolution"),
        ts(0),
        ts(10**5),
    )
    assert followed.trades["exitReason"][0] == "followCluster"
    assert followed.trades["exitPrice"][0] == pytest.approx(0.60)
    assert followed.summary["totalPnl"] == pytest.approx(40)
    assert held.trades["exitReason"][0] == "resolution"
    assert held.summary["totalPnl"] == pytest.approx(120)


def test_unresolvedPositionIsMarked() -> None:
    markets = marketsFrame([oneMarket("m", "event", None, None)])
    markets = markets.with_columns(
        pl.lit(None).cast(pl.String).alias("winner"),
        pl.lit(None).cast(pl.Datetime(time_unit="us", time_zone="UTC")).alias("resolvedAt"),
    )
    fills = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.40, 0),
            buy("0xb", "m", 1, 0.70, 1000),
        ]
    )
    result = runBacktest(fills, markets, ["0xa"], params(), ts(0), ts(2000))
    trade = result.trades.row(0, named=True)
    assert trade["marked"] is True
    assert trade["exitReason"] == "mark"
    assert trade["exitPrice"] == pytest.approx(0.70)
    assert trade["pnl"] == pytest.approx(3)
    assert result.summary["markedCount"] == 1
    assert result.summary["totalPnl"] == pytest.approx(3)


def test_exposureCapScalesTheNextTrade() -> None:
    markets = marketsFrame(
        [
            oneMarket("m1", "event", "Yes", ts(5000)),
            oneMarket("m2", "event", "Yes", ts(5000)),
        ]
    )
    fills = pl.DataFrame(
        [
            buy("0xa", "m1", 10, 0.5, 0),
            buy("0xa", "m2", 10, 0.5, 10),
        ]
    )
    result = runBacktest(
        fills,
        markets,
        ["0xa"],
        params(sizing="fixed", fixedUsd=100, maxPositionUsd=None, maxTotalExposureUsd=150),
        ts(0),
        ts(10**5),
    )
    usd = result.trades.sort("tradeId")["usd"].to_list()
    assert usd == pytest.approx([100, 50])
    assert result.summary["tradeCount"] == 2


def test_buysOutsideTheWindowAreIgnored() -> None:
    markets = marketsFrame([oneMarket()])
    fills = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.2, -10),
            buy("0xa", "m", 4, 0.25, 5),
        ]
    )
    result = runBacktest(fills, markets, ["0xa"], params(), ts(0), ts(100))
    assert result.summary["tradeCount"] == 1
    assert result.trades["shares"][0] == pytest.approx(4)


def test_sameInputsMatch() -> None:
    markets = marketsFrame(
        [
            oneMarket("m", "event", "Yes", ts(400)),
            oneMarket("n", "other", "No", ts(800)),
        ]
    )
    fills = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.3, 0),
            buy("0xa", "m", 5, 0.4, 20),
            buy("0xb", "m", 2, 0.35, 30),
            buy("0xa", "n", 8, 0.6, 40),
            buy("0xa", "m", 6, 0.55, 200, side="SELL"),
        ]
    )
    knobs = params(
        minNetUsd=1, maxEntryPrice=0.7, exitMode="followCluster", delaySec=30, slippageBps=50
    )
    cluster = {"0xa": "c", "0xb": "c"}
    first = runBacktest(fills, markets, ["0xA", "0xB"], knobs, ts(0), ts(1000), cluster)
    second = runBacktest(fills, markets, ["0xA", "0xB"], knobs, ts(0), ts(1000), cluster)
    assert first.paramsHash == second.paramsHash == paramsHash(knobs)
    assert first.summary == second.summary
    assert first.trades.equals(second.trades)
    again = json.dumps(first.summary, sort_keys=True)
    assert again == json.dumps(second.summary, sort_keys=True)


def test_laterFillDoesNotChangeEarlierTrades() -> None:
    markets = marketsFrame([oneMarket("m", "event", "Yes", ts(5000))])
    early = pl.DataFrame([buy("0xa", "m", 10, 0.40, 0)])
    later = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.40, 0),
            buy("0xa", "m", 1000, 0.10, 300),
        ]
    )
    knobs = params()
    first = runBacktest(early, markets, ["0xa"], knobs, ts(0), ts(10**5))
    both = runBacktest(later, markets, ["0xa"], knobs, ts(0), ts(10**5))
    assert first.summary["tradeCount"] == 1
    assert both.summary["tradeCount"] == 2
    opened = both.trades.sort("entryTs").row(0, named=True)
    original = first.trades.row(0, named=True)
    assert opened["entryTs"] == original["entryTs"] == ts(0)
    assert opened["shares"] == pytest.approx(original["shares"]) == pytest.approx(10)
    assert opened["entryPrice"] == pytest.approx(original["entryPrice"]) == pytest.approx(0.40)
    assert opened["pnl"] == pytest.approx(original["pnl"])
    added = both.trades.sort("entryTs").row(1, named=True)
    assert added["shares"] == pytest.approx(1000)
    assert added["entryPrice"] == pytest.approx(0.10)


def test_fixedSizingAddsOnlyOnANewBurst() -> None:
    markets = marketsFrame([oneMarket()])
    close = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.40, 0),
            buy("0xa", "m", 10, 0.40, 60),
        ]
    )
    gap = pl.DataFrame(
        [
            buy("0xa", "m", 10, 0.40, 0),
            buy("0xa", "m", 10, 0.40, 11 * 60),
        ]
    )
    knobs = params(sizing="fixed", fixedUsd=100)
    assert runBacktest(close, markets, ["0xa"], knobs, ts(0), ts(10**6)).summary["tradeCount"] == 1
    assert runBacktest(gap, markets, ["0xa"], knobs, ts(0), ts(10**6)).summary["tradeCount"] == 2


def test_rollingWindowsAreHalfOpenMonths() -> None:
    windows = rollingWindows(date(2026, 1, 31), date(2026, 4, 1), stepMonths=1)
    assert windows == [
        (date(2026, 1, 31), date(2026, 2, 28)),
        (date(2026, 2, 28), date(2026, 3, 28)),
        (date(2026, 3, 28), date(2026, 4, 1)),
    ]
    assert rollingWindows(date(2026, 3, 1), date(2026, 5, 1)) == [
        (date(2026, 3, 1), date(2026, 4, 1)),
        (date(2026, 4, 1), date(2026, 5, 1)),
    ]


def test_runRollingUsesOnlyThatMonthsAccounts() -> None:
    markets = marketsFrame(
        [
            oneMarket("march", "march-event", "Yes", datetime(2026, 3, 20, tzinfo=utc)),
            oneMarket("april", "april-event", "No", datetime(2026, 4, 20, tzinfo=utc)),
        ]
    )
    fills = pl.DataFrame(
        [
            {
                "ts": datetime(2026, 3, 10, tzinfo=utc),
                "account": "0xa",
                "marketId": "march",
                "outcome": "Yes",
                "side": "BUY",
                "size": 10.0,
                "price": 0.25,
            },
            {
                "ts": datetime(2026, 4, 1, tzinfo=utc),
                "account": "0xa",
                "marketId": "april",
                "outcome": "Yes",
                "side": "BUY",
                "size": 10.0,
                "price": 0.40,
            },
            {
                "ts": datetime(2026, 4, 10, tzinfo=utc),
                "account": "0xb",
                "marketId": "april",
                "outcome": "Yes",
                "side": "BUY",
                "size": 8.0,
                "price": 0.50,
            },
        ]
    )
    rolled = runRolling(
        fills,
        markets,
        {date(2026, 3, 1): {"0xa"}, date(2026, 4, 1): {"0xb"}},
        params(),
        date(2026, 3, 1),
        date(2026, 5, 1),
    )
    assert [item.summary["tradeCount"] for item in rolled.windows] == [1, 1]
    assert rolled.windows[0].trades["account"][0] == "0xa"
    assert rolled.windows[1].trades["account"][0] == "0xb"
    assert rolled.summary["tradeCount"] == 2
    assert rolled.summary["totalPnl"] == pytest.approx(
        rolled.windows[0].summary["totalPnl"] + rolled.windows[1].summary["totalPnl"]
    )


def test_loadMarketFillsDedupes(tmp_path) -> None:
    left = tmp_path / "a"
    right = tmp_path / "b"
    left.mkdir()
    right.mkdir()
    fill = {
        "ts": ts(0),
        "account": "0xa",
        "marketId": "m",
        "outcome": "Yes",
        "side": "BUY",
        "size": 1.0,
        "price": 0.4,
        "txHash": "0x1",
    }
    extra = dict(fill, txHash="0x2", price=0.5)
    pl.DataFrame([fill]).write_parquet(left / "fills.parquet")
    pl.DataFrame([fill, extra]).write_parquet(right / "fills.parquet")
    pl.DataFrame([{"marketId": "m", "question": "first"}]).write_parquet(left / "markets.parquet")
    pl.DataFrame(
        [{"marketId": "m", "question": "second"}, {"marketId": "n", "question": "other"}]
    ).write_parquet(right / "markets.parquet")
    fills, markets = loadMarketFills([left, right])
    assert fills.select(pl.len()).collect().item() == 2
    kept = markets.filter(pl.col("marketId") == "m")
    assert kept["question"].to_list() == ["first"]
    assert set(markets["marketId"].to_list()) == {"m", "n"}


def test_ineligibleSweepRanksLast() -> None:
    markets = marketsFrame(
        [
            oneMarket("m1", "big", "Yes", ts(500)),
            oneMarket("m2", "small", "Yes", ts(800)),
        ]
    )
    fills = pl.DataFrame(
        [
            buy("0xa", "m1", 10, 0.2, 0),
            buy("0xa", "m2", 10, 0.5, 10),
        ]
    )
    from polycrawler.backtest import prepareBacktest

    prepared = prepareBacktest(fills, markets, ["0xa"], ts(0), ts(1000))
    ranked = runSweep(
        prepared,
        params(),
        {"maxEntryPrice": [1, 0.3]},
        "medianEventReturn",
        minTrades=1,
        minEvents=2,
    )
    assert ranked["eventCount"].to_list() == [2, 1]
    assert ranked["eligible"].to_list() == [True, False]
    assert ranked["medianEventReturn"][0] == pytest.approx(2.5)
    assert ranked["medianEventReturn"][1] == pytest.approx(4)


def test_loadSweepDefaultsToMedianEventReturn(tmp_path) -> None:
    path = tmp_path / "sweep.yaml"
    path.write_text("grid:\n  delaySec: [0]\n")
    spec = loadSweep(path)
    assert spec.objective == "medianEventReturn"
    assert spec.minTrades == 20
    assert spec.minEvents == 3
