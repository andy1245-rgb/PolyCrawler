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
    assert priceDedupeKeys == ["tokenId", "ts"]


def test_runFetchWritesPricesParquet(tmp_path, monkeypatch):
    """The wiring: whatever the three fetchers return lands in three parquet files."""
    monkeypatch.setattr(fetchMod, "fetchMarkets", lambda *a, **k: [market()])
    monkeypatch.setattr(fetchMod, "fetchFills", lambda *a, **k: [
        {"ts": fetchMod.parseTime(1791585433), "account": "0xa", "marketId": "0xm",
         "outcome": "Yes", "side": "BUY", "size": 10.0, "price": 0.41, "txHash": "0xdead"},
    ])
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
