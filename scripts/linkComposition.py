"""Cluster composition audit: does a NEW discovery snapshot keep every
baseline funding cluster whole after the mergeScores refactor?

Baseline = a discovery snapshot already on disk (parents.parquet +
clusterAccounts.parquet, READ-ONLY; `pc2 discover` and `pc2 funding` both
write those two files into `config.fetch.dataDir`). New = the engine's
funding stage re-executed inside a TEMP-COPY of that data dir -- the real
data dir is never written to. The etherscan/relay caches ride along so a
no-op replay is fully cache-served (offline when nothing changed).
HONESTY NOTE on that claim: ALCHEMY_API_KEY is deliberately dropped from the
environment for the replay, so no live Alchemy calls can happen — the run is
cache-served or it fails. A no-CACHE replay (cache misses the addresses it
needs) makes real authenticated Etherscan calls and fails fast with
RuntimeError("ETHERSCAN_API_KEY is not set") when that key is absent.

Per config the report carries:
  * old -> new clusterId mapping (accounts present in both snapshots)
  * spread of each old cluster = how many new ids its old accounts settle in
  * false-split detection: any old cluster spreading over >= 2 new ids
  * false-fusion detection: prior-old clusters, any two of which now share
    one new id
  * parent-label delta (old parent string of each mapped old cluster vs the
    parent of the new cluster it overlaps most, by shared accounts)
  * member-count delta by evidence type (direct, sharedFunder, sharedCashOut,
    hop, sharedOrigin, originSibling, coTrade, funded)
  * clusterAlreadyCopied count: member rows pulled in under a parent label
    (linkType is exactly "funded"/"originSibling", i.e. copy rows, not edges)
  * pre-registered verdict rule: trade delta (coTrade-evidence member rows)
    <= +/-2  ->  "no demonstrable effect, keep default"

Run:
  uv run python scripts/linkComposition.py --config configs/insiderCases.yaml
      --data-dir data            (ETHERSCAN_API_KEY must be set; caches make
                                  a no-op replay offline)
  --data-dir overrides the baseline dir; --config must be the config the
  baseline snapshot was produced WITH (its splitDate gates both the funding
  uses and the coTrade windows).
"""

import argparse
import itertools
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import polars as pl

from polycrawler.config import loadConfig
from polycrawler.discovery import runFunding

# Edge kinds plus the two copy labels ("funded" pool rows and "originSibling"
# siblingExtra rows) that appear in the linkType column of member rows.
EVIDENCE_KINDS = (
    "direct",
    "sharedFunder",
    "sharedCashOut",
    "hop",
    "sharedOrigin",
    "originSibling",
    "coTrade",
    "funded",
)
COPY_KINDS = {"funded"}
COPY_ONLY_KINDS = COPY_KINDS | {"originSibling"}
TRADE_KIND = "coTrade"
# Pre-registered: a coTrade-evidence member-count delta within +/-2 is noise;
# anything else is a demonstrable composition effect of the refactor.
TRADE_DELTA_TOLERANCE = 2

parentsSchema = {
    "parent": pl.String,
    "clusterId": pl.String,
    "accountCount": pl.Int64,
    "suspiciousCount": pl.Int64,
    "totalProfitUsd": pl.Float64,
    "firstSeen": pl.Datetime(time_unit="us", time_zone="UTC"),
    "linkTypes": pl.String,
}
clusterAccountSchema = {
    "clusterId": pl.String,
    "account": pl.String,
    "linkType": pl.String,
}


def loadSnapshot(dir_: str | Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """parents.parquet + clusterAccounts.parquet from a snapshot dir."""
    base = Path(dir_)
    parents = pl.read_parquet(base / "parents.parquet").select(list(parentsSchema))
    members = pl.read_parquet(base / "clusterAccounts.parquet").select(
        list(clusterAccountSchema)
    )
    return parents, members


def parentById(parents: pl.DataFrame) -> dict[str, str]:
    return {
        str(row["clusterId"]): str(row["parent"])
        for row in parents.iter_rows(named=True)
    }


def accountMap(members: pl.DataFrame) -> dict[str, str]:
    """account -> clusterId over component rows (any linkType, incl. copies)."""
    return {str(row["account"]): str(row["clusterId"]) for row in
            members.iter_rows(named=True)}


def linkKinds(members: pl.DataFrame) -> dict[str, set[str]]:
    return {
        str(row["account"]): {part for part in str(row["linkType"]).split(",") if part}
        for row in members.iter_rows(named=True)
    }


def kindCounts(members: pl.DataFrame) -> dict[str, int]:
    """Rows carrying each evidence kind, counted from the linkType comma list."""
    counts = {kind: 0 for kind in EVIDENCE_KINDS}
    for row in members.iter_rows(named=True):
        kinds = {part for part in str(row["linkType"]).split(",") if part}
        for kind in kinds:
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def copiedCount(members: pl.DataFrame) -> int:
    """Rows pulled in under a parent label: sole linkType funded/originSibling."""
    count = 0
    for row in members.iter_rows(named=True):
        kinds = {part for part in str(row["linkType"]).split(",") if part}
        if kinds and kinds <= COPY_ONLY_KINDS:
            count += 1
    return count


def compare(
    oldParents: pl.DataFrame,
    oldMembers: pl.DataFrame,
    newParents: pl.DataFrame,
    newMembers: pl.DataFrame,
) -> dict:
    """Cluster composition old vs new, from the member/parent rows only."""
    oldIds = sorted({str(cid) for cid in oldMembers["clusterId"].drop_nulls().to_list()})
    newIds = sorted({str(cid) for cid in newMembers["clusterId"].drop_nulls().to_list()})
    oldOf = accountMap(oldMembers)
    newOf = accountMap(newMembers)
    oldParent = parentById(oldParents)
    newParent = parentById(newParents)
    shared = {row["account"] for row in oldMembers.iter_rows(named=True)} & {
        row["account"] for row in newMembers.iter_rows(named=True)
    }

    # old -> new mapping + spread, over the accounts both snapshots contain
    mapping: dict[str, list[str]] = {oldId: [] for oldId in oldIds}
    for account in shared:
        target = newOf[account]
        if target not in mapping[oldOf[account]]:
            mapping[oldOf[account]].append(target)
    mapping = {oldId: sorted(targets) for oldId, targets in mapping.items()}
    spread = {oldId: len(targets) for oldId, targets in mapping.items()}
    falseSplits = {
        oldId: targets for oldId, targets in mapping.items() if len(targets) >= 2
    }
    unmappedOld = sorted(oldId for oldId, targets in mapping.items() if not targets)
    freshNew = sorted(
        newId for newId in newIds
        if newId not in {target for targets in mapping.values() for target in targets}
    )

    # false fusion: a new cluster that contains accounts from >= 2 old clusters
    oldSets: dict[str, set[str]] = {}
    for account in shared:
        oldSets.setdefault(newOf[account], set()).add(oldOf[account])
    falseFusions = [
        {"newId": newId, "oldIds": sorted(olds)}
        for newId, olds in sorted(oldSets.items())
        if len(olds) >= 2
    ]
    falseFusionPairs = []
    for fusion in falseFusions:
        for left, right in itertools.combinations(fusion["oldIds"], 2):
            falseFusionPairs.append([left, right])

    # parent-label delta: dominant new cluster of each old cluster (most
    # shared accounts, ties -> smallest newId)
    overlaps: dict[str, dict[str, int]] = {}
    for account in shared:
        overlaps.setdefault(oldOf[account], {}).setdefault(newOf[account], 0)
        overlaps[oldOf[account]][newOf[account]] += 1
    parentDeltas = []
    for oldId, counts in sorted(overlaps.items()):
        best = min(counts, key=lambda cid: (-counts[cid], cid))
        if oldParent.get(oldId) != newParent.get(best):
            parentDeltas.append(
                {
                    "clusterId": oldId,
                    "oldParent": oldParent.get(oldId),
                    "newId": best,
                    "newParent": newParent.get(best),
                    "sharedAccounts": counts[best],
                }
            )

    oldKind = kindCounts(oldMembers)
    newKind = kindCounts(newMembers)
    deltas = {
        kind: {
            "old": oldKind.get(kind, 0),
            "new": newKind.get(kind, 0),
            "delta": newKind.get(kind, 0) - oldKind.get(kind, 0),
        }
        for kind in sorted(set(oldKind) | set(newKind))
    }
    clusterAlreadyCopied = {
        "old": copiedCount(oldMembers),
        "new": copiedCount(newMembers),
        "delta": copiedCount(newMembers) - copiedCount(oldMembers),
    }
    return {
        "clusters": {"old": len(oldIds), "new": len(newIds)},
        "mapping": mapping,
        "spread": spread,
        "falseSplits": falseSplits,
        "falseFusions": falseFusions,
        "falseFusionPairs": [list(pair) for pair in falseFusionPairs],
        "unmappedOld": unmappedOld,
        "freshNew": freshNew,
        "parentLabelDelta": parentDeltas,
        "memberCountDeltaByEvidenceType": deltas,
        "clusterAlreadyCopied": clusterAlreadyCopied,
        "tradeDelta": deltas[TRADE_KIND]["delta"],
        "verdict": verdict(deltas[TRADE_KIND]["delta"], falseSplits, falseFusions),
    }


def verdict(tradeDelta: int, falseSplits: dict, falseFusions: list) -> str:
    if falseSplits or falseFusions:
        return "composition changed (split/fusion detected)"
    if abs(tradeDelta) <= TRADE_DELTA_TOLERANCE:
        return "no demonstrable effect, keep default"
    return f"trade delta {tradeDelta} exceeds +/-{TRADE_DELTA_TOLERANCE}"


def stageSnapshot(src: str | Path, dst: str | Path) -> None:
    """Copy the pieces runFunding reads (and its caches) into a temp dir."""
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("suspicious.parquet", "fills.parquet"):
        path = Path(src) / name
        if path.exists():
            shutil.copy2(path, dst / name)
    for kind in ("etherscan", "relay"):
        kindDir = Path(src) / "raw" / kind
        if kindDir.is_dir():
            shutil.copytree(kindDir, dst / "raw" / kind)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="cluster composition audit old vs new discovery snapshot"
    )
    parser.add_argument("--config", default="configs/base.yaml")
    parser.add_argument(
        "--data-dir", default=None,
        help="baseline snapshot dir (read-only); default config.fetch.dataDir",
    )
    parser.add_argument("--tmp-root", default=None)
    args = parser.parse_args()
    t0 = time.time()
    # The tool must never depend on cwd: the default snapshot dir (and a
    # relative dataDir from the config) is anchored at the repository root.
    repoRoot = Path(__file__).resolve().parents[1]
    if args.data_dir:
        dataDir: Path = Path(args.data_dir)
    else:
        dataDir = repoRoot / "data"
    oldParents, oldMembers = loadSnapshot(dataDir)
    tmp = Path(tempfile.mkdtemp(prefix="linkcomp-", dir=args.tmp_root))
    savedAlchemy = os.environ.pop("ALCHEMY_API_KEY", None)
    try:
        cfg = loadConfig(args.config)
        if args.data_dir:
            source = dataDir
        else:
            source = Path(cfg.fetch.dataDir)
            if not source.is_absolute():
                source = repoRoot / source
        stageSnapshot(source, tmp)
        print(f"temp snapshot {tmp} ({time.time() - t0:.0f}s)", flush=True)
        frozen = cfg.model_copy(deep=True)
        frozen.fetch.dataDir = str(tmp)
        runFunding(frozen, refresh=False)
        newParents, newMembers = loadSnapshot(tmp)
        report = compare(oldParents, oldMembers, newParents, newMembers)
        print(json.dumps(report, indent=2, default=str))
        print(f"verdict: {report['verdict']}")
        print(f"({time.time() - t0:.0f}s)")
    finally:
        if savedAlchemy is not None:
            os.environ["ALCHEMY_API_KEY"] = savedAlchemy
        # The staged snapshot is a full raw/etherscan + raw/relay copy
        # (hundreds of MB): always clean it up, even on failure.
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
