"""Tests for the live-tape ingestion: RTDS payload normalization, /v2/trades
row normalization, and the shared fill dedup. The scripts are imported by
path (they are not a package)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def watcher():
    return load("liveWatcher")


@pytest.fixture(scope="module")
def tape():
    return load("rtdsTape")


def test_rtds_normalize_seconds_and_fields(tape):
    msg = {"topic": "activity", "type": "trades", "timestamp": 1791585433000,
           "payload": {"conditionId": "0xabc", "proxyWallet": "0xWALLET",
                       "side": "BUY", "size": 100, "price": 0.2,
                       "outcome": "Yes", "transactionHash": "0xdead",
                       "eventSlug": "evt", "timestamp": 1791585433}}
    row = tape.RtdsTape._normalize(None, msg)
    assert row["mid"] == "0xabc"
    assert row["ts"] == 1791585433  # payload seconds, not envelope ms
    assert row["proxyWallet"] == "0xwallet"


def test_rtds_normalize_ms_fallback(tape):
    # a payload timestamp mistakenly in ms is corrected to seconds
    msg = {"topic": "activity", "type": "trades",
           "payload": {"conditionId": "0xabc", "proxyWallet": "0xw",
                       "side": "BUY", "size": 1, "price": 0.5,
                       "outcome": "Yes", "timestamp": 1791585433000}}
    row = tape.RtdsTape._normalize(None, msg)
    assert row["ts"] == 1791585433


def test_rtds_drops_empty_and_acks(tape):
    assert tape.RtdsTape._normalize(None, {"topic": "activity", "payload": {}}) is None
    # combo rows arrive with no conditionId
    msg = {"topic": "activity", "type": "trades",
           "payload": {"conditionId": "", "proxyWallet": "0xw", "side": "BUY",
                       "size": 1, "price": 0.5, "outcome": "Yes", "timestamp": 100}}
    assert tape.RtdsTape._normalize(None, msg) is None


def test_v2_trade_normalization(watcher):
    row = watcher.normalizeV2Trade({
        "condition_id": "0xabc", "proxy_wallet": "0xWallet", "side": "BUY",
        "size": 2500.0, "price": 0.2, "outcome": "Yes",
        "timestamp": 1791585526, "transaction_hash": "0xfeed"})
    assert row == {"mid": "0xabc", "ts": 1791585526, "proxyWallet": "0xwallet",
                   "side": "BUY", "size": 2500.0, "price": 0.2,
                   "outcome": "Yes", "txnHash": "0xfeed"}
    assert watcher.normalizeV2Trade({"condition_id": "", "timestamp": 1}) is None


def test_seen_before_dedup(watcher):
    watcher.SEEN.clear()
    watcher.SEEN_SET.clear()
    assert not watcher.seenBefore("a|b")
    assert watcher.seenBefore("a|b")
    assert not watcher.seenBefore("a|c")
    # bounded memory: evicted keys become eligible again
    for i in range(watcher.SEEN.maxlen + 5):
        watcher.seenBefore(f"k{i}")
    assert not watcher.seenBefore("a|b")


def test_fill_key_uses_txn_hash(watcher):
    row = {"proxyWallet": "0xw", "txnHash": "0xt", "side": "BUY", "size": 1.0,
           "price": 0.5, "ts": 7}
    k1 = watcher.fillKey(row, "0xm")
    row2 = dict(row, size=2.0)
    assert k1 != watcher.fillKey(row2, "0xm")
    assert k1 == watcher.fillKey(dict(row), "0xm")
