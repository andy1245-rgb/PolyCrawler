from collections import defaultdict
from datetime import datetime
from typing import Any

import polars as pl

from polycrawler.discovery.funding import TransferRow


def anchorPairs(groups: dict[str, set[str]], accounts: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for group in groups.values():
        members = sorted(account for account in group if account in accounts)
        if len(members) < 2:
            continue
        for other in members[1:]:
            pairs.append((members[0], other))
    return pairs


def transferGroups(
    usable: list[TransferRow],
    accounts: set[str],
    blocked: set[str],
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[tuple[str, str]]]:
    byFunder: dict[str, set[str]] = defaultdict(set)
    byCashOut: dict[str, set[str]] = defaultdict(set)
    direct: list[tuple[str, str]] = []
    for row in usable:
        if row.toAddr in accounts and row.fromAddr not in blocked:
            byFunder[row.fromAddr].add(row.toAddr)
        if row.fromAddr in accounts and row.toAddr not in accounts and row.toAddr not in blocked:
            byCashOut[row.toAddr].add(row.fromAddr)
        if row.fromAddr in accounts and row.toAddr in accounts:
            direct.append((row.fromAddr, row.toAddr))
    return byFunder, byCashOut, direct


def sharedFunderPairs(byFunder: dict[str, set[str]], accounts: set[str]) -> list[tuple[str, str]]:
    return anchorPairs(byFunder, accounts)


def sharedCashOutPairs(byCashOut: dict[str, set[str]], accounts: set[str]) -> list[tuple[str, str]]:
    return anchorPairs(byCashOut, accounts)


def directTransferPairs(direct: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(direct)


def hopLinks(
    byFunder: dict[str, set[str]],
    eoaFunders: set[str],
    grandparents: dict[str, set[str]],
    blocked: set[str],
    accounts: set[str],
) -> tuple[list[tuple[str, str]], dict[str, set[str]]]:
    reached: dict[str, set[str]] = defaultdict(set)
    for funder, group in byFunder.items():
        if funder not in eoaFunders:
            continue
        for grand in grandparents.get(funder, ()):
            if grand in blocked or grand == funder:
                continue
            for account in group:
                if account in accounts:
                    reached[grand].add(account)
    return anchorPairs(reached, accounts), reached


def sharedOriginPairs(originGroups: dict[str, set[str]], accounts: set[str]) -> list[tuple[str, str]]:
    return anchorPairs(originGroups, accounts)


def originSiblingPairs(siblingGroups: dict[str, set[str]], accounts: set[str]) -> list[tuple[str, str]]:
    return anchorPairs(siblingGroups, accounts)


def matchTimes(left: list[Any], right: list[Any], windowSec: int) -> int:
    index = 0
    other = 0
    matched = 0
    while index < len(left) and other < len(right):
        delta = (left[index] - right[other]).total_seconds()
        if abs(delta) <= windowSec:
            matched += 1
            index += 1
            other += 1
        elif delta < 0:
            index += 1
        else:
            other += 1
    return matched


def coTradePairs(
    fills: pl.DataFrame,
    accounts: set[str],
    cutoff: datetime,
    windowSec: int,
    minCount: int,
    minMarkets: int = 1,
) -> list[tuple[str, str]]:
    if windowSec < 0 or minCount <= 0 or minMarkets <= 0 or len(accounts) < 2 or fills.height == 0:
        return []
    buys = fills.filter(
        (pl.col("side") == "BUY")
        & (pl.col("ts") < cutoff)
        & pl.col("account").is_in(list(accounts))
    )
    grouped: dict[tuple[str, str], dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for row in buys.select(["account", "marketId", "outcome", "ts"]).iter_rows(named=True):
        grouped[(row["marketId"], row["outcome"])][str(row["account"]).lower()].append(row["ts"])
    counts: dict[tuple[str, str], int] = defaultdict(int)
    markets: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, byAccount in grouped.items():
        names = sorted(byAccount)
        for index, left in enumerate(names):
            leftTimes = sorted(byAccount[left])
            for right in names[index + 1 :]:
                matched = matchTimes(leftTimes, sorted(byAccount[right]), windowSec)
                if matched:
                    counts[(left, right)] += matched
                    markets[(left, right)].add(key[0])
    return [
        pair
        for pair, count in sorted(counts.items())
        if count >= minCount and len(markets[pair]) >= minMarkets
    ]


def coTradeClusters(
    fills: pl.DataFrame,
    accounts: set[str],
    cutoff: datetime,
    windowSec: int,
    minCount: int,
    minMarkets: int,
) -> pl.DataFrame:
    schema = {
        "account": pl.String,
        "coTradeClusterId": pl.String,
        "coTradeClusterSize": pl.Int64,
    }
    pairs = coTradePairs(fills, accounts, cutoff, windowSec, minCount, minMarkets)
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        leftRoot, rightRoot = find(left), find(right)
        if leftRoot == rightRoot:
            return
        if leftRoot < rightRoot:
            parent[rightRoot] = leftRoot
        else:
            parent[leftRoot] = rightRoot

    for left, right in pairs:
        union(left, right)
    groups: dict[str, list[str]] = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    rows = []
    for group in groups.values():
        if len(group) < 2:
            continue
        clusterId = min(group)
        size = len(group)
        for account in group:
            rows.append(
                {"account": account, "coTradeClusterId": clusterId, "coTradeClusterSize": size}
            )
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema)
