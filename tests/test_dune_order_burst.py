"""Tests for the Dune order_hash burst rebuild logic (synthetic fills)."""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

RESEARCH = Path(__file__).resolve().parents[1] / "scripts" / "research"
spec = importlib.util.spec_from_file_location("dob", RESEARCH / "duneOrderBurst.py")
dob = importlib.util.module_from_spec(spec)
sys.modules["dob"] = dob
spec.loader.exec_module(dob)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fillRow(account, ts, usd, fills=1, mid="0xm", outcome="Yes", oh="0xo", gapSec=60):
    """Split `usd` into `fills` sequential fills each `gapSec` apart."""
    per = usd / fills
    return [{"ts": ts + timedelta(seconds=gapSec * i), "account": account, "marketId": mid,
             "outcome": outcome, "shares": per / 0.10, "price": 0.10, "usd": per,
             "orderHash": oh} for i in range(fills)]


def test_split_order_recovered_by_order_level():
    # one $8k order paid as 10 x $800 fills at 12-minute gaps: every fill
    # opens a new 10-minute burst window, so the shipped rule sees only
    # $800 bursts; the order_hash view reassembles the full $8k.
    rows = fillRow("0xa", T0, 8000, fills=10, gapSec=720)
    fills = pl.DataFrame(rows)
    bursts = dob.burstEntries(fills)
    orders = dob.orderEntries(fills)
    assert (bursts["usd"] < 5000).all()
    assert orders.height == 1
    assert abs(orders["usd"][0] - 8000) < 1e-6
    assert abs(orders["price"][0] - 0.10) < 1e-9


def test_assembled_burst_dropped_by_order_level():
    # five unrelated $1k orders inside 10 minutes: the shipped rule sees a
    # $5k burst, the order-level rule sees nothing >= $5k.
    rows = []
    for n in range(5):
        rows += fillRow("0xa", T0 + timedelta(minutes=n), 1000, oh=f"0x{n}")
    fills = pl.DataFrame(rows)
    bursts = dob.burstEntries(fills)
    orders = dob.orderEntries(fills)
    assert bursts.height == 1 and bursts["usd"][0] == 5000.0
    assert (orders["usd"] < 5000).all()


def test_burst_baseline_matches_shipped_mechanics():
    # same wallet, two bursts separated by > 10 min stay separate
    rows = fillRow("0xa", T0, 6000, fills=2) + fillRow("0xa", T0 + timedelta(minutes=30), 6000, fills=2)
    bursts = dob.burstEntries(pl.DataFrame(rows))
    assert bursts.height == 2
    assert (bursts["usd"] == 6000.0).all()


def test_annotate_joins_winner_and_freshness():
    markets = pl.DataFrame({
        "marketId": ["0xm"], "eventSlug": ["iran-thing"], "winner": ["Yes"],
        "resolvedAt": [T0 + timedelta(days=3)]})
    firstSeen = pl.DataFrame({"account": ["0xa"], "firstTs": [T0]})
    rows = fillRow("0xa", T0 + timedelta(hours=1), 6000, fills=2)
    entries = dob.orderEntries(pl.DataFrame(rows))
    ann = dob.annotate(entries, markets, firstSeen)
    assert ann["won"][0] is True
    assert ann["ret"][0] == 1 / 0.10 - 1
    assert ann["ageDays"][0] == 1 / 24
    assert ann["marketsSoFar"][0] == 1
