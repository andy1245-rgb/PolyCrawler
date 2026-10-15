"""Tests for the orderBurstMonitor day-list and progress helpers."""

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "mon", Path(__file__).resolve().parents[1] / "scripts" / "research" / "orderBurstMonitor.py"
)
mon = importlib.util.module_from_spec(spec)
sys.modules["mon"] = mon
spec.loader.exec_module(mon)


def _isolatePlan(monkeypatch, tmp_path):
    """Point the monitor's plan file at an absent path so the tests exercise
    the sampleDays() fallback (the runtime file is data-driven)."""
    monkeypatch.setattr(mon, "PLAN_PATH", tmp_path / "absent-samplePlan.json")


def test_plan_days_is_the_pullers_own_plan(monkeypatch, tmp_path):
    # The monitor must derive the plan from orderBurstOnchain.sampleDays, not
    # restate it: same months, same per-month count, deterministic, and with
    # the days that have not yet elapsed filtered out ("complete" = all
    # OBSERVED days cached, never a future day).
    _isolatePlan(monkeypatch, tmp_path)
    full = mon.samplePlanDays(2)
    expected = mon.PULLER.sampleDays(
        (mon.PULLER.SAMPLE_START.year, mon.PULLER.SAMPLE_START.month), 2)
    assert full == expected
    today = datetime.now(timezone.utc).date()
    assert mon.planDays(2) == [d for d in full if d < today]
    assert full == sorted(full)
    # Pinned sampling contract, recorded at commit time from
    # PULLER.sampleDays((2023, 10), 2, seed=7). If a sampling-contract change
    # moves this, the diff shows up here for review.
    assert full[0] == date(2023, 10, 11)


def test_sample_plan_file_wins_over_recomputation(monkeypatch, tmp_path):
    # When the puller has written samplePlan.json, the monitor reads the
    # actual plan instead of recomputing it (a plan the puller itself pinned).
    plan = tmp_path / "samplePlan.json"
    plan.write_text('["2024-01-05", "2024-01-19"]')
    monkeypatch.setattr(mon, "PLAN_PATH", plan)
    assert mon.samplePlanDays() == [date(2024, 1, 5), date(2024, 1, 19)]
    assert mon.planDays() == mon.samplePlanDays()


def test_future_and_today_days_never_enter_the_wait_list(monkeypatch, tmp_path):
    # regression: future days made "complete" unreachable mid-month (monitor
    # timeouts forever); today and later must be dropped.
    _isolatePlan(monkeypatch, tmp_path)
    today = datetime.now(timezone.utc).date()
    assert all(d < today for d in mon.planDays())


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
