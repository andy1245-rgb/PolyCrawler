"""Tests for the on-chain OrderFilled BUY-leg parsers (orderBurstOnchain).

Fixtures below are REAL swapped-in payloads captured on-chain:
  V2 (ctfExchangeV2 block ~95.5M): side=0 BUY; usd 68.09 for 340.45 shares
  at price 0.20 exactly.
  V1 (ctfExchangeV1 block ~56.97M): makerAssetId=0; $33.2965 for 416.20625
  shares at price 0.08 exactly (verified against fills.parquet ground truth
  data in USD/shares terms).
Indexed topics: [sig, orderHash, maker, taker].
"""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "obo", Path(__file__).resolve().parents[1] / "scripts" / "research" / "orderBurstOnchain.py"
)
obo = importlib.util.module_from_spec(spec)
sys.modules["obo"] = obo
spec.loader.exec_module(obo)

V1_TOPIC = obo.V1_TOPIC
V2_TOPIC = obo.V2_TOPIC

V2_LOG = {
    "address": "0xe111180000d2663c0091e4f400237545b87b996b",
    "transactionHash": "0x" + "ab" * 32,
    "topics": [
        V2_TOPIC,
        "0xafe08a8a817da7e60154cf504cd4e00a46d681467cec251c2f17df3cb2411332",
        "0x00000000000000000000000052b7fc8a97df5f18974c06a83909f60c81010aa1",
        "0x00000000000000000000000031e9b2c4de53216f1250020a990d737376a5ed27",
    ],
    "data": "0x" + "".join([
        "0" * 64,                                             # side 0 = BUY
        "dc76cb66da95539d7ead27af1eb25d44c0005f04cbe3090f1fcf929c0b2f0aca",  # tokenId
        "%064x" % 68_090_000,                                 # makerAmountFilled
        "%064x" % 340_450_000,                                # takerAmountFilled
        "0" * 64, "0" * 64, "0" * 64,                         # fee, builder, metadata
    ]),
}

V1_LOG = {
    "address": "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",
    "transactionHash": "0x" + "cd" * 32,
    "topics": [
        V1_TOPIC,
        "0x049a0a21f5e338639ae1c972cc272022541a3ae57d7fe1e7b66bdd17b1be0748",
        "0x000000000000000000000000a14b10b083b4ab5bfd0d80c749fb0a01d50cb944",
        "0x000000000000000000000000200544427dfc822652cb55ca5ca9f99476a9e414",
    ],
    "data": "0x" + "".join([
        "0" * 64,                                             # makerAssetId = 0 (collateral)
        "bbfae67cc0bb4ce9b9495be19bff6445a4606543d93e0415c68d78078a645d7f",  # takerAssetId
        "%064x" % 33_296_500,                                 # makerAmountFilled = $33.2965
        "%064x" % 416_206_250,                                # takerAmountFilled = 416.20625
        "0" * 64,                                             # fee
    ]),
}

V1_SELL = {
    **V1_LOG,
    "data": "0x" + "".join([
        "bbfae67cc0bb4ce9b9495be19bff6445a4606543d93e0415c68d78078a645d7f",  # maker gives outcome
        "0" * 64,
        "%064x" % 416_206_250,
        "%064x" % 33_296_500,
        "0" * 64,
    ]),
}


def test_parse_v2_buy_leg():
    row = obo.parseV2Log(V2_LOG, ts=1792032000)
    assert row is not None
    assert row["ts"] == 1792032000
    assert row["account"] == "0x52b7fc8a97df5f18974c06a83909f60c81010aa1"
    assert abs(row["usd"] - 68.09) < 1e-9
    assert abs(row["shares"] - 340.45) < 1e-9
    assert abs(row["price"] - 0.20) < 1e-9
    assert row["orderHash"] == V2_LOG["topics"][1]
    assert row["txHash"] == "0x" + "ab" * 32


def test_parse_v2_sell_leg_skipped():
    sell = dict(V2_LOG)
    sell["data"] = "0x" + "".join([
        "%064x" % 1,          # side 1 = SELL
        "dc76cb66da95539d7ead27af1eb25d44c0005f04cbe3090f1fcf929c0b2f0aca",
        "%064x" % 68_090_000,
        "%064x" % 340_450_000,
        "0" * 64, "0" * 64, "0" * 64,
    ])
    assert obo.parseV2Log(sell, ts=1792032000) is None


def test_parse_v2_malformed_data_skipped():
    assert obo.parseV2Log({**V2_LOG, "data": "0x" + "0" * 192}, ts=1) is None


def test_parse_v1_buy_leg():
    row = obo.parseV1Log(V1_LOG, ts=1792032000)
    assert row is not None
    assert abs(row["usd"] - 33.2965) < 1e-9
    assert abs(row["shares"] - 416.20625) < 1e-9
    assert abs(row["price"] - 0.08) < 1e-9
    assert row["account"] == "0xa14b10b083b4ab5bfd0d80c749fb0a01d50cb944"
    assert row["orderHash"] == V1_LOG["topics"][1]


def test_parse_v1_sell_leg_skipped():
    assert obo.parseV1Log(V1_SELL, ts=1792032000) is None


def test_canonical_token_id_strips_leading_zeros():
    assert obo.canonicalTokenId("0" * 50 + "00ec4") == "0xec4"


def test_sample_days_deterministic_and_sorted():
    days = obo.sampleDays((2024, 1), 2, seed=7)
    again = obo.sampleDays((2024, 1), 2, seed=7)
    assert days == again
    assert len(days) == 34 * 2  # Jan 2024 .. Oct 2026 = 34 months
    assert days == sorted(days)
    assert all(d.year >= 2024 and d.year <= 2026 for d in days)
