import json
import threading
import time

import httpx

from polycrawler.fetch import decodeTransferLog, transferLogFilter
from polycrawler.http import (
    HostLimiter,
    HttpSession,
    JsonRequest,
    cachePath,
    rateLimitMessage,
    redactSecrets,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def testCachePathKeepsExistingLayout(tmp_path) -> None:
    path = cachePath(str(tmp_path), "etherscan", "tokentx_0xabc_page-1")
    assert path == tmp_path / "raw" / "etherscan" / "tokentx_0xabc_page-1.json"


def testLimiterSpacesStartsAndPenalizeWidensTheGap() -> None:
    clock = FakeClock()
    limiter = HostLimiter(2.0, clock.time, clock.sleep)
    limiter.acquire()
    limiter.acquire()
    assert clock.now == 0.5
    limiter.penalize()
    assert limiter.interval == 1.0
    limiter.acquire()
    assert clock.now == 1.5
    limited = HostLimiter(1.0, clock.time, clock.sleep)
    limited.penalize()
    limited.penalize()
    assert limited.interval == 4.0
    limited.relax()
    assert limited.interval == 2.5


def testRetriesRateLimitBodyAndSkipsDeprecationNote() -> None:
    clock = FakeClock()
    seen = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        if seen["calls"] == 1:
            return httpx.Response(200, json={"message": "You reached the rate limit for GET /requests/v2"})
        return httpx.Response(
            200,
            json={
                "requests": [],
                "deprecation": {"message": "reduces the v2 rate limit"},
            },
        )

    session = HttpSession(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock.time,
        sleep=clock.sleep,
        rng=lambda: 0.0,
        maxAttempts=4,
    )
    payload = session.getJson("https://api.relay.link/requests/v2", {"hash": "0xabc"})
    assert payload["requests"] == []
    assert seen["calls"] == 2
    assert clock.now == 0.5
    assert session.stats.rateLimits["api.relay.link"] == 1
    assert session.stats.calls["api.relay.link"] == 2


def testHttp429ThenSuccess() -> None:
    clock = FakeClock()
    seen = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"] += 1
        if seen["calls"] == 1:
            return httpx.Response(429, json={"message": "You reached the rate limit"})
        return httpx.Response(200, json={"ok": True})

    session = HttpSession(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        hostRates={"example.com": 0},
        clock=clock.time,
        sleep=clock.sleep,
        rng=lambda: 0.0,
    )
    assert session.getJson("https://example.com/x") == {"ok": True}
    assert seen["calls"] == 2


def testFetchManyOverlapsAndCacheSkipsTheNetwork(tmp_path) -> None:
    state = {"inFlight": 0, "maxInFlight": 0}
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            state["inFlight"] += 1
            state["maxInFlight"] = max(state["maxInFlight"], state["inFlight"])
        time.sleep(0.05)
        with lock:
            state["inFlight"] -= 1
        return httpx.Response(200, json={"q": request.url.params["q"]})

    session = HttpSession(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        dataDir=str(tmp_path),
    )
    requests = [JsonRequest("https://example.com/i", {"q": str(i)}, "relay", f"q{i}") for i in range(4)]
    first = session.fetchMany(requests, maxWorkers=4)
    assert [row["q"] for row in first] == ["0", "1", "2", "3"]
    assert state["maxInFlight"] > 1
    second = session.fetchMany(requests, maxWorkers=4)
    assert second == first
    assert session.stats.calls["example.com"] == 4
    assert session.stats.cacheHits["example.com"] == 4
    cached = json.loads((tmp_path / "raw" / "relay" / "q0.json").read_text())
    assert cached == {"q": "0"}


def testRedactStripsKeys() -> None:
    text = redactSecrets("https://polygon-mainnet.g.alchemy.com/v2/secretkey https://api.etherscan.io/v2/api?apikey=secretkey")
    assert "secretkey" not in text
    assert rateLimitMessage({"result": [{"ok": 1}], "message": "Max rate limit reached"}) is False
    assert rateLimitMessage({"message": "NOTOK", "result": "Max rate limit reached"}) is True


def testTransferLogFilterOrsRecipients() -> None:
    filt = transferLogFilter("0xAbC", ["0x" + "11" * 20, "0x" + "22" * 20], 5, 9)
    assert filt["fromBlock"] == hex(5)
    assert filt["topics"][1] is None
    assert len(filt["topics"][2]) == 2
    assert filt["topics"][2][0].endswith("11" * 20)
    log = {
        "address": "0xabc",
        "topics": [
            filt["topics"][0],
            "0x" + "00" * 12 + "aa" * 20,
            "0x" + "00" * 12 + "11" * 20,
        ],
        "data": hex(2_500_000),
        "transactionHash": "0xFF",
        "blockNumber": hex(9),
    }
    parsed = decodeTransferLog(log)
    assert parsed is not None
    assert parsed["toAddr"] == "0x" + "11" * 20
    assert parsed["amountUsd"] == 2.5
    assert parsed["txHash"] == "0xff"
    assert parsed["block"] == 9
