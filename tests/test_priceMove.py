from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from polycrawler.priceMove import (
    aggregateEntries,
    buildPriceTape,
    priceAt,
    summarizeReturns,
    tradeReturns,
)

utc = timezone.utc


def ts(seconds: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=utc) + timedelta(seconds=seconds)


def marketsFrame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def test_priceAtUsesComplementAndGoesStale() -> None:
    markets = marketsFrame(
        [
            {"marketId": "m", "outcomes": ["Yes", "No"], "question": "m", "winner": "Yes", "resolvedAt": ts(10**6)},
            {"marketId": "n", "outcomes": ["Yes", "No"], "question": "n", "winner": None, "resolvedAt": None},
        ]
    )
    fills = pl.DataFrame(
        [
            {"ts": ts(0), "marketId": "m", "outcome": "No", "price": 0.30},
            {"ts": ts(0), "marketId": "m", "outcome": "Yes", "price": 0.55},
            {"ts": ts(3600), "marketId": "m", "outcome": "Yes", "price": 0.80},
            {"ts": ts(0), "marketId": "n", "outcome": "Yes", "price": 0.10},
            {"ts": ts(0), "marketId": "m", "outcome": "Valparaiso", "price": 0.99},
        ]
    )
    tape = buildPriceTape(fills, markets)
    queries = pl.DataFrame(
        {
            "name": ["yesNow", "noNow", "yesLater", "noAtYesPrint", "yesAt6h", "yesPast6h", "otherNo", "before"],
            "marketId": ["m", "m", "m", "m", "m", "m", "n", "m"],
            "outcome": ["Yes", "No", "Yes", "No", "Yes", "Yes", "No", "Yes"],
            "ts": [
                ts(0),
                ts(0),
                ts(30 * 60),
                ts(3600),
                ts(3600 + 6 * 3600),
                ts(3600 + 6 * 3600 + 1),
                ts(0),
                ts(-1),
            ],
        }
    )
    got = {row["name"]: row["price"] for row in priceAt(tape, queries).iter_rows(named=True)}
    assert got["yesNow"] == pytest.approx(0.55)
    assert got["noNow"] == pytest.approx(0.30)
    assert got["yesLater"] == pytest.approx(0.55)
    assert got["noAtYesPrint"] == pytest.approx(0.20)
    assert got["yesAt6h"] == pytest.approx(0.80)
    assert got["yesPast6h"] is None
    assert got["otherNo"] == pytest.approx(0.90)
    assert got["before"] is None


def test_aggregateEntriesClustersBuysWithinTenMinutes() -> None:
    t0 = ts(0)
    fills = pl.DataFrame(
        [
            {"ts": t0, "account": "0xAAA", "marketId": "m", "outcome": "Yes", "side": "BUY", "size": 10.0, "price": 0.2},
            {"ts": t0 + timedelta(minutes=5), "account": "0xaaa", "marketId": "m", "outcome": "Yes", "side": "BUY", "size": 30.0, "price": 0.4},
            {"ts": t0 + timedelta(minutes=10), "account": "0xaaa", "marketId": "m", "outcome": "Yes", "side": "BUY", "size": 10.0, "price": 0.6},
            {"ts": t0 + timedelta(minutes=10, seconds=1), "account": "0xaaa", "marketId": "m", "outcome": "Yes", "side": "BUY", "size": 5.0, "price": 0.8},
            {"ts": t0 + timedelta(minutes=1), "account": "0xaaa", "marketId": "m", "outcome": "No", "side": "BUY", "size": 7.0, "price": 0.3},
            {"ts": t0 + timedelta(minutes=2), "account": "0xaaa", "marketId": "m", "outcome": "Yes", "side": "SELL", "size": 100.0, "price": 0.9},
            {"ts": t0, "account": "0xbbb", "marketId": "m", "outcome": "Yes", "side": "BUY", "size": 100.0, "price": 0.1},
        ]
    )
    entries = aggregateEntries(fills, ["0xaaa"])
    assert entries.height == 3
    yes = entries.filter(pl.col("outcome") == "Yes").sort("ts")
    assert yes.height == 2
    first = yes.row(0, named=True)
    second = yes.row(1, named=True)
    assert first["ts"] == t0
    assert first["size"] == pytest.approx(50)
    assert first["usd"] == pytest.approx(20)
    assert first["price"] == pytest.approx(0.4)
    assert second["ts"] == t0 + timedelta(minutes=10, seconds=1)
    assert second["usd"] == pytest.approx(4)
    assert second["price"] == pytest.approx(0.8)
    no = entries.filter(pl.col("outcome") == "No").row(0, named=True)
    assert no["size"] == pytest.approx(7)
    assert no["usd"] == pytest.approx(2.1)


def test_delayPricingUsesLastTradeBeforeDelayPlusSlippage() -> None:
    t0 = ts(0)
    markets = marketsFrame(
        [
            {
                "marketId": "m",
                "outcomes": ["Yes", "No"],
                "question": "q",
                "winner": "Yes",
                "resolvedAt": t0 + timedelta(days=30),
            }
        ]
    )
    fills = pl.DataFrame(
        [
            {"ts": t0, "marketId": "m", "outcome": "Yes", "price": 0.40},
            {"ts": t0 + timedelta(seconds=45), "marketId": "m", "outcome": "Yes", "price": 0.50},
        ]
    )
    tape = buildPriceTape(fills, markets)
    entries = pl.DataFrame(
        [
            {
                "entryId": 1,
                "account": "0x1",
                "marketId": "m",
                "outcome": "Yes",
                "ts": t0,
                "price": 0.40,
                "size": 25.0,
                "usd": 10.0,
            }
        ]
    )
    returns = tradeReturns(
        entries,
        tape,
        markets,
        delays=[0, 30, 60],
        horizons=[("1h", 3600), ("resolution", None)],
        slippageBps=50,
    )
    our = {}
    ret1h = {}
    for row in returns.filter(pl.col("horizon") == "1h").iter_rows(named=True):
        our[row["delaySec"]] = row["ourEntryPrice"]
        ret1h[row["delaySec"]] = row["ret"]
    assert our[0] == pytest.approx(0.40 * 1.005)
    assert our[30] == pytest.approx(0.40 * 1.005)
    assert our[60] == pytest.approx(0.50 * 1.005)
    assert ret1h[0] == pytest.approx((0.50 - our[0]) / our[0])
    assert ret1h[60] == pytest.approx((0.50 - our[60]) / our[60])
    res0 = returns.filter((pl.col("horizon") == "resolution") & (pl.col("delaySec") == 0)).row(0, named=True)
    assert res0["exitPrice"] == pytest.approx(1.0)
    assert res0["ret"] == pytest.approx((1.0 - our[0]) / our[0])


def test_resolutionReturnPaysOneOrZero() -> None:
    t0 = ts(0)
    markets = marketsFrame(
        [
            {"marketId": "m", "outcomes": ["Yes", "No"], "question": "won", "winner": "Yes", "resolvedAt": t0 + timedelta(days=1)},
            {"marketId": "mEarly", "outcomes": ["Yes", "No"], "question": "early", "winner": "Yes", "resolvedAt": t0 + timedelta(seconds=10)},
            {"marketId": "mAt", "outcomes": ["Yes", "No"], "question": "at", "winner": "Yes", "resolvedAt": t0},
            {"marketId": "mOpen", "outcomes": ["Yes", "No"], "question": "open", "winner": None, "resolvedAt": None},
        ]
    )
    fills = pl.DataFrame(
        [
            {"ts": t0, "marketId": "m", "outcome": "Yes", "price": 0.20},
            {"ts": t0, "marketId": "m", "outcome": "No", "price": 0.25},
            {"ts": t0, "marketId": "mEarly", "outcome": "Yes", "price": 0.20},
            {"ts": t0, "marketId": "mAt", "outcome": "Yes", "price": 0.20},
            {"ts": t0, "marketId": "mOpen", "outcome": "Yes", "price": 0.20},
        ]
    )
    tape = buildPriceTape(fills, markets)
    entries = pl.DataFrame(
        [
            {"entryId": 1, "account": "0x1", "marketId": "m", "outcome": "Yes", "ts": t0, "price": 0.2, "size": 1.0, "usd": 1.0},
            {"entryId": 2, "account": "0x1", "marketId": "m", "outcome": "No", "ts": t0, "price": 0.25, "size": 1.0, "usd": 1.0},
            {"entryId": 3, "account": "0x1", "marketId": "mEarly", "outcome": "Yes", "ts": t0, "price": 0.2, "size": 1.0, "usd": 1.0},
            {"entryId": 4, "account": "0x1", "marketId": "mAt", "outcome": "Yes", "ts": t0, "price": 0.2, "size": 1.0, "usd": 1.0},
            {"entryId": 5, "account": "0x1", "marketId": "mOpen", "outcome": "Yes", "ts": t0, "price": 0.2, "size": 1.0, "usd": 1.0},
        ]
    )
    returns = tradeReturns(
        entries,
        tape,
        markets,
        delays=[0, 60],
        horizons=[("resolution", None)],
        slippageBps=50,
    )

    def cell(entryId: int, delay: int) -> dict:
        return returns.filter((pl.col("entryId") == entryId) & (pl.col("delaySec") == delay)).row(0, named=True)

    win = cell(1, 0)
    assert win["ourEntryPrice"] == pytest.approx(0.20 * 1.005)
    assert win["exitPrice"] == pytest.approx(1.0)
    assert win["ret"] == pytest.approx((1.0 - win["ourEntryPrice"]) / win["ourEntryPrice"])
    lose = cell(2, 0)
    assert lose["ourEntryPrice"] == pytest.approx(0.25 * 1.005)
    assert lose["exitPrice"] == pytest.approx(0.0)
    assert lose["ret"] == pytest.approx(-1.0)
    assert cell(3, 0)["ret"] == pytest.approx(win["ret"])
    assert cell(3, 60)["ourEntryPrice"] is not None
    assert cell(3, 60)["ret"] is None
    assert cell(4, 0)["ret"] is None
    assert cell(5, 0)["ret"] is None


def test_summarizeReturnsWeightsAndInterval() -> None:
    returns = pl.DataFrame(
        {
            "delaySec": [0, 0],
            "horizon": ["resolution", "resolution"],
            "ret": [1.0, -1.0],
            "usd": [10.0, 30.0],
        }
    )
    delays = [0]
    horizons = [("resolution", None), ("1h", 3600)]
    summary = summarizeReturns(returns, delays=delays, horizons=horizons, draws=1000, seed=0)
    again = summarizeReturns(returns, delays=delays, horizons=horizons, draws=1000, seed=0)
    row = summary.filter(pl.col("horizon") == "resolution").row(0, named=True)
    assert row["n"] == 2
    assert row["meanRet"] == pytest.approx(0.0)
    assert row["medianRet"] == pytest.approx(0.0)
    assert row["winRate"] == pytest.approx(0.5)
    assert row["usdWeightedMean"] == pytest.approx(-0.5)
    assert row["ciLow"] <= 0.0 <= row["ciHigh"]
    assert summary["ciLow"].to_list() == again["ciLow"].to_list()
    empty = summary.filter(pl.col("horizon") == "1h").row(0, named=True)
    assert empty["n"] == 0
    assert empty["meanRet"] is None
