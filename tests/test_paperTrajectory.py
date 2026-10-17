"""Tests for the paper trajectory append/report (synthetic open positions)."""

import csv
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ptraj", Path(__file__).resolve().parents[1] / "scripts" / "paperTrajectory.py"
)
ptraj = importlib.util.module_from_spec(spec)
sys.modules["ptraj"] = ptraj
spec.loader.exec_module(ptraj)

MARK_FIELDS = [
    "alertTs", "account", "eventSlug", "copiedOutcome", "burstUsd", "avgPrice",
    "entry", "mark", "openPnl", "spend", "shares", "valuedAt",
]


def writeOpen(root: Path, rows: list[dict]) -> None:
    live = root / "data" / "live"
    live.mkdir(parents=True)
    with (live / "openPositions.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MARK_FIELDS)
        w.writeheader()
        w.writerows(rows)


def readTraj(root: Path) -> list[dict]:
    with (root / "data" / "live" / "trajectory.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


OPEN_ROWS = [
    {
        "alertTs": "2026-10-14 23:43:32",
        "account": "0x93fb8127a1b21a112b11af936361225df0563e4a",
        "eventSlug": "will-the-us-invade-iran-before-2027",
        "copiedOutcome": "Yes",
        "burstUsd": "16358.22",
        "avgPrice": "0.18",
        "entry": "0.17",
        "mark": "0.155",
        "openPnl": "-8.82",
        "spend": "100.0",
        "shares": "588.24",
        "valuedAt": "2026-10-17T04:00:02+00:00",
    },
    {
        "alertTs": "2026-10-14 23:43:39",
        "account": "0x7f1842fefaf9d6254a98803337323361ffa5dc02",
        "eventSlug": "who-will-be-the-next-prime-minister-of-israel",
        "copiedOutcome": "Yes",
        "burstUsd": "5900.0",
        "avgPrice": "0.3418",
        "entry": "0.26",
        "mark": "0.295",
        "openPnl": "13.46",
        "spend": "100.0",
        "shares": "384.62",
        "valuedAt": "2026-10-17T04:00:02+00:00",
    },
]


def test_append_creates_file_with_header(tmp_path):
    writeOpen(tmp_path, OPEN_ROWS)
    appended, skipped = ptraj.appendTrajectory(tmp_path)
    assert appended == 2
    assert skipped == 0
    rows = readTraj(tmp_path)
    with (tmp_path / "data" / "live" / "trajectory.csv").open(newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ptraj.FIELDNAMES
    # short account form (0x + 8 hex), mark's valuedAt carried through
    assert rows[0]["account"] == "0x93fb8127"
    assert rows[0]["valuedAt"] == "2026-10-17T04:00:02+00:00"
    assert rows[0]["openPnl"] == "-8.82"
    assert rows[0]["date"]  # UTC date today, non-empty


def test_append_is_idempotent(tmp_path):
    writeOpen(tmp_path, OPEN_ROWS)
    ptraj.appendTrajectory(tmp_path)
    appended, skipped = ptraj.appendTrajectory(tmp_path)
    assert appended == 0
    assert skipped == 2
    assert len(readTraj(tmp_path)) == 2


def test_missing_input_is_quiet_zero(tmp_path):
    # no openPositions.csv at all: nothing written, exit-0 path
    assert ptraj.appendTrajectory(tmp_path) == (0, 0)
    assert not (tmp_path / "data" / "live" / "trajectory.csv").exists()


def test_header_only_input_is_noop(tmp_path):
    writeOpen(tmp_path, [])
    assert ptraj.appendTrajectory(tmp_path) == (0, 0)
    assert not (tmp_path / "data" / "live" / "trajectory.csv").exists()


def test_report_sums_per_date(tmp_path, capsys):
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True)
    with (live / "trajectory.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ptraj.FIELDNAMES)
        w.writeheader()
        w.writerows([
            {"date": "2026-10-16", "openPnl": "-8.82", "alertTs": "a",
             "account": "x", "eventSlug": "e"},
            {"date": "2026-10-17", "openPnl": "13.46", "alertTs": "b",
             "account": "x", "eventSlug": "e"},
            {"date": "2026-10-17", "openPnl": "-4.14", "alertTs": "c",
             "account": "y", "eventSlug": "f"},
        ])
    ptraj.report(tmp_path)
    out = capsys.readouterr().out
    assert "2026-10-16 n=1 pnl=-8.82" in out
    assert "2026-10-17 n=2 pnl=+9.32" in out


def test_report_without_file_is_quiet(tmp_path, capsys):
    ptraj.report(tmp_path)
    assert capsys.readouterr().out.strip() == "no trajectory yet"
