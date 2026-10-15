"""Tests for engineParity residual-bucket set math and the hardened
entrySweep fingerprint (mtime + row counts must invalidate the cache)."""

import importlib.util
import os
import sys
import time
from pathlib import Path

import polars as pl

RESEARCH = Path(__file__).resolve().parents[1] / "scripts" / "research"


def _load(name: str, moduleKey: str):
    spec = importlib.util.spec_from_file_location(moduleKey, RESEARCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[moduleKey] = module
    spec.loader.exec_module(module)
    return module


ep = _load("engineParity", "engineParityTest")
esw = _load("entrySweep", "entrySweepFingerprintTest")

PICK = lambda a, m="0xm", o="Yes": (a, m, o)


def test_residual_buckets_cover_each_class():
    finalPicks = [
        PICK("0xexec"),    # engine copied it -> overlap
        PICK("0xclust"),   # a sibling's copy covers it -> clusterAlreadyCopied
        PICK("0xprefix"),  # legal running prefix, never executed -> notExecutedLegalPrefix
        PICK("0xorph"),    # no legal prefix at all -> noLegalPrefix
    ]
    executedKeys = {PICK("0xexec"), PICK("0xdrift")}  # 0xdrift entered on a
    # legal running prefix whose final burst average drifted past the gate
    prefixKeys = {PICK("0xprefix"), PICK("0xdrift")}
    executedGroups = {
        ("0xcluster0", "0xm", "Yes"),  # the cluster copy that covers 0xclust
        ("0xexec", "0xm", "Yes"),
        ("0xother", "0xn", "No"),
    }
    clusterMap = {"0xclust": "0xcluster0", "0xcluster0": "0xcluster0"}
    buckets = ep.residualBuckets(finalPicks, executedKeys, prefixKeys, executedGroups, clusterMap)
    assert buckets["overlap"] == 1
    assert buckets["enginePrefixDrift"] == 1  # drift is a count (engine-only keys)
    assert buckets["clusterAlreadyCopied"] == [PICK("0xclust")]
    assert buckets["notExecutedLegalPrefix"] == [PICK("0xprefix")]
    assert buckets["noLegalPrefix"] == [PICK("0xorph")]


def test_residual_buckets_group_lookup_falls_back_to_account():
    finalPicks = [PICK("0xsolo")]
    executedGroups = {("0xsolo", "0xm", "Yes")}  # engine recorded the copy under the account
    buckets = ep.residualBuckets(finalPicks, executedKeys=set(), prefixKeys=set(),
                                 executedGroups=executedGroups, clusterMap={})
    assert buckets["clusterAlreadyCopied"] == [PICK("0xsolo")]


def _write_inputs(d: Path, rowsFills: int, rowsMarkets: int) -> None:
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"fill": range(rowsFills)}).write_parquet(d / "fills.parquet")
    pl.DataFrame({"market": range(rowsMarkets)}).write_parquet(d / "markets.parquet")


def test_fingerprint_changes_with_row_count_at_equal_size_and_mtime(tmp_path):
    a = tmp_path / "a"
    _write_inputs(a, 1000, 10)
    fp0 = esw.dataFingerprint([str(a)])
    # A stale-looking rewrite: same dir, same mtime, but a different row count
    # carried in the parquet metadata -> the row count must flip the fingerprint.
    _write_inputs(a, 2000, 10)
    ns = (a / "fills.parquet").stat().st_mtime_ns + 1
    os.utime(a / "fills.parquet", ns=(ns, ns))
    fp1 = esw.dataFingerprint([str(a)])
    assert fp0 != fp1
    assert len(fp1) == 10  # same digest length, new recipe


def test_fingerprint_changes_with_mtime_at_equal_size(tmp_path):
    a = tmp_path / "a"
    _write_inputs(a, 1000, 10)
    fp0 = esw.dataFingerprint([str(a)])
    # identical row count, identical size, only mtime moves -> cache must miss
    _write_inputs(a, 1000, 10)
    ns = (a / "fills.parquet").stat().st_mtime_ns + 1
    os.utime(a / "fills.parquet", ns=(ns, ns))
    fp1 = esw.dataFingerprint([str(a)])
    assert fp0 != fp1


def test_cache_file_name_carries_schema_version(tmp_path):
    a = tmp_path / "a"
    _write_inputs(a, 5, 2)
    expected = (esw.CACHE_DIR /
                f"entries_v{esw.CACHE_SCHEMA_VERSION}_{esw.dataFingerprint([str(a)])}.parquet")
    assert esw.CACHE_SCHEMA_VERSION == 2
    assert "entries_v2_" in expected.name


def test_rows_metadata_only_is_cheap(tmp_path):
    a = tmp_path / "a"
    _write_inputs(a, 200000, 3)
    start = time.perf_counter()
    assert esw._rows(a / "fills.parquet") == 200000
    assert time.perf_counter() - start < 1.0  # footer read, not a row scan
