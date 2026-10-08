import json

import httpx

from polycrawler import fetch as fetchMod
from polycrawler.fetch import fetchFills


def testWalksBackwardWhenOffsetWindowIsFull(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetchMod, "tradePageLimit", 2)
    monkeypatch.setattr(fetchMod, "tradeMaxOffset", 2)
    monkeypatch.setattr(fetchMod, "requestSleepSec", 0)
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(params)
        assert params["takerOnly"] == "false"
        offset = int(params.get("offset", "0"))
        end = params.get("end")
        pool = [5, 4, 3, 2, 1]
        if end is not None:
            pool = [ts for ts in pool if ts <= int(end)]
        page = pool[offset : offset + 2]
        rows = [
            {
                "proxyWallet": "0xABC",
                "side": "BUY",
                "conditionId": "0xabc",
                "size": 1,
                "price": 0.5,
                "timestamp": ts,
                "outcome": "Yes",
                "transactionHash": f"0x{ts:02x}",
            }
            for ts in page
        ]
        return httpx.Response(200, json=rows)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fills = fetchFills(["0xabc"], str(tmp_path), refresh=False, client=client)
    assert sorted(int(row["ts"].timestamp()) for row in fills) == [1, 2, 3, 4, 5]
    assert fills[0]["account"] == "0xabc"
    assert any(params.get("end") == "2" for params in seen)
    assert all(int(params["offset"]) <= 2 for params in seen)
    cached = json.loads((tmp_path / "raw" / "trades" / "0xabc.json").read_text())
    assert len(cached) >= 5
