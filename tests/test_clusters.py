from polycrawler.discovery import (
    TransferRow,
    buildFundingClusters,
    collateralCounterparties,
    hubAddresses,
    hubFromSample,
)

usdc = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
spamToken = "0x1111111111111111111111111111111111111111"


def rawTransfer(src: str, dst: str, token: str = usdc) -> dict:
    return {
        "from": src,
        "to": dst,
        "contractAddress": token,
        "tokenDecimal": "6",
        "value": "1000000",
        "timeStamp": "1",
        "hash": "0xabc",
    }


def clusters(**overrides):
    args = {
        "accounts": {"a", "b", "c", "d"},
        "suspicious": {"a", "b", "c", "d"},
        "transfers": [],
        "blocked": set(),
        "eoaFunders": set(),
        "grandparents": {},
        "profits": {},
        "splitTs": 10_000,
        "minSuspiciousAccounts": 2,
        "fundingHops": 2,
        "minFundingUsd": 1,
    }
    args.update(overrides)
    args["transfers"] = [
        row if isinstance(row, TransferRow) else TransferRow(**row) for row in args["transfers"]
    ]
    return buildFundingClusters(**args)


def testHubThresholdUsesCollateralCounterpartiesOnly() -> None:
    hub = "0xhub"
    rows = [rawTransfer(f"0x{index:040x}", hub) for index in range(49)]
    assert collateralCounterparties(hub, rows) == 49
    assert hubAddresses({hub: rows}, 50) == {}
    rows.append(rawTransfer(f"0x{49:040x}", hub))
    rows.append(rawTransfer(rows[0]["from"], hub))
    assert hubAddresses({hub: rows}, 50) == {hub: 50}
    spam = [rawTransfer(f"0x{index:040x}", hub, spamToken) for index in range(60)]
    assert collateralCounterparties(hub, spam) == 0


def testFullPageContractIsHubEvenWhenCounterpartiesAreConcentrated() -> None:
    assert hubFromSample(21, 51, pageFull=True, isContract=True, minimum=50) is True
    assert hubFromSample(21, 21, pageFull=True, isContract=True, minimum=50, codeChars=9000) is True
    assert hubFromSample(6, 0, pageFull=True, isContract=True, minimum=50, codeChars=250) is False
    assert hubFromSample(14, 0, pageFull=False, isContract=True, minimum=50, codeChars=250) is False
    assert hubFromSample(510, 0, pageFull=True, isContract=False, minimum=50) is True
    assert hubFromSample(21, 21, pageFull=True, isContract=False, minimum=50) is False


def testSharedFunderBecomesClusterAndHubDoesNot() -> None:
    parents, members = clusters(
        transfers=[
            {"ts": 10, "fromAddr": "funder", "toAddr": "a", "amountUsd": 100, "txHash": "1"},
            {"ts": 11, "fromAddr": "funder", "toAddr": "b", "amountUsd": 80, "txHash": "2"},
            {"ts": 12, "fromAddr": "hub", "toAddr": "c", "amountUsd": 90, "txHash": "3"},
            {"ts": 13, "fromAddr": "hub", "toAddr": "d", "amountUsd": 90, "txHash": "4"},
        ],
        blocked={"hub"},
        profits={"a": 5, "b": 7},
    )
    assert len(parents) == 1
    assert parents[0]["parent"] == "funder"
    assert parents[0]["clusterId"] == "a"
    assert parents[0]["suspiciousCount"] == 2
    assert parents[0]["accountCount"] == 2
    assert parents[0]["totalProfitUsd"] == 12
    assert parents[0]["linkTypes"] == "sharedFunder"
    assert parents[0]["firstSeen"] == 10
    assert {row["account"] for row in members} == {"a", "b"}


def testSharedCashOutUsesComponentParent() -> None:
    parents, members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        transfers=[
            {"ts": 30, "fromAddr": "a", "toAddr": "dest", "amountUsd": 40, "txHash": "1"},
            {"ts": 31, "fromAddr": "b", "toAddr": "dest", "amountUsd": 40, "txHash": "2"},
            {"ts": 32, "fromAddr": "a", "toAddr": "hub", "amountUsd": 40, "txHash": "3"},
            {"ts": 33, "fromAddr": "b", "toAddr": "hub", "amountUsd": 40, "txHash": "4"},
        ],
        blocked={"hub"},
    )
    assert len(parents) == 1
    assert parents[0]["parent"] == "component:a"
    assert parents[0]["linkTypes"] == "sharedCashOut"
    assert {row["linkType"] for row in members} == {"sharedCashOut"}


def testDirectTransferLinksAccounts() -> None:
    parents, _members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        transfers=[{"ts": 4, "fromAddr": "a", "toAddr": "b", "amountUsd": 25, "txHash": "1"}],
    )
    assert parents[0]["parent"] == "component:a"
    assert parents[0]["linkTypes"] == "direct"
    assert parents[0]["firstSeen"] == 4


def testHopLinksThroughNonHubEoaAndStopsAtHub() -> None:
    transfers = [
        {"ts": 1, "fromAddr": "x", "toAddr": "a", "amountUsd": 10, "txHash": "1"},
        {"ts": 2, "fromAddr": "y", "toAddr": "b", "amountUsd": 10, "txHash": "2"},
    ]
    linked, _members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        transfers=transfers,
        eoaFunders={"x", "y"},
        grandparents={"x": {"g"}, "y": {"g"}},
    )
    assert linked[0]["parent"] == "g"
    assert linked[0]["linkTypes"] == "hop"
    blocked, _members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        transfers=transfers,
        blocked={"g"},
        eoaFunders={"x", "y"},
        grandparents={"x": {"g"}, "y": {"g"}},
    )
    assert blocked == []
    noHop, _members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        transfers=transfers,
        eoaFunders={"x", "y"},
        grandparents={"x": {"g"}, "y": {"g"}},
        fundingHops=1,
    )
    assert noHop == []


def testParentIsMostSharedFunderAndSplitIsRespected() -> None:
    parents, members = clusters(
        transfers=[
            {"ts": 10, "fromAddr": "f1", "toAddr": "a", "amountUsd": 100, "txHash": "1"},
            {"ts": 11, "fromAddr": "f1", "toAddr": "b", "amountUsd": 100, "txHash": "2"},
            {"ts": 20, "fromAddr": "f2", "toAddr": "a", "amountUsd": 100, "txHash": "3"},
            {"ts": 21, "fromAddr": "f2", "toAddr": "b", "amountUsd": 100, "txHash": "4"},
            {"ts": 22, "fromAddr": "f2", "toAddr": "c", "amountUsd": 100, "txHash": "5"},
            {"ts": 11000, "fromAddr": "f2", "toAddr": "d", "amountUsd": 100, "txHash": "6"},
            {"ts": 23, "fromAddr": "f3", "toAddr": "a", "amountUsd": 0.5, "txHash": "7"},
            {"ts": 24, "fromAddr": "f3", "toAddr": "b", "amountUsd": 0.5, "txHash": "8"},
        ],
        profits={"a": 1, "b": 2, "c": 4, "d": 8},
    )
    assert len(parents) == 1
    assert parents[0]["parent"] == "f2"
    assert parents[0]["suspiciousCount"] == 3
    assert parents[0]["totalProfitUsd"] == 7
    assert parents[0]["firstSeen"] == 10
    assert {row["account"] for row in members} == {"a", "b", "c"}


def testSiblingsIncludeAccountsFundedAfterSplit() -> None:
    parents, members = clusters(
        accounts={"a", "b"},
        suspicious={"a", "b"},
        transfers=[
            {"ts": 5, "fromAddr": "funder", "toAddr": "a", "amountUsd": 50, "txHash": "1"},
            {"ts": 6, "fromAddr": "funder", "toAddr": "b", "amountUsd": 50, "txHash": "2"},
        ],
        fundedByParent={"funder": {"a", "b", "sib"}},
    )
    assert parents[0]["accountCount"] == 3
    sibling = [row for row in members if row["account"] == "sib"]
    assert sibling == [{"clusterId": "a", "account": "sib", "linkType": "funded"}]
