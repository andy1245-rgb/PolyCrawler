"""Tests for paper mark-to-market valuation logic (synthetic signal rows)."""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pmtm", Path(__file__).resolve().parents[1] / "scripts" / "paperMarkToMarket.py"
)
pmtm = importlib.util.module_from_spec(spec)
sys.modules["pmtm"] = pmtm
spec.loader.exec_module(pmtm)


def test_spend_capped_at_budget():
    # big ask: the $100 budget binds even though the book had $376 takeable
    row = {"bestAsk": "0.26", "avgPrice": "0.27", "takeableShares": "1448.69"}
    spend, shares = pmtm.copySpend(row)
    assert spend == 100.0
    assert abs(shares - 100.0 / 0.26) < 1e-9


def test_spend_limited_by_takeable_size():
    # tiny ask: $149.6 takeable caps far below the $100 budget... wait, it
    # doesn't: 149.6 * 0.14 > 100. Use a genuinely small book instead.
    row = {"bestAsk": "0.14", "avgPrice": "0.18", "takeableShares": "10"}
    spend, shares = pmtm.copySpend(row)
    assert abs(spend - 1.40) < 1e-9
    assert abs(shares - 10.0) < 1e-9


def test_entry_falls_back_to_avg_price():
    row = {"bestAsk": "", "avgPrice": "0.27", "takeableShares": "0"}
    spend, _ = pmtm.copySpend(row)
    assert abs(spend - 100.0) < 1e-9


def test_zero_entry_skipped():
    row = {"bestAsk": "0", "avgPrice": "0", "takeableShares": "7"}
    assert pmtm.copySpend(row) == (0.0, 0.0)


def test_open_pnl_tracks_mark():
    # entry 0.20, bought $50 of stock; mark doubles to 0.40: +$50
    row = {"bestAsk": "0.20", "avgPrice": "", "takeableShares": "250"}
    entry, spend, shares, pnl = pmtm.openPnl(row, 0.40)
    assert entry == 0.20
    assert abs(spend - 50.0) < 1e-9
    assert abs(shares - 250.0) < 1e-9
    assert abs(pnl - 50.0) < 1e-6


def test_open_pnl_into_winning_market():
    row = {"bestAsk": "0.14", "avgPrice": "", "takeableShares": "2000"}
    _, _, _, pnl = pmtm.openPnl(row, 1.0)
    # $100 spent at 0.14 -> 714.3 shares -> +$614.3 at resolution
    assert abs(pnl - (100.0 / 0.14 - 100.0)) < 1e-6


def test_signalKey_keeps_apart_alerts_sharing_a_second():
    """59 of the first 72 live alerts shared an alertTs with another alert, so a
    single-field dedupe key silently drops most of the book. The key must be the
    same tuple the other books use."""
    a = {"alertTs": "2026-11-09 20:00:57", "account": "0xaaa", "eventSlug": "e"}
    b = {"alertTs": "2026-11-09 20:00:57", "account": "0xbbb", "eventSlug": "e"}
    same = dict(a)
    assert pmtm.signalKey(a) != pmtm.signalKey(b)
    assert pmtm.signalKey(a) == pmtm.signalKey(same)
    assert len({pmtm.signalKey(r) for r in (a, b, same)}) == 2


def test_paperPnl_keys_signals_identically():
    """paperPnl.py and paperMarkToMarket.py must agree on alert identity, or the
    realized book and the open book disagree about which alerts are already done."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "paperPnl.py"
    spec = importlib.util.spec_from_file_location("ppnl", path)
    ppnl = importlib.util.module_from_spec(spec)
    sys.modules["ppnl"] = ppnl
    spec.loader.exec_module(ppnl)
    row = {"alertTs": "2026-11-09 20:00:57", "account": "0xaaa", "eventSlug": "e"}
    assert ppnl.signalKey(row) == pmtm.signalKey(row)
    assert ppnl.signalKey({}) == pmtm.signalKey({})
