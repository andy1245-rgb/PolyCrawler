"""Tests for the CLOB price-history fetch (`data/prices.parquet`).

The point of this table is coverage: a market with no trade print inside the
staleness window still has a quote. It is fetched per outcome token, cached under
data/raw/prices/, and never touched by discovery.
"""

import json

import httpx
import polars as pl
import pytest

from polycrawler import fetch as fetchMod
from polycrawler.fetch import (
    fetchPrices,
    normalizePriceHistory,
    priceDedupeKeys,
    priceHistorySchema,
    runFetch,
)

HISTORY = {
    "history": [
        {"t": 1791585433, "p": 0.41},
        {"t": 1791585500, "p": 0.39},
        {"t": 1791585600, "p": 1.5},   # out of range: dropped
        {"t": 1791585601},             # no price: dropped
        {"t": "notatime", "p": 0.5},   # unparsable: dropped
    ]
}


def market(marketId="0xm", outcomes=("Yes", "No"), tokens=("tokY", "tokN")):
    return {"marketId": marketId, "outcomes": list(outcomes),
            "clobTokenIds": list(tokens)}


def noWaitSession(monkeypatch):
    """A session whose retry backoff does not actually sleep."""
    from polycrawler.http import HttpSession

    def build(client):
        return HttpSession(client=client, defaultRate=0.0,
                           sleep=lambda _seconds: None, clock=lambda: 0.0)

    monkeypatch.setattr(fetchMod, "sessionFor", build)


def test_fetchPricesRequestsOnePerTokenAndKeepsBothOutcomes(tmp_path, monkeypatch):
    monkeypatch.setattr(fetchMod, "requestSleepSec", 0)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params)["market"])
        return httpx.Response(200, json=HISTORY)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = fetchPrices([market()], str(tmp_path), refresh=False, client=client)

    assert sorted(seen) == ["tokN", "tokY"]
    assert len(rows) == 2 * 2  # two usable points per token
    assert {row["outcome"] for row in rows} == {"Yes", "No"}
    assert {row["marketId"] for row in rows} == {"0xm"}
    assert all(0.0 <= row["price"] <= 1.0 for row in rows)
    assert all(row["ts"].tzinfo is not None for row in rows)


def test_fetchPricesCachesPerTokenAndServesWithoutNetwork(tmp_path, monkeypatch):
    monkeypatch.setattr(fetchMod, "requestSleepSec", 0)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params)["market"])
        return httpx.Response(200, json=HISTORY)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetchPrices([market()], str(tmp_path), refresh=False, client=client)
    assert (tmp_path / "raw" / "prices" / "tokY.json").exists()
    assert json.loads((tmp_path / "raw" / "prices" / "tokY.json").read_text()) == HISTORY

    again = fetchPrices([market()], str(tmp_path), refresh=False, client=client)
    assert len(again) == 4
    assert sorted(calls) == ["tokN", "tokY"]  # second pass hit the cache


def test_oneBadTokenDoesNotCostTheOtherTokens(tmp_path, monkeypatch, capsys):
    """Prices enrich the fill fetch, so one delisted token or one 429 must not raise
    out of fetchPrices and take the other tokens with it."""
    noWaitSession(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if dict(request.url.params)["market"] == "tokN":
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=HISTORY)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = fetchPrices([market()], str(tmp_path), refresh=False, client=client)
    assert len(rows) == 2                      # tokY still priced
    assert {row["outcome"] for row in rows} == {"Yes"}
    assert "1 of 2 tokens returned no history" in capsys.readouterr().out


def test_nonJsonBodyIsTreatedAsNoHistory(tmp_path, monkeypatch, capsys):
    noWaitSession(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>rate limited</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetchPrices([market()], str(tmp_path), refresh=False, client=client) == []
    assert "2 of 2 tokens returned no history" in capsys.readouterr().out


def test_fetchPricesSkipsMarketsWithNoToken(tmp_path, monkeypatch):
    monkeypatch.setattr(fetchMod, "requestSleepSec", 0)
    assert fetchPrices([{"marketId": "0xm", "outcomes": ["Yes"], "clobTokenIds": []}],
                       str(tmp_path), refresh=False, client=None) == []
    assert fetchPrices([], str(tmp_path), refresh=False, client=None) == []


@pytest.mark.parametrize("payload", [None, {}, {"history": None}, {"history": "nope"},
                                     {"history": [7, None, {"t": 1}]}])
def test_normalizePriceHistoryIgnoresMalformedPayloads(payload):
    assert normalizePriceHistory(payload, "0xm", "Yes", "tok") == []


def test_priceHistoryRowsMatchTheSchema():
    rows = normalizePriceHistory(HISTORY, "0xm", "Yes", "tokY")
    frame = pl.DataFrame(rows, schema=priceHistorySchema)
    assert frame.columns == list(priceHistorySchema)
    assert frame.height == 2
    # keyed on what priceAt joins on, so a token under two market labels
    # cannot lose one of them
    assert priceDedupeKeys == ["marketId", "outcome", "ts"]


def fillsRow():
    return {"ts": fetchMod.parseTime(1791585433), "account": "0xa", "marketId": "0xm",
            "outcome": "Yes", "side": "BUY", "size": 10.0, "price": 0.41,
            "txHash": "0xdead"}


def test_runFetchWritesPricesParquet(tmp_path, monkeypatch):
    """The wiring: whatever the three fetchers return lands in three parquet files."""
    monkeypatch.setattr(fetchMod, "fetchMarkets", lambda *a, **k: [market()])
    monkeypatch.setattr(fetchMod, "fetchFills", lambda *a, **k: [fillsRow()])
    monkeypatch.setattr(fetchMod, "fetchPrices",
                        lambda *a, **k: normalizePriceHistory(HISTORY, "0xm", "Yes", "tokY"))
    config = fetchMod.Config.model_validate({"fetch": {"dataDir": str(tmp_path)}})
    summary = runFetch(config, eventSlugs=["e"], refresh=False)
    assert summary.prices == 2
    assert (tmp_path / "prices.parquet").exists()
    assert pl.read_parquet(tmp_path / "prices.parquet").height == 2
    assert pl.read_parquet(tmp_path / "markets.parquet").height == 1
    assert pl.read_parquet(tmp_path / "fills.parquet").height == 1


def test_runFetchCanSkipPrices(tmp_path, monkeypatch):
    monkeypatch.setattr(fetchMod, "fetchMarkets", lambda *a, **k: [market()])
    monkeypatch.setattr(fetchMod, "fetchFills", lambda *a, **k: [])
    monkeypatch.setattr(fetchMod, "fetchPrices",
                        lambda *a, **k: pytest.fail("prices should not be fetched"))
    config = fetchMod.Config.model_validate({"fetch": {"dataDir": str(tmp_path)}})
    summary = runFetch(config, eventSlugs=["e"], refresh=False, prices=False)
    assert summary.prices == 0
    assert not (tmp_path / "prices.parquet").exists()


def test_allTokensFailingYieldsNoRowsAndAWarning(tmp_path, monkeypatch, capsys):
    """Each token failure is caught at its own boundary, so a total outage of the
    price endpoint degrades to no quotes rather than an exception."""
    noWaitSession(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("clob down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetchPrices([market()], str(tmp_path), refresh=False, client=client) == []
    assert "2 of 2 tokens returned no history" in capsys.readouterr().out


def test_noQuotesStillWritesMarketsAndFills(tmp_path, monkeypatch):
    """Prices are enrichment: an empty price result leaves the other two tables
    exactly as they would have been."""
    monkeypatch.setattr(fetchMod, "fetchMarkets", lambda *a, **k: [market()])
    monkeypatch.setattr(fetchMod, "fetchFills", lambda *a, **k: [fillsRow()])
    monkeypatch.setattr(fetchMod, "fetchPrices", lambda *a, **k: [])
    config = fetchMod.Config.model_validate({"fetch": {"dataDir": str(tmp_path)}})
    summary = runFetch(config, eventSlugs=["e"], refresh=False)
    assert summary.prices == 0
    assert pl.read_parquet(tmp_path / "markets.parquet").height == 1
    assert pl.read_parquet(tmp_path / "fills.parquet").height == 1
    assert not (tmp_path / "prices.parquet").exists()
