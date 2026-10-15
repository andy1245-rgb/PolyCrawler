"""Cluster composition audit: split + fusion detection on scripted snapshots.

compare() never runs the engine; the snapshots are hand-built parents.parquet
/ clusterAccounts.parquet pairs in tmp dirs, so the audit logic is checked
against both failure modes it exists to catch (False splits by the refactor;
False fusions) and against the identity case the shipped mergeScores defaults
must reproduce (zero delta + the pre-registered verdict rule).
"""

import importlib.util
import sys
from pathlib import Path

import polars as pl

spec = importlib.util.spec_from_file_location(
    "linkcomp", Path(__file__).resolve().parents[1] / "scripts" / "linkComposition.py"
)
linkcomp = importlib.util.module_from_spec(spec)
sys.modules["linkcomp"] = linkcomp
spec.loader.exec_module(linkcomp)


def parentsFrame(rows: list[dict]) -> pl.DataFrame:
    frame = pl.DataFrame(
        [
            {
                "parent": row.get("parent", f"component:{row['clusterId']}"),
                "clusterId": row["clusterId"],
                "accountCount": row.get("accountCount", len(row.get("accounts", []))),
                "suspiciousCount": row.get("suspiciousCount", 2),
                "totalProfitUsd": row.get("totalProfitUsd", 0.0),
                "firstSeen": row.get("firstSeen", None),
                "linkTypes": row.get("linkTypes", "coTrade"),
            }
            for row in rows
        ],
        schema=linkcomp.parentsSchema,
    )
    return frame


def memberRows(clusterId: str, accounts: list[str]) -> list[dict]:
    return [
        {"clusterId": clusterId, "account": account, "linkType": "direct"}
        for account in accounts
    ]


def membersFrame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=linkcomp.clusterAccountSchema)


def writeSnapshot(path: Path, parents: list[dict], rows: list[dict]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    parentsFrame(parents).write_parquet(path / "parents.parquet")
    membersFrame(rows).write_parquet(path / "clusterAccounts.parquet")


def testIdenticalSnapshotsDetectNothingAndKeepDefault() -> None:
    parents = [{"clusterId": "0xaaa", "linkTypes": "coTrade"}]
    members = memberRows("0xaaa", ["0x1", "0x2"])
    oldP, oldM = parentsFrame(parents), membersFrame(members)
    newP, newM = parentsFrame(parents), membersFrame(members)
    report = linkcomp.compare(oldP, oldM, newP, newM)
    assert report["clusters"] == {"old": 1, "new": 1}
    assert report["mapping"] == {"0xaaa": ["0xaaa"]}
    assert all(v == 1 for v in report["spread"].values())
    assert report["falseSplits"] == {}
    assert report["falseFusions"] == [] and report["falseFusionPairs"] == []
    assert report["unmappedOld"] == [] and report["freshNew"] == []
    assert report["parentLabelDelta"] == []
    assert report["tradeDelta"] == 0
    assert report["verdict"] == "no demonstrable effect, keep default"


def testScriptedSplitDetected() -> None:
    # baseline cluster {0x1,0x2,0x3}; the new snapshot splits 0x3 away
    oldP = parentsFrame([{"clusterId": "0xaaa", "linkTypes": "coTrade"}])
    oldM = membersFrame(memberRows("0xaaa", ["0x1", "0x2", "0x3"]))
    newP = parentsFrame(
        [
            {"clusterId": "0x1", "linkTypes": "coTrade"},
            {"clusterId": "0x3", "linkTypes": "coTrade"},
        ]
    )
    newM = membersFrame(
        memberRows("0x1", ["0x1", "0x2"]) + memberRows("0x3", ["0x3"])
    )
    report = linkcomp.compare(oldP, oldM, newP, newM)
    assert report["falseSplits"] == {"0xaaa": ["0x1", "0x3"]}
    assert report["spread"]["0xaaa"] == 2
    assert report["falseFusions"] == []
    # the split also shifts the dominant overlap: parent label differs
    assert report["parentLabelDelta"] == [
        {
            "clusterId": "0xaaa",
            "oldParent": "component:0xaaa",
            "newId": "0x1",
            "newParent": "component:0x1",
            "sharedAccounts": 2,
        }
    ]
    assert report["clusters"] == {"old": 1, "new": 2}
    assert report["verdict"] == "composition changed (split/fusion detected)"


def testScriptedFusionDetected() -> None:
    # baseline {0x1,0x2} and {0x3,0x4}; the new snapshot fuses all four
    oldP = parentsFrame(
        [
            {"clusterId": "0x1", "linkTypes": "coTrade"},
            {"clusterId": "0x3", "linkTypes": "coTrade"},
        ]
    )
    oldM = membersFrame(
        memberRows("0x1", ["0x1", "0x2"]) + memberRows("0x3", ["0x3", "0x4"])
    )
    newP = parentsFrame([{"clusterId": "0x1", "linkTypes": "coTrade"}])
    newM = membersFrame(memberRows("0x1", ["0x1", "0x2", "0x3", "0x4"]))
    report = linkcomp.compare(oldP, oldM, newP, newM)
    assert report["falseFusionPairs"] == [["0x1", "0x3"]]
    assert report["falseFusions"] == [{"newId": "0x1", "oldIds": ["0x1", "0x3"]}]
    assert report["falseSplits"] == {}
    assert report["mapping"] == {"0x1": ["0x1"], "0x3": ["0x1"]}
    # the fused new cluster swallows the old 0x3 label: parent-label delta on
    # the absorbed old cluster only
    deltaByOld = {row["clusterId"]: row for row in report["parentLabelDelta"]}
    assert "0x3" in deltaByOld and "0x1" not in deltaByOld
    assert report["verdict"] == "composition changed (split/fusion detected)"


def testParentLabelDeltaCountsRenamedParents() -> None:
    # identical membership but the funding parent relabels 0x3 in {0x3,0x4}
    oldP = parentsFrame([{"clusterId": "0x3", "parent": "0xfunder"}])
    oldM = membersFrame(memberRows("0x3", ["0x3", "0x4"]))
    newP = parentsFrame([{"clusterId": "0x4", "parent": "0xother"}])
    newM = membersFrame(memberRows("0x4", ["0x3", "0x4"]))
    report = linkcomp.compare(oldP, oldM, newP, newM)
    assert report["mapping"] == {"0x3": ["0x4"]}
    assert report["falseSplits"] == {} and report["falseFusions"] == []
    assert report["parentLabelDelta"] == [
        {
            "clusterId": "0x3",
            "oldParent": "0xfunder",
            "newId": "0x4",
            "newParent": "0xother",
            "sharedAccounts": 2,
        }
    ]
    # no composition change and no trade delta: keep default
    assert report["verdict"] == "no demonstrable effect, keep default"


def testMemberCountDeltaByEvidenceTypeAndTradeVerdict() -> None:
    oldP = parentsFrame([{"clusterId": "0xaaa", "linkTypes": "coTrade"}])
    oldM = membersFrame(
        memberRows("0xaaa", ["0x1", "0x2"])
        + [{"clusterId": "0xaaa", "account": "0x9", "linkType": "funded"}]
    )
    newP = parentsFrame([{"clusterId": "0xaaa", "linkTypes": "coTrade"}])
    newM = membersFrame(
        memberRows("0xaaa", ["0x1", "0x2", "0x3", "0x4"])
        + [
            {"clusterId": "0xaaa", "account": "0x8", "linkType": "originSibling"},
            {"clusterId": "0xaaa", "account": "0x9", "linkType": "funded"},
        ]
    )
    report = linkcomp.compare(oldP, oldM, newP, newM)
    deltas = report["memberCountDeltaByEvidenceType"]
    assert deltas["direct"] == {"old": 2, "new": 4, "delta": 2}
    assert deltas["funded"] == {"old": 1, "new": 1, "delta": 0}
    assert deltas["originSibling"] == {"old": 0, "new": 1, "delta": 1}
    assert report["clusterAlreadyCopied"] == {"old": 1, "new": 2, "delta": 1}
    assert report["tradeDelta"] == 0
    assert report["verdict"] == "no demonstrable effect, keep default"

    # a coTrade member-row swing beyond the tolerance flips the verdict even
    # though no cluster split or fused
    newTrade = membersFrame(
        memberRows("0xaaa", ["0x1", "0x2"])
        + [{"clusterId": "0xaaa", "account": "0x9", "linkType": "funded"}]
        + [
            {"clusterId": "0xaaa", "account": f"0xco{i}", "linkType": "coTrade"}
            for i in range(3)
        ]
    )
    reportTrade = linkcomp.compare(oldP, oldM, newP, newTrade)
    assert reportTrade["tradeDelta"] == 3
    assert reportTrade["verdict"] == "trade delta 3 exceeds +/-2"
    assert reportTrade["falseSplits"] == {} and reportTrade["falseFusions"] == []


def testLoadSnapshotRoundTripsTmpScripts() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        snap = Path(root) / "snap"
        writeSnapshot(
            snap,
            [{"clusterId": "0xaaa", "linkTypes": "coTrade"}],
            memberRows("0xaaa", ["0x1", "0x2"]),
        )
        parents, members = linkcomp.loadSnapshot(snap)
        assert linkcomp.accountMap(members) == {"0x1": "0xaaa", "0x2": "0xaaa"}
        assert linkcomp.parentById(parents) == {"0xaaa": "component:0xaaa"}


def testStageSnapshotCopiesOnlyWhatRunFundingReads() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as root:
        src = Path(root) / "src"
        (src / "raw" / "etherscan").mkdir(parents=True)
        (src / "raw" / "relay").mkdir(parents=True)
        (src / "suspicious.parquet").write_text("parquet")
        (src / "fills.parquet").write_text("parquet")
        (src / "markets.parquet").write_text("unneeded")
        (src / "parents.parquet").write_text("unneeded")
        dst = Path(root) / "dst"
        linkcomp.stageSnapshot(src, dst)
        assert (dst / "suspicious.parquet").exists()
        assert (dst / "fills.parquet").exists()
        assert (dst / "raw" / "etherscan").is_dir()
        assert (dst / "raw" / "relay").is_dir()
        assert not (dst / "markets.parquet").exists()
        assert not (dst / "parents.parquet").exists()
