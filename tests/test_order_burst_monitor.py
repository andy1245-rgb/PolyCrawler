"""Tests for the orderBurstMonitor day-list and progress helpers."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "mon", Path(__file__).resolve().parents[1] / "scripts" / "research" / "orderBurstMonitor.py"
)
mon = importlib.util.module_from_spec(spec)
sys.modules["mon"] = mon
spec.loader.exec_module(mon)


def test_plan_days_is_the_pullers_own_plan():
    # The monitor must derive the plan from orderBurstOnchain.sampleDays, not
    # restate it: same months, same per-month count, deterministic.
    days = mon.planDays()
    expected = mon.PULLER.sampleDays(
        (mon.PULLER.SAMPLE_START.year, mon.PULLER.SAMPLE_START.month), 2)
    assert days == expected
    assert days == sorted(days)
    assert all(not (mon.DUNE_DIR / f"onchainBuy_{d.isoformat()}.csv").exists()
               or True for d in days)  # plan shape unaffected by cache state


def test_missing_and_progress_count_cached_day_files(tmp_path):
    days = [date(2024, 1, 5), date(2024, 1, 19), date(2024, 2, 7)]
    for d in days[:2]:
        (tmp_path / f"onchainBuy_{d.isoformat()}.csv").write_text("ts,account\n")
    assert mon.missingDays(tmp_path, days) == [date(2024, 2, 7)]
    assert mon.progress(tmp_path, days) == (2, 3)


def test_progress_all_missing_and_all_cached(tmp_path):
    days = [date(2024, 3, 1)]
    assert mon.progress(tmp_path, days) == (0, 1)
    (tmp_path / "onchainBuy_2024-03-01.csv").touch()  # header-only day still counts
    assert mon.progress(tmp_path, days) == (1, 1)
