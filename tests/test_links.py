import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from polycrawler.discovery import (
    TransferRow,
    buildFundingClusters,
    coTradePairs,
    firstBridgeDeposits,
    matchTimes,
    parseRelayPage,
)

utc = timezone.utc
solver = "0xf70da97812cb96acdf810712aa562db8dfa3dbef"


def clusters(**overrides):
    args = {
        "accounts": {"a", "b", "c"},
        "suspicious": {"a", "b", "c"},
        "transfers": [],
        "blocked": set(),
        "eoaFunders": set(),
        "grandparents": {},
        "profits": {},
        "splitTs": 10_000,
        "minSuspiciousAccounts": 2,
        "fundingHops": 1,
        "minFundingUsd": 1,
    }
    args.update(overrides)
    args["transfers"] = [
        row if isinstance(row, TransferRow) else TransferRow(**row) for row in args["transfers"]
    ]
    return buildFundingClusters(**args)


def testRelayHashResponseParsesOrigin() -> None:
    payload = json.loads((Path(__file__).parent / "fixtures" / "relayHash.json").read_text())
    page = parseRelayPage(payload)
    assert page.continuation is None
    row = page.rows[0]
    assert row.user == "0xd22e599505446dec378f9c161b741e6e722b2eda"
    assert row.recipient == "0x09d3273fa76282ce09f4f35a87d6f087c05f4e84"
    assert row.originChainId == 1
    assert row.destinationChainId == 137
    assert row.payoutTxHash == "0x7244132470aa5b71c8b797b1424629b9185f06a7ac84710937f33a7d40eb3465"
    assert row.amountUsd == 9925.152641
    assert row.block == 83000000
    continued = parseRelayPage({"requests": [], "continuation": "cursor-2"})
    assert continued.continuation == "cursor-2"


def testFirstBridgeDepositIsEarliestLargeSolverPayout() -> None:
    rows = [
        TransferRow(50, solver, "a", 10, "dust"),
        TransferRow(80, solver, "a", 200, "second"),
        TransferRow(40, solver, "a", 150, "first"),
        TransferRow(30, "0xperson", "a", 500, "friend"),
        TransferRow(20_000, solver, "b", 400, "late"),
    ]
    picked = firstBridgeDeposits(rows, {"a", "b"}, {solver}, 100, 10_000)
    assert [(row.toAddr, row.txHash) for row in picked] == [("a", "first")]


def testCoTradeLinksOnlyRepeatedSuspiciousBuys() -> None:
    def fill(account: str, market: str, outcome: str, when: int) -> dict:
        return {
            "ts": datetime.fromtimestamp(when, tz=utc),
            "account": account,
            "marketId": market,
            "outcome": outcome,
            "side": "BUY",
            "size": 1.0,
            "price": 0.2,
            "txHash": f"{account}-{market}-{when}",
        }

    fills = pl.DataFrame(
        [
            fill("a", "m1", "Yes", 100),
            fill("b", "m1", "Yes", 105),
            fill("a", "m2", "No", 200),
            fill("b", "m2", "No", 200),
            fill("a", "m3", "Yes", 300),
            fill("b", "m3", "Yes", 400),
            fill("mm", "m1", "Yes", 100),
            fill("mm", "m2", "No", 200),
            fill("a", "m1", "Yes", 500),
        ]
    ).with_columns(pl.col("ts").cast(pl.Datetime("us", "UTC")))
    cutoff = datetime.fromtimestamp(1000, tz=utc)
    linked = coTradePairs(fills, {"a", "b"}, cutoff, 10, 2)
    assert linked == [("a", "b")]
    assert "mm" not in {name for pair in linked for name in pair}
    assert coTradePairs(fills, {"a", "b"}, cutoff, 10, 3) == []
    assert matchTimes(
        [datetime.fromtimestamp(1, tz=utc), datetime.fromtimestamp(20, tz=utc)],
        [datetime.fromtimestamp(9, tz=utc)],
        10,
    ) == 1


def testSharedOriginBecomesParentAndSiblingIsExtra() -> None:
    parents, members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        blocked={solver},
        transfers=[
            {"ts": 10, "fromAddr": solver, "toAddr": "a", "amountUsd": 100, "txHash": "1"},
            {"ts": 11, "fromAddr": solver, "toAddr": "b", "amountUsd": 100, "txHash": "2"},
        ],
        originGroups={"0xorigin": {"a", "b"}},
        siblingGroups={"0xorigin": {"a", "b"}},
        siblingExtras={"0xorigin": {"a", "b", "later"}},
        originTimes={"a": 10, "b": 11},
    )
    assert parents[0]["parent"] == "0xorigin"
    assert parents[0]["linkTypes"] == "originSibling,sharedOrigin"
    assert parents[0]["accountCount"] == 3
    assert parents[0]["firstSeen"] == 10
    extra = [row for row in members if row["account"] == "later"]
    assert extra == [{"clusterId": "a", "account": "later", "linkType": "originSibling"}]


def testCoTradeClusterWithoutSharedFunder() -> None:
    parents, members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        coTrades=[("a", "b")],
    )
    assert parents[0]["parent"] == "component:a"
    assert parents[0]["linkTypes"] == "coTrade"
    assert {row["linkType"] for row in members} == {"coTrade"}


def testOriginBeatsComponentWhenBothExist() -> None:
    parents, _members = clusters(
        coTrades=[("a", "b"), ("b", "c")],
        originGroups={"0xorigin": {"a", "b", "c"}},
    )
    assert parents[0]["parent"] == "0xorigin"
    assert "coTrade" in parents[0]["linkTypes"]
    assert "sharedOrigin" in parents[0]["linkTypes"]
