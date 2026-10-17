"""Tests for the execution-fill stamping sweep (research/executionStamps.md).

Covers the pre-registered conventions: idempotent append-once keys
(lane, horizon, alertTs, account, eventSlug), T+300s/T+600s due windows, the
missReason enum, the $100-takeable fill predicate, fail-soft behavior on
missing inputs, and the mocked-transport book contract (httpx params is
keyword-only — the paperLanes.md R14 lesson). All file activity happens on
tmp roots; the watcher's own data files are never touched.
"""

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bookExecStamps as bes


@pytest.fixture(autouse=True)
def fastRetries(monkeypatch):
    monkeypatch.setattr(bes.time, "sleep", lambda s: None)


SIG_FIELDS = ["alertTs", "account", "eventSlug", "question", "marketId",
              "outcome", "burstUsd", "avgPrice", "ageDays", "marketsSeen",
              "bestAsk", "askSize", "takeableShares"]
CLOB = "clob.polymarket.com"
GAMMA = "gamma-api.polymarket.com"


def signalRow(mid="0xmm", account="0xw", outcome="Yes", bestAsk="0.60",
              alertTs="2026-10-01 12:00:00"):
    return {"alertTs": alertTs, "account": account, "eventSlug": "fav",
            "question": "Q?", "marketId": mid, "outcome": outcome,
            "burstUsd": "12000.0", "avgPrice": "0.60", "ageDays": "0.0",
            "marketsSeen": "1", "bestAsk": bestAsk, "askSize": "500",
            "takeableShares": "0"}


def writeCsv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def addCache(root, lane, tokens):
    events = {mid: {"tokens": tok} for mid, tok in tokens.items()}
    (root / "data" / "live" / bes.EVENTS_CACHE[lane]).write_text(
        json.dumps({"fetched": 0.0, "markets": events}))


def readStamps(root):
    path = root / "data" / "live" / "execStamps.csv"
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def okClient():
    def handler(request):
        if GAMMA in request.url.host:
            mid = request.url.params["condition_ids"]
            closed = mid == "0xclosed"
            return httpx.Response(200, json=[{"closed": closed, "active": not closed}])
        if "last-trade-price" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={"asks": [{"price": "0.61", "size": "300"}],
                                         "bids": [{"price": "0.59", "size": "200"}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def testIdempotency(tmp_path):
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    addCache(root, "lane1", {"0xmm": {"Yes": "111"}})
    writeCsv(root / "data" / "live" / "signals.csv", SIG_FIELDS,
             [signalRow(alertTs="2026-10-01 12:00:00")])
    now = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)
    run1 = bes.runDue(root, okClient(), now=now)
    assert run1["stamped"]["lane1"] == 2
    first = (root / "data" / "live" / "execStamps.csv").read_text()
    run2 = bes.runDue(root, okClient(), now=now)
    assert run2["stamped"]["lane1"] == 0 and run2["apiLeft"] == 0
    assert (root / "data" / "live" / "execStamps.csv").read_text() == first


def testDueSelectionWindowsBothHorizons(tmp_path):
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    addCache(root, "lane2", {"0xmm": {"Yes": "111"}})
    writeCsv(root / "data" / "live" / "signalsLane2.csv", SIG_FIELDS, [
        signalRow(account="0xf", alertTs="2026-10-01 12:06:00"),  # fresh: nothing due
        signalRow(account="0xa", alertTs="2026-10-01 12:05:30"),  # h300 only
        signalRow(account="0xw", alertTs="2026-10-01 12:00:00"),  # both horizons
    ])
    now = datetime(2026, 10, 1, 12, 10, 40, tzinfo=UTC)
    run1 = bes.runDue(root, okClient(), now=now)
    assert run1["stamped"]["lane2"] == 3
    rows = readStamps(root)
    assert sorted((r["account"], r["horizon"]) for r in rows) == [
        ("0xa", "300"), ("0xw", "300"), ("0xw", "600")]
    assert {int(r["stampDrivenS"]) for r in rows} == {10, 40, 340}
    run2 = bes.runDue(root, okClient(), now=datetime(2026, 10, 1, 12, 17, tzinfo=UTC))
    assert run2["stamped"]["lane2"] == 3
    assert len(readStamps(root)) == 6


def testMissReasonCoverageAndTakeablePredicate(tmp_path):
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    addCache(root, "lane3", {"0xmm": {"Yes": "111"}, "0xbidonly": {"Yes": "222"},
                             "0xclosed": {"Yes": "333"}, "0xdead": {"Yes": "444"},
                             "0xrunaway": {"Yes": "555"}})
    writeCsv(root / "data" / "live" / "signalsLane3.csv", SIG_FIELDS, [
        signalRow(mid="0xmm", account="0x1", bestAsk="0.62"),       # ok
        signalRow(mid="0xbidonly", account="0x2"),                  # no asks, bids
        signalRow(mid="0xclosed", account="0x3", bestAsk="0.62"),   # resolved market
        signalRow(mid="0xdead", account="0x4", bestAsk="0.62"),     # no quotes, open
        signalRow(mid="0xrunaway", account="0x5", bestAsk="0.62"),  # over the floor
    ])

    def handler(request):
        if GAMMA in request.url.host:
            mid = request.url.params["condition_ids"]
            closed = mid == "0xclosed"
            return httpx.Response(200, json=[{"closed": closed, "active": not closed}])
        if "last-trade-price" in request.url.path:
            return httpx.Response(404)
        token = request.url.params["token_id"]
        if token == "444" or token == "333":
            return httpx.Response(200, json={"asks": [], "bids": []})
        if token == "222":
            return httpx.Response(200, json={"asks": [],
                                             "bids": [{"price": "0.58", "size": "900"}]})
        if token == "555":
            return httpx.Response(200, json={"asks": [{"price": "0.95", "size": "500"}],
                                             "bids": [{"price": "0.58", "size": "900"}]})
        return httpx.Response(200, json={"asks": [{"price": "0.61", "size": "500"},
                                                  {"price": "0.75", "size": "400"}],
                                         "bids": [{"price": "0.58", "size": "900"}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    bes.runDue(root, client, now=datetime(2026, 10, 1, 12, 10, tzinfo=UTC))
    st = {(r["account"], r["horizon"]): r for r in readStamps(root) if r["horizon"] == "300"}
    ok = st[("0x1", "300")]
    assert ok["missReason"] == "ok" and ok["fill100"] == "True"
    assert float(ok["takeableUsd150"]) == pytest.approx(0.61 * 500 + 0.75 * 400)
    assert float(ok["takeableUsd0"]) == pytest.approx(0.61 * 500)
    assert ok["askNow"] == "0.61" and ok["bidNow"] == "0.58" and float(ok["askSize"]) == 500
    assert float(ok["spreadPct"]) == round((0.61 - 0.58) / 0.61 * 100, 2)
    assert st[("0x2", "300")]["missReason"] == "book-empty"
    dead = st[("0x4", "300")]
    assert dead["missReason"] == "dead-market" and dead["suspect"] == "no-prints-never"
    assert dead["fill100"] == "False"
    over = st[("0x5", "300")]
    assert over["missReason"] == "ask-gt-1.5x" and over["fill100"] == "False"
    assert float(over["takeableUsd150"]) == 0.0 and over["askNow"] == "0.95"
    assert st[("0x3", "300")]["missReason"] == "book-closed"


def testFillBelow100IsNotFillable(tmp_path):
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    addCache(root, "lane1", {"0xmm": {"Yes": "111"}})
    writeCsv(root / "data" / "live" / "signals.csv", SIG_FIELDS,
             [signalRow(alertTs="2026-10-01 12:00:00")])

    def handler(request):
        return httpx.Response(200, json={"asks": [{"price": "0.61", "size": "60"}],
                                         "bids": [{"price": "0.58", "size": "900"}]})
    bes.runDue(root, httpx.Client(transport=httpx.MockTransport(handler)),
               now=datetime(2026, 10, 1, 12, 10, tzinfo=UTC))
    row = readStamps(root)[0]
    assert row["missReason"] == "ok" and row["fill100"] == "False"
    assert float(row["takeableUsd150"]) == pytest.approx(0.61 * 60)


def testFailSoftOnMissingInputs(tmp_path):
    root = tmp_path
    run = bes.runDue(root, httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200))))
    assert run["stamped"] == {"lane1": 0, "lane2": 0, "lane3": 0}
    assert run["apiLeft"] == 0 and not (root / "data" / "live" / "execStamps.csv").exists()
    # a corrupt signals file also fails soft (retry-once path)
    (root / "data" / "live").mkdir(parents=True)
    (root / "data" / "live" / "signals.csv").write_text("<html>502</html>")
    (root / "data" / "live" / "events.json").write_text(json.dumps({"fetched": 0.0}))
    run2 = bes.runDue(root, httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200))))
    assert run2["stamped"]["lane1"] == 0


def testGammaFallbackWhenCacheMissesTheToken(tmp_path):
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    writeCsv(root / "data" / "live" / "signals.csv", SIG_FIELDS,
             [signalRow(alertTs="2026-10-01 12:00:00")])

    def handler(request):
        if GAMMA in request.url.host:
            return httpx.Response(200, json=[{"clobTokenIds": json.dumps(["111", "222"]),
                                              "outcomes": json.dumps(["Yes", "No"]),
                                              "closed": False, "active": True}])
        return httpx.Response(200, json={"asks": [{"price": "0.62", "size": "400"}],
                                         "bids": [{"price": "0.58", "size": "900"}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    bes.runDue(root, client, now=datetime(2026, 10, 1, 12, 10, tzinfo=UTC))
    row = readStamps(root)[0]
    assert row["missReason"] == "ok" and row["tokenId"] == "111" and row["fill100"] == "True"


def testApiErrorGraceThenTerminalStamp(tmp_path):
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    addCache(root, "lane2", {"0xmm": {"Yes": "111"}})
    writeCsv(root / "data" / "live" / "signalsLane2.csv", SIG_FIELDS, [
        signalRow(mid="0xmm", alertTs="2026-10-01 12:04:00"),   # 60s past h300, in grace
        signalRow(mid="0xmm", account="0xa",
                  alertTs="2026-09-30 09:00:00"),               # deep past grace
    ])

    def handler(request):
        raise httpx.ConnectError("server disconnected without sending a response")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    run = bes.runDue(root, client, now=datetime(2026, 10, 1, 12, 10, tzinfo=UTC))
    assert run["apiLeft"] == 1
    rows = [r for r in readStamps(root) if r["account"] == "0w" or True]
    assert [r for r in rows if r["account"] == "0xw"] == []          # grace: no row
    old = [r for r in readStamps(root) if r["account"] == "0xa"]
    assert [r["horizon"] for r in old] == ["300", "600"]
    assert all(r["missReason"] == "api-error" and r["fill100"] == "False" for r in old)


def testRunCapLeavesRestForNextTick(tmp_path, monkeypatch):
    monkeypatch.setattr(bes, "CAP_PER_RUN", 2)
    root = tmp_path
    (root / "data" / "live").mkdir(parents=True)
    addCache(root, "lane1", {"0xmm": {"Yes": "111"}})
    writeCsv(root / "data" / "live" / "signals.csv", SIG_FIELDS, [
        signalRow(account=f"0x{i}", alertTs="2026-10-01 12:00:00") for i in range(3)])
    now = datetime(2026, 10, 1, 12, 10, tzinfo=UTC)
    run1 = bes.runDue(root, okClient(), now=now)
    assert run1["capped"] is True and run1["stamped"]["lane1"] == 2
    assert len(readStamps(root)) == 2
    run2, run3 = [bes.runDue(root, okClient(), now=now) for _ in range(2)]
    assert run2["capped"] is True and run2["stamped"]["lane1"] == 2
    assert run3 is not None
    final = bes.runDue(root, okClient(), now=now)
    assert final["capped"] is False and final["stamped"]["lane1"] == 0
    keySet = {(r["account"], r["horizon"]) for r in readStamps(root)}
    assert keySet == {(f"0x{i}", str(h)) for i in range(3) for h in (300, 600)}
