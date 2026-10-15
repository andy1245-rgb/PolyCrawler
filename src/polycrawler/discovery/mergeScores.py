"""Merge scoring for the funding-cluster linker.

buildFundingClusters is deliberately direct: one edge of any of the seven link
kinds glues two accounts together, unconditionally. This module does not
change those semantics (tests/test_mergeScores.py locks them against a copy of
the old unconditional union-find); it just makes every merge auditable and
gives the plumbing a threshold hook WITHOUT shipping a tuning knob.

What it emits, for each raw edge set:
  * per-edge evidence records - edge kind, both endpoints, the evidence count
    (`evidence`) and what that count counts (`basis`), so a merge can be
    traced back to its source;
  * per-pair merge decisions - whether this specific pair bridges two
    components, and under which rule ("kind basis evidence >= threshold").

Two-sided audit gate (pre-registered, shipped defaults):
  * strong money-flow edges - direct, sharedFunder, sharedCashOut, hop,
    sharedOrigin, originSibling - merge at >= 1 edge, exactly today's
    "one strong edge merges" behaviour;
  * coTrade merges exactly when the matched BUY windows reach minCoTrades
    (coTradePairs already gates the pairs, so the gate is restated here in
    the rule text it prints).

Thresholds are plumbing only: a weight below a kind's threshold flips that
pair to merge=False in the decision record with a matching "< threshold"
rule, but no shipped caller passes anything besides the defaults - that is a
conscious choice, not a swept tau (recall-lift is unmeasurable at 6
clusters / 9 labels).
"""

from collections import defaultdict
from dataclasses import dataclass, field

from polycrawler.discovery.funding import TransferRow
from polycrawler.discovery.links import anchorPairs


# Strong money-flow kinds: the presence of a single edge is the merge signal.
STRONG_KINDS = (
    "direct",
    "sharedFunder",
    "sharedCashOut",
    "hop",
    "sharedOrigin",
    "originSibling",
)
CO_TRADE = "coTrade"
ALL_KINDS = STRONG_KINDS + (CO_TRADE,)


def defaultThresholds(minCoTrades: int) -> dict[str, int]:
    """Shipped merge thresholds: strong kinds 1 edge, coTrade minCoTrades."""
    thresholds = {kind: 1 for kind in STRONG_KINDS}
    thresholds[CO_TRADE] = minCoTrades
    return thresholds


@dataclass(frozen=True)
class EdgeEvidence:
    """One raw link edge, with the count of source records behind it."""

    kind: str
    left: str
    right: str
    evidence: int
    basis: str
    source: str


@dataclass(frozen=True)
class MergeDecision:
    """Per-pair merge decision: bridge or not, and under which rule."""

    kind: str
    left: str
    right: str
    evidence: int
    merge: bool
    rule: str


@dataclass
class MergePlan:
    """Everything buildFundingClusters needs to merge and to score parents."""

    edges: list[EdgeEvidence]
    decisions: list[MergeDecision]
    byFunder: dict[str, set[str]] = field(default_factory=dict)
    reached: dict[str, set[str]] = field(default_factory=dict)


def buildEdges(
    usable: list[TransferRow],
    accounts: set[str],
    blocked: set[str],
    eoaFunders: set[str],
    grandparents: dict[str, set[str]],
    originGroups: dict[str, set[str]],
    siblingGroups: dict[str, set[str]],
    coTrades: list[tuple[str, str]] | list[tuple[str, str, int]] | None,
    fundingHops: int,
    minCoTrades: int,
) -> tuple[list[EdgeEvidence], dict[str, set[str]], dict[str, set[str]]]:
    """Collect evidence edges in the exact order buildFundingClusters used to
    union them: direct transfers, sharedFunder, sharedCashOut, hop,
    sharedOrigin, originSibling, coTrade. Also returns byFunder and the hop
    `reached` map, which parent scoring still reads."""
    edges: list[EdgeEvidence] = []
    byFunder: dict[str, set[str]] = defaultdict(set)
    funderRows: dict[str, int] = defaultdict(int)
    byCashAll: dict[str, set[str]] = defaultdict(set)
    cashOutRows: dict[str, int] = defaultdict(int)
    directCounts: dict[tuple[str, str], int] = {}
    directOrder: list[tuple[str, str]] = []

    for row in usable:
        if row.toAddr in accounts and row.fromAddr not in blocked:
            byFunder[row.fromAddr].add(row.toAddr)
            funderRows[row.fromAddr] += 1
        if (
            row.fromAddr in accounts
            and row.toAddr not in accounts
            and row.toAddr not in blocked
        ):
            byCashAll[row.toAddr].add(row.fromAddr)
            cashOutRows[row.toAddr] += 1
        if row.fromAddr in accounts and row.toAddr in accounts:
            pair = (row.fromAddr, row.toAddr)
            if pair in directCounts:
                directCounts[pair] += 1
            else:
                directCounts[pair] = 1
                directOrder.append(pair)
    for left, right in directOrder:
        edges.append(
            EdgeEvidence(
                "direct",
                left,
                right,
                directCounts[(left, right)],
                "collateral transfers between the pair",
                "",
            )
        )

    # Groups are walked in insertion order (transfer order), exactly like the
    # old linkGroup loops, so pair ordering is reproducible.
    for funder, accountsLegs in byFunder.items():
        volume = funderRows[funder]
        for anchor, member in anchorPairsByGroup(funder, accountsLegs, accounts):
            edges.append(
                EdgeEvidence(
                    "sharedFunder",
                    anchor,
                    member,
                    volume,
                    "collateral transfer legs from the funder",
                    funder,
                )
            )
    for cashOut, accountsLegs in byCashAll.items():
        volume = cashOutRows[cashOut]
        for anchor, member in anchorPairsByGroup(cashOut, accountsLegs, accounts):
            edges.append(
                EdgeEvidence(
                    "sharedCashOut",
                    anchor,
                    member,
                    volume,
                    "collateral transfer legs into the cash-out",
                    cashOut,
                )
            )

    reached: dict[str, set[str]] = defaultdict(set)
    hopLegs: dict[str, int] = defaultdict(int)
    if fundingHops >= 2:
        for funder, accountsLegs in byFunder.items():
            if funder not in eoaFunders:
                continue
            for grand in grandparents.get(funder, ()):
                if grand in blocked or grand == funder:
                    continue
                hopLegs[grand] += 1
                for account in accountsLegs:
                    if account in accounts:
                        reached[grand].add(account)
        for grand, group in reached.items():
            legs = hopLegs[grand]
            members = sorted(account for account in group if account in accounts)
            for member in members[1:]:
                edges.append(
                    EdgeEvidence(
                        "hop",
                        members[0],
                        member,
                        legs,
                        "EOA hop legs (funder -> grandparent) behind the group",
                        grand,
                    )
                )

    for origin, group in originGroups.items():
        for anchor, member in anchorPairsByGroup(origin, group, accounts):
            edges.append(
                EdgeEvidence(
                    "sharedOrigin",
                    anchor,
                    member,
                    1,
                    "shared funding-origin address",
                    origin,
                )
            )
    for origin, group in siblingGroups.items():
        for anchor, member in anchorPairsByGroup(origin, group, accounts):
            edges.append(
                EdgeEvidence(
                    "originSibling",
                    anchor,
                    member,
                    1,
                    "accounts minted by the same origin",
                    origin,
                )
            )

    for item in coTrades or []:
        left, right = str(item[0]).lower(), str(item[1]).lower()
        if left not in accounts or right not in accounts or left == right:
            # Old behaviour silently skipped these; there is no edge to audit.
            continue
        windows = int(item[2]) if len(item) > 2 else minCoTrades
        edges.append(
            EdgeEvidence(
                "coTrade",
                left,
                right,
                windows,
                "matched BUY windows",
                "",
            )
        )
    return edges, byFunder, reached


def anchorPairsByGroup(
    source: str, group: set[str], accounts: set[str]
) -> list[tuple[str, str]]:
    """Anchor pairs over one group (single-source variant of links.anchorPairs:
    anchor = alphabetically first member, paired against every later member)."""
    members = sorted(account for account in group if account in accounts)
    return [(members[0], member) for member in members[1:]]


def planMerges(
    edges: list[EdgeEvidence], thresholds: dict[str, int]
) -> list[MergeDecision]:
    """Per-edge decision: merge iff evidence clears the kind's threshold.

    FAIL-CLOSED gate: every edge kind must have an explicit threshold in the
    dict — a missing key raises ValueError instead of silently defaulting to
    1 (fail-open would let an unknown/untuned kind merge freely). The shipped
    defaultThresholds() fills all seven kinds, and an explicit dict overrides
    a kind's default wholesale (coTrade's threshold replaces minCoTrades).

    The rule text is the printable audit gate: strong money-flow kinds merge
    at >= 1 edge, coTrade at >= minCoTrades matched windows."""
    decisions: list[MergeDecision] = []
    for edge in edges:
        try:
            threshold = thresholds[edge.kind]
        except KeyError:
            raise ValueError(
                f"no threshold for edge kind {edge.kind!r}: fail-closed, "
                f"pass {list(ALL_KINDS)} (see defaultThresholds)"
            ) from None
        merge = edge.evidence >= threshold
        operator = ">=" if merge else "<"
        decisions.append(
            MergeDecision(
                kind=edge.kind,
                left=edge.left,
                right=edge.right,
                evidence=edge.evidence,
                merge=merge,
                rule=(
                    f"{edge.kind} {edge.basis} {edge.evidence} "
                    f"{operator} threshold {threshold} "
                    f"(edge count by {edge.basis})"
                ),
            )
        )
    return decisions


def mergePlan(
    usable: list[TransferRow],
    accounts: set[str],
    blocked: set[str],
    eoaFunders: set[str],
    grandparents: dict[str, set[str]],
    originGroups: dict[str, set[str]] | None,
    siblingGroups: dict[str, set[str]] | None,
    coTrades: list[tuple[str, str]] | list[tuple[str, str, int]] | None,
    fundingHops: int,
    minCoTrades: int,
    thresholds: dict[str, int] | None = None,
) -> MergePlan:
    """Edges + decisions for buildFundingClusters. `thresholds=None` uses the
    shipped defaults, which reproduce the unconditional-merge semantics."""
    edges, byFunder, reached = buildEdges(
        usable,
        accounts,
        blocked,
        eoaFunders,
        grandparents,
        originGroups or {},
        siblingGroups or {},
        coTrades,
        fundingHops,
        minCoTrades,
    )
    if thresholds is None:
        thresholds = defaultThresholds(minCoTrades)
    return MergePlan(
        edges=edges,
        decisions=planMerges(edges, thresholds),
        byFunder=byFunder,
        reached=reached,
    )
