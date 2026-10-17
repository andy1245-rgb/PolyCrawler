"""Tests for the paper-lane engine (research/paperLanes.md).

Everything runs on tmp dirs: the lane CSVs, the lane-3 cache file, and the
alert paths are all exercised with monkeypatched paths/helpers, never the
real data/live files. Network calls (CLOB bookSize, /activity age stamp,
Gamma refresh) are stubbed. The scripts tree is put on sys.path so the
watcher's own `import paperLanes` resolves to the SAME module object the
tests inspect (one shared CFG/HELPERS/SEEN store across both).
"""

import csv
import importlib.util
import json
import sys
import time
import uuid

SENTINEL = object()
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import paperLanes as pl


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def wr():
    return load("liveWatcher")


@pytest.fixture()
def cfg():
    return {
        "lane2": {"enabled": True, "horizonsDays": [7], "sellSlippageBps": 50},
        "lane3": {"enabled": True, "horizonsDays": [3, 7], "sellSlippageBps": 50,
                  "minUsd": 10000.0, "priceMin": 0.55, "priceMax": 0.90,
                  "maxAlertsPerDay": 3, "skipFeeMarkets": True,
                  "tags": ["politics"], "maxMarkets": 600},
    }


@pytest.fixture(autouse=True)
def _clean_module_state(wr):
    pl.setConfig(None)
    wr.LANES = None
    yield
    pl.setConfig(None)
    wr.LANES = None


@pytest.fixture()
def helpers():
    pl.configure({"fillKey": lambda row, mid:
                  f"{row['proxyWallet']}|{row['txnHash']}|{mid}",
                  "bookSize": lambda client, info, outcome, price:
                  {"bestAsk": 0.61, "askSize": 500.0, "takeableShares": 800.0},
                  "normalize": lambda raw: raw})


def readCsv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


# --- config parsing ------------------------------------------------------------

def test_missing_config_disables_all(tmp_path):
    cfg = pl.loadConfig(tmp_path / "nonexistent.yaml")
    assert cfg["lane2"]["enabled"] is False
    assert cfg["lane3"]["enabled"] is False
    assert cfg["lane2"]["horizonsDays"] == [7]
    assert cfg["lane3"]["horizonsDays"] == [3, 7]


def test_garbage_config_disables_all(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("lane2: [oops\nlane3: bxsjtd::\n  x")
    cfg = pl.loadConfig(bad)
    assert cfg["lane2"]["enabled"] is False
    assert cfg["lane3"]["enabled"] is False


def test_config_parses(tmp_path):
    good = tmp_path / "lanes.yaml"
    good.write_text(
        "lane2:\n  enabled: true\n  horizonsDays: [7]\n"
        "lane3:\n  enabled: true\n  minUsd: 25000\n  tags: [sports]\n")
    cfg = pl.loadConfig(good)
    assert cfg["lane2"]["enabled"] is True
    assert cfg["lane3"]["minUsd"] == 25000.0
    assert cfg["lane3"]["tags"] == ["sports"]
    assert cfg["lane3"]["maxAlertsPerDay"] == 3  # <=$300/day budget default


def test_horizon_garbage_falls_back(tmp_path):
    good = tmp_path / "lanes.yaml"
    good.write_text("lane2:\n  enabled: true\n  horizonsDays: [nope]\n")
    cfg = pl.loadConfig(good)
    assert cfg["lane2"]["horizonsDays"] == [7]


# --- lane-1 untouched (byte-identical baseline; lanes flat-out off) ------------

def test_watcher_rule_constants_untouched(wr):
    assert wr.RULE_MIN_USD == 5000
    assert wr.RULE_MAX_PRICE == 0.35
    assert wr.RULE_MAX_AGE_DAYS == 5
    assert wr.RULE_MAX_MARKETS == 3
    assert wr.BURST_WINDOW_SEC == 600
    assert wr.SIGNALS.name == "signals.csv"
    assert wr.STATE.name == "state.json"


def test_bank_is_additive():
    state = {"accounts": {"a": {"firstTs": 1}}, "lastTs": {"m": 2}}
    pl.bank(state)
    assert state["lane3"] == {"accounts": {}, "lastTs": {}, "alerts": [], "daily": {}}
    assert state["accounts"] == {"a": {"firstTs": 1}}
    assert state["lastTs"] == {"m": 2}
    assert pl.bank(state) is state["lane3"]


def test_disabled_lane3_hooks_do_not_write(tmp_path, cfg, helpers):
    off = {**cfg, "lane3": {**cfg["lane3"], "enabled": False}}
    pl.setConfig(off)
    state = {}
    row = {"mid": "0xm", "ts": int(time.time()), "proxyWallet": "0xw",
           "side": "BUY", "size": 20000, "price": 0.7, "outcome": "Yes",
           "txnHash": "0xt"}
    pl.onTapeRow(row, False, {"0xm": {"eventSlug": "e", "question": "q",
                                      "tokens": {}, "fees": False}},
                 state, None, root=tmp_path)
    assert "lane3" not in state
    assert not (tmp_path / "data" / "live" / "signalsLane3.csv").exists()


# --- lane-2: derive from a lane-1 alert ----------------------------------------

def test_lane2_clone_writes_identical_shape(wr, tmp_path, cfg, monkeypatch):
    pl.setConfig(cfg)
    wr.LANES = cfg
    wr.SIGNALS = tmp_path / "signals.csv"
    wr.ROOT = tmp_path
    info = {"eventSlug": "e-slug", "question": "Q?",
            "tokens": {"Yes": "tok1"}}
    monkeypatch.setattr(wr, "bookSize",
                        lambda client, info, outcome, price:
                        {"bestAsk": 0.6, "askSize": 400.0, "takeableShares": 600.0})
    wr.alert("0xw", int(time.time()), "0xm", info, {"start": 1, "usd": 12000.0},
             0.6, 0.0, 1, {"alerts": []}, None, "Yes")
    with (tmp_path / "signals.csv").open() as fh:
        header = next(csv.reader(fh))
    assert header == pl.L2_FIELDNAMES  # lane-1 CSV shape unchanged
    rows = readCsv(tmp_path / "data" / "live" / "signalsLane2.csv")
    assert len(rows) == 1
    assert rows[0]["account"] == "0xw"
    assert rows[0]["burstUsd"] == "12000.0"
    assert rows[0]["bestAsk"] == "0.6"   # same CLOB book as the lane-1 row
    assert not (REPO / "data" / "live" / "signalsLane2.csv").exists()


def test_lane2_off_writes_nothing(wr, tmp_path, cfg):
    off = {**cfg, "lane2": {**cfg["lane2"], "enabled": False}}
    pl.setConfig(off)
    wr.LANES = off
    wr.SIGNALS = tmp_path / "out.csv"
    wr.ROOT = tmp_path
    info = {"eventSlug": "e", "question": "Q?"}
    wr.alert("0xw", int(time.time()), "0xm", info, {"start": 1, "usd": 9999.0},
             0.3, 0.0, 1, {"alerts": []}, None, "Yes")
    assert not (tmp_path / "data" / "live" / "signalsLane2.csv").exists()


# --- lane-3 evaluation ---------------------------------------------------------

def lane3Row(w, ts, price=0.7, mid="0xm", outcome="Yes"):
    return {"mid": mid, "ts": ts, "proxyWallet": w, "side": "BUY",
            "size": 5000.0 / price, "price": price, "outcome": outcome,
            "txnHash": f"0x{uuid.uuid4().hex}"}


def test_lane3_fires_on_ten_k_favorite_burst(tmp_path, cfg, helpers, monkeypatch):
    pl.setConfig(cfg)
    monkeypatch.setattr(pl, "ageWindowClean", lambda *a, **k: True)
    market = {"eventSlug": "big-market", "question": "Q?", "tokens": {}, "fees": False}
    state = {}
    ts = int(time.time())
    for delta in (0, 30):
        pl.onTapeRow(lane3Row("0xw", ts + delta), False, {"0xm": market}, state,
                     None, root=tmp_path)
    rows = readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")
    assert len(rows) == 1
    assert rows[0]["burstUsd"] == "10000.0"
    assert rows[0]["avgPrice"] == "0.7"
    assert rows[0]["ageStamp"] == "verified"
    assert rows[0]["freshWindow5d"] == "True"
    assert state["lane3"]["alerts"] == [f"0xw|0xm|{ts}"]


def test_lane3_daily_cap(tmp_path, cfg, helpers, monkeypatch):
    pl.setConfig(cfg)
    monkeypatch.setattr(pl, "ageWindowClean", lambda *a, **k: None)
    market = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": False}
    state = {}
    ts = int(time.time())
    for i in range(4):  # 4 distinct $10k bursts -> cap is maxAlertsPerDay = 3
        for delta in (0, 30):
            pl.evalLane3(lane3Row(f"0xw{i}", ts + 60 * i + delta,
                                  mid=f"0xm{i}"), ts + 60 * i + delta,
                         f"0xm{i}", market, state, backfill=False, client=None,
                     root=tmp_path)
    rows = readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")
    assert len(rows) == 3
    assert all(r["ageStamp"] == "failed" for r in rows)
    assert len(state["lane3"]["alerts"]) == 3


def test_lane3_window_reset_re_fires_after_600s(tmp_path, cfg, helpers, monkeypatch):
    pl.setConfig(cfg)
    monkeypatch.setattr(pl, "ageWindowClean", lambda *a, **k: True)
    market = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": False}
    state = {}
    ts = int(time.time())
    for delta in (0, 30):
        pl.onTapeRow(lane3Row("0xw", ts + delta), False, {"0xm": market}, state,
                     None, root=tmp_path)
    assert len(readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")) == 1
    for delta in (700, 730):  # >600s: window resets, a new burst can fire
        pl.onTapeRow(lane3Row("0xw", ts + delta), False, {"0xm": market}, state,
                     None, root=tmp_path)
    rows = readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")
    assert len(rows) == 2
    assert len(state["lane3"]["alerts"]) == 2


def test_lane3_price_band_and_fees_skip(tmp_path, cfg, helpers, monkeypatch):
    pl.setConfig(cfg)
    monkeypatch.setattr(pl, "ageWindowClean", lambda *a, **k: True)
    state = {}
    ts = int(time.time())
    noFee = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": False}
    feeMkt = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": True}
    for delta in (0, 30):  # avg 0.50 < priceMin: never alerts
        pl.onTapeRow(lane3Row("0xa", ts + delta, price=0.5), False,
                     {"0xm": noFee}, state, None, root=tmp_path)
    for delta in (60, 90):  # fee market: skipped even in-band
        pl.onTapeRow(lane3Row("0xb", ts + delta, price=0.6, mid="0xfee"), False,
                     {"0xfee": feeMkt}, state, None, root=tmp_path)
    assert not (tmp_path / "data" / "live" / "signalsLane3.csv").exists()
    assert state["lane3"]["alerts"] == []


def test_lane3_poll_watermark_prevents_refetch_alerts(tmp_path, cfg, helpers,
                                                      monkeypatch):
    pl.setConfig(cfg)
    monkeypatch.setattr(pl, "ageWindowClean", lambda *a, **k: True)
    market = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": False}
    state = {}
    ts = int(time.time()) - 10

    class FakeResp:
        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, body):
            self._body = body

        def get(self, url, params=SENTINEL):
            if params is SENTINEL:
                raise TypeError('params must be passed by keyword, like httpx')
            return FakeResp(self._body)

    body = {"data": [{"condition_id": "0xm", "timestamp": ts,
                      "proxy_wallet": "0xw", "side": "BUY", "size": 20000,
                      "price": 0.7, "outcome": "Yes",
                      "transaction_hash": "0xt"}],
            "pagination": {"has_more": False, "next_cursor": None}}
    client = FakeClient(body)
    wr = load("liveWatcher")
    pl.configure({**pl.HELPERS, "normalize": wr.normalizeV2Trade})
    pl.pollLane3(client, state, {"0xm": market}, 10000.0, root=tmp_path)
    assert len(state["lane3"]["alerts"]) == 1
    assert len(readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")) == 1
    # second poll: the watermark makes the same rows un-new; no duplicate alert
    pl.pollLane3(client, state, {"0xm": market}, 10000.0, root=tmp_path)
    assert len(state["lane3"]["alerts"]) == 1
    assert len(readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")) == 1


def test_lane3_backfill_rows_marked(tmp_path, cfg, helpers, monkeypatch):
    pl.setConfig(cfg)
    monkeypatch.setattr(pl, "ageWindowClean", lambda *a, **k: True)
    market = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": False}
    state = {}
    row = {"mid": "0xm", "ts": int(time.time()), "proxyWallet": "0xw",
           "side": "BUY", "size": 20000, "price": 0.7, "outcome": "Yes",
           "txnHash": "0xt"}
    pl.evalLane3(row, row["ts"], "0xm", market, state, backfill=True,
                 client=None, root=tmp_path)
    assert state["lane3"]["accounts"]["0xw"]["backfill"] is True
    rows = readCsv(tmp_path / "data" / "live" / "signalsLane3.csv")
    assert len(rows) == 1  # backfill stamp is diagnostic, never a lane-3 gate


def test_lane3_cache_serves_without_network(tmp_path, cfg):
    pl.setConfig(cfg)
    market = {"eventSlug": "e", "question": "Q?", "tokens": {}, "fees": False}

    class Boom:
        def get(self, url, params=None):
            raise AssertionError("network must not be hit when the cache is fresh")

    cachePath = tmp_path / "data" / "live" / "eventsLane3.json"
    cachePath.parent.mkdir(parents=True)
    cachePath.write_text(json.dumps({"fetched": time.time(),
                                     "markets": {"0xm": market}}))
    out = pl.refreshLane3(Boom(), cfg["lane3"], root=tmp_path)
    assert out == {"0xm": market}
