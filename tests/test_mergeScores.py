"""Parity of the mergeScores merge plan against the old unconditional
union-find in buildFundingClusters, on synthetic graphs.

The reference implementation below is a verbatim copy of the pre-refactor
merge loop (direct transfers, sharedFunder/sharedCashOut anchor pairs, hop,
sharedOrigin, originSibling, coTrade), so each test asserts that the new
evidence/decision pipeline produces the same partition at the shipped
thresholds — plus that the threshold plumbing WOULD flip a merged pair, which
is the audit hook, not a shipped knob."""

from polycrawler.discovery import TransferRow, buildFundingClusters
from polycrawler.discovery.mergeScores import (
    STRONG_KINDS,
    defaultThresholds,
    mergePlan,
)


def rows(*specs: tuple[int, str, str, float]) -> list[TransferRow]:
    return [
        TransferRow(ts, src, dst, usd, f"tx{index}")
        for index, (ts, src, dst, usd) in enumerate(specs)
    ]


def legacyMerge(
    accounts: set[str],
    blocked: set[str],
    eoaFunders: set[str],
    grandparents: dict[str, set[str]],
    originGroups: dict[str, set[str]],
    siblingGroups: dict[str, set[str]],
    coTrades: list[tuple[str, str]],
    fundingHops: int,
    usable: list[TransferRow],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Verbatim pre-refactor merge machinery (union-find + linkOf),
    returns (account -> clusterId, account -> linkType set)."""
    uf = {account: account for account in accounts}
    linkOf: dict[str, set[str]] = {account: set() for account in accounts}

    def find(account: str) -> str:
        root = account
        while uf[root] != root:
            root = uf[root]
        while uf[account] != root:
            nxt = uf[account]
            uf[account] = root
            account = nxt
        return root

    def union(left: str, right: str, kind: str) -> None:
        leftRoot = find(left)
        rightRoot = find(right)
        if leftRoot != rightRoot:
            if leftRoot < rightRoot:
                uf[rightRoot] = leftRoot
            else:
                uf[leftRoot] = rightRoot
        linkOf[left].add(kind)
        linkOf[right].add(kind)

    byFunder: dict[str, set[str]] = {}
    byCashOut: dict[str, set[str]] = {}
    for row in usable:
        if row.toAddr in accounts and row.fromAddr not in blocked:
            byFunder.setdefault(row.fromAddr, set()).add(row.toAddr)
        if (
            row.fromAddr in accounts
            and row.toAddr not in accounts
            and row.toAddr not in blocked
        ):
            byCashOut.setdefault(row.toAddr, set()).add(row.fromAddr)
        if row.fromAddr in accounts and row.toAddr in accounts:
            union(row.fromAddr, row.toAddr, "direct")

    def linkGroup(group: set[str], kind: str) -> None:
        members = sorted(account for account in group if account in accounts)
        if len(members) < 2:
            return
        for other in members[1:]:
            union(members[0], other, kind)

    for group in byFunder.values():
        linkGroup(group, "sharedFunder")
    for group in byCashOut.values():
        linkGroup(group, "sharedCashOut")

    reached: dict[str, set[str]] = {}
    if fundingHops >= 2:
        for funder, group in byFunder.items():
            if funder not in eoaFunders:
                continue
            for grand in grandparents.get(funder, ()):
                if grand in blocked or grand == funder:
                    continue
                for account in group:
                    if account in accounts:
                        reached.setdefault(grand, set()).add(account)
        for group in reached.values():
            linkGroup(group, "hop")

    for group in originGroups.values():
        linkGroup(group, "sharedOrigin")
    for group in siblingGroups.values():
        linkGroup(group, "originSibling")
    for left, right in coTrades:
        left, right = left.lower(), right.lower()
        if left in uf and right in uf and left != right:
            union(left, right, "coTrade")

    return {account: find(account) for account in accounts}, linkOf


def snap(transfers: list[TransferRow], blocked: set[str], splitTs: int):
    return [
        row
        for row in transfers
        if row.amountUsd >= 1
        and row.ts < splitTs
        and row.fromAddr not in blocked
        and row.toAddr not in blocked
    ]


def groupsByAccount(partition: dict[str, str]) -> list[list[str]]:
    grouped: dict[str, set[str]] = {}
    for account, cluster in partition.items():
        grouped.setdefault(cluster, set()).add(account)
    return sorted(map(sorted, grouped.values()))


def testParityOnSyntheticGraphWithTwoSidedGate() -> None:
    funder = "0x11"
    otherFunder = "0x12"
    hub = "0x22"
    grand = "0x33"
    hopFunder = "0x44"
    hopFunder2 = "0x45"
    dest = "0x55"
    splitTs = 10_000
    blocked = {hub}
    accounts = {"a", "b", "c", "d", "e", "f", "g"}
    transfers = [
        # direct edge a->b seen twice: evidence count 2
        (10, "a", "b", 50.0),
        (20, "a", "b", 50.0),
        # two EOA funders reach accounts a,b behind one grandparent: hop edge
        # with 2 hop legs
        (30, hopFunder, "a", 40.0),
        (31, hopFunder, "b", 40.0),
        (32, hopFunder2, "a", 40.0),
        (33, hopFunder2, "b", 40.0),
        # c/d co-trade the same book across 3 matched windows (multi-window)
        # sharedFunder with a hub: the hub funder is blocked, the real funders
        # are not, so only real funder groups link e,f,g
        (40, funder, "e", 40.0),
        (41, funder, "f", 40.0),
        (42, funder, "g", 40.0),
        (43, otherFunder, "e", 40.0),
        (44, otherFunder, "g", 40.0),
        (50, hub, "e", 40.0),
        (51, hub, "f", 40.0),
        # shared cash-out: e and f both emptied into dest
        (60, "e", dest, 40.0),
        (61, "f", dest, 40.0),
    ]
    usdRows = rows(*transfers)
    usable = snap(usdRows, blocked, splitTs)
    originGroups = {"0xorigin": {"e", "f", "g"}}
    siblingGroups = {"0xorigin": {"e", "f", "g"}}
    coTrades = [("c", "d", 3)]
    legacyPartition, legacyLinkOf = legacyMerge(
        accounts=accounts,
        blocked=blocked,
        eoaFunders={hopFunder, hopFunder2},
        grandparents={hopFunder: {grand}, hopFunder2: {grand}},
        originGroups=originGroups,
        siblingGroups=siblingGroups,
        coTrades=[("c", "d")],
        fundingHops=2,
        usable=usable,
    )
    args = {
        "accounts": accounts,
        "suspicious": set(accounts),
        "transfers": usdRows,
        "blocked": blocked,
        "eoaFunders": {hopFunder, hopFunder2},
        "grandparents": {hopFunder: {grand}, hopFunder2: {grand}},
        "profits": {},
        "splitTs": splitTs,
        "minSuspiciousAccounts": 2,
        "fundingHops": 2,
        "minFundingUsd": 1,
        "minCoTrades": 2,
        "originGroups": originGroups,
        "siblingGroups": siblingGroups,
        "coTrades": coTrades,
    }
    parents, members = buildFundingClusters(**args)
    # identical partition to the old unconditional merge
    partition: dict[str, str] = {row["account"]: row["clusterId"] for row in members}
    assert partition == legacyPartition
    # identical per-account link types
    linkTypes: dict[str, set[str]] = {}
    for row in members:
        linkTypes[row["account"]] = set(row["linkType"].split(","))
    for account in accounts:
        assert linkTypes[account] == legacyLinkOf[account], account
    # expected shape: 3 components
    assert groupsByAccount(partition) == [
        ["a", "b"],
        ["c", "d"],
        ["e", "f", "g"],
    ]
    # parents: keep it stable — one row per component, parent = its anchor
    assert {row["clusterId"] for row in parents} == {"a", "c", "e"}

    # the plan's evidence + decisions explain every merge with its rule
    plan = mergePlan(
        usable,
        accounts,
        blocked,
        {hopFunder, hopFunder2},
        {hopFunder: {grand}, hopFunder2: {grand}},
        originGroups,
        siblingGroups,
        coTrades,
        2,
        2,
    )
    edges = {(edge.kind, edge.left, edge.right): edge for edge in plan.edges}
    decisions = {(d.kind, d.left, d.right): d for d in plan.decisions}
    assert len(plan.decisions) == len(plan.edges)
    # two-sided gate: every strong money-flow edge merged (>= 1), coTrade by windows
    for key, decision in decisions.items():
        kind, left, right = key
        if kind == "coTrade":
            assert decision.evidence == 3
            assert "3 >= threshold 2" in decision.rule
        else:
            assert decision.merge is True
        assert decision.left < decision.right or kind == "coTrade"
    assert edges[("direct", "a", "b")].evidence == 2
    assert decisions[("direct", "a", "b")].merge is True
    assert "2 >= threshold 1" in decisions[("direct", "a", "b")].rule
    # hop group reached through the grandparent: 2 members, 2 hop legs
    assert edges[("hop", "a", "b")].evidence == 2
    assert decisions[("hop", "a", "b")].merge is True
    # sharedFunder pairs from BOTH funders exist; each counts its funder legs
    sharedFunderEdges = [
        edge for edge in plan.edges if edge.kind == "sharedFunder"
    ]
    shared = {
        (edge.source, edge.left, edge.right): edge for edge in sharedFunderEdges
    }
    assert shared[(funder, "e", "f")].evidence == 3
    assert shared[(otherFunder, "e", "g")].evidence == 2
    assert len([e for e in sharedFunderEdges if (e.left, e.right) == ("e", "g")]) == 2
    sharedByKey = {
        (edge.left, edge.right): edge for edge in sharedFunderEdges
    }
    assert sharedByKey[("e", "g")].source == otherFunder
    assert decisions[("sharedFunder", "e", "g")].merge is True
    # sharedCashOut: both members emptied into dest (2 rows)
    assert edges[("sharedCashOut", "e", "f")].evidence == 2
    # sharedOrigin + originSibling links exist from the same origin group
    assert edges[("sharedOrigin", "e", "f")].evidence == 1
    assert decisions[("originSibling", "e", "g")].merge is True
    # the hub is blocked: no edge in the plan touches it
    assert not any(hub in key for key in decisions)
    # clusters' linkTypes rows now carry every kind the edges imply
    clusterKinds = {row["linkTypes"] for row in parents}
    for kind in {"direct", "hop", "coTrade", "sharedFunder", "sharedCashOut", "sharedOrigin", "originSibling"}:
        assert any(kind in text for text in clusterKinds), kind


def testThresholdPlumbingFlipsButDefaultsDoNothing() -> None:
    usd = 50.0
    args = {
        "accounts": {"a", "b", "c", "d"},
        "suspicious": {"a", "b", "c", "d"},
        "transfers": rows(
            (10, "a", "b", usd),  # direct pair seen twice
            (20, "a", "b", usd),
            (30, "0x1", "c", usd),  # sharedFunder: 2 legs -> c,d
            (31, "0x1", "d", usd),
            (40, "0x2", "c", usd),  # second shared funder: 2 legs -> c,d
            (41, "0x2", "d", usd),
        ),
        "blocked": set(),
        "eoaFunders": set(),
        "grandparents": {},
        "profits": {},
        "splitTs": 10_000,
        "minSuspiciousAccounts": 2,
        "fundingHops": 1,
        "minFundingUsd": 1,
        "minCoTrades": 2,
    }
    parents, members = buildFundingClusters(**args)
    # membership gate: every component with >= minSuspiciousAccounts flagged
    # accounts gets a row, and ALL of its accounts get member rows. Both
    # components here carry exactly 2 flagged accounts, so neither is dropped
    # by the gate and {a,b,c,d} are all inside the member rows.
    assert {row["clusterId"] for row in parents} == {"a", "c"}
    membership = {row["account"] for row in members}
    assert membership == set(args["accounts"])
    # parents[0] is NOT the anchor component: the returned rows iterate the
    # accounts set, so their order varies with the interpreter hash seed —
    # that is why the clusterId membership is asserted as a set above.
    # shipped default thresholds reproduce the unconditional merge exactly
    tight = dict(args)
    tight["mergeThresholds"] = defaultThresholds(minCoTrades=2)
    parentsTight, membersTight = buildFundingClusters(**tight)
    assert [(r["clusterId"], r["account"], r["linkType"]) for r in membersTight] == [
        (r["clusterId"], r["account"], r["linkType"]) for r in members
    ]
    assert [r["linkTypes"] for r in parentsTight] == [r["linkTypes"] for r in parents]
    # a hypothetical weight BELOW the kind's threshold flips the merge: the
    # sharedFunder evidence is 2 legs per funder, so a threshold of 4 must
    # split c and d, while direct (2 rows >= 1) still merges a and b. Lower
    # minSuspiciousAccounts to 1 so the split singletons stay visible.
    flip = dict(args, minSuspiciousAccounts=1)
    flip["mergeThresholds"] = {"sharedFunder": 4, "direct": 1, "coTrade": 2}
    parentsFlip, membersFlip = buildFundingClusters(**flip)
    partitionFlip = {row["account"]: row["clusterId"] for row in membersFlip}
    assert partitionFlip["a"] == "a"  # direct still merged (2 rows >= 1)
    assert partitionFlip["b"] == "a"
    assert partitionFlip["c"] == "c"  # c stays its own anchor
    assert partitionFlip["d"] == "d"  # d split from c
    assert {row["clusterId"] for row in parentsFlip} == {"a", "c", "d"}
    # the un-merged edge is still AUDITED: its sharedFunder label sticks to
    # both endpoints as edge presence, the accounts are NOT merged, and the
    # decision rule records the flip.
    assert all(
        "sharedFunder" in row["linkType"]
        for row in membersFlip
        if row["account"] in {"c", "d"}
    )
    planFlip = mergePlan(
        snap(args["transfers"], set(), 10_000),
        args["accounts"],
        set(),
        set(),
        {},
        {},
        {},
        None,
        1,
        2,
        thresholds={"sharedFunder": 4, "direct": 1, "coTrade": 2},
    )
    flipped = [
        decision
        for decision in planFlip.decisions
        if decision.kind == "sharedFunder" and not decision.merge
    ]
    assert len(flipped) == 2  # (c,d) once per funding funder 0x1 / 0x2
    assert all("< threshold 4" in decision.rule for decision in flipped)
    # coTrade threshold flips with the edge label still audited: one matched
    # window is below minCoTrades 2, and no sharedFunder edge remains to glue them
    flip2 = dict(args, minSuspiciousAccounts=1)
    flip2["coTrades"] = [("c", "d", 1)]
    flip2["mergeThresholds"] = {"sharedFunder": 4, "direct": 1, "coTrade": 2}
    parents2, members2 = buildFundingClusters(**flip2)
    partition2 = {row["account"]: row["clusterId"] for row in members2}
    assert partition2["c"] == "c" and partition2["d"] == "d"
    rowsByAccount = {row["account"]: row for row in members2}
    assert "coTrade" in rowsByAccount["c"]["linkType"]  # edge presence, not a merge
    parentC = next(
        row for row in parents2 if row["clusterId"] == "c"
    )
    assert "coTrade" in parentC["linkTypes"]
    # shipped default with the same single-window evidence has no coTrade merge
    # but the sharedFunder edges still glue c,d at threshold 1: cluster {c,d}.
    flip3 = dict(args, minSuspiciousAccounts=1, coTrades=[("c", "d", 1)])
    _, members3 = buildFundingClusters(**flip3)
    partition3 = {row["account"]: row["clusterId"] for row in members3}
    assert partition3["c"] == "c" and partition3["d"] == "c"
    # and the shipped default keeps it merged
    defaultPlan = mergePlan(
        [], {"c", "d"}, set(), set(), {}, {}, {}, [("c", "d", 3)], 1, 2
    )
    assert defaultPlan.decisions[0].merge is True
    # the audit gate also catches under-threshold coTrade evidence at defaults:
    # one window < minCoTrades 2 stays unmerged in the decision record
    gatedPlan = mergePlan(
        [], {"c", "d"}, set(), set(), {}, {}, {}, [("c", "d", 1)], 1, 2
    )
    assert gatedPlan.decisions[0].merge is False
    assert "1 < threshold 2" in gatedPlan.decisions[0].rule


def testDefaultThresholdsTwoSidedGate() -> None:
    thresholds = defaultThresholds(minCoTrades=2)
    # strong money-flow kinds merge on >= 1 edge; coTrade on >= minCoTrades
    assert all(thresholds[kind] == 1 for kind in STRONG_KINDS)
    assert thresholds["coTrade"] == 2
    with3 = defaultThresholds(minCoTrades=3)
    assert with3["coTrade"] == 3
