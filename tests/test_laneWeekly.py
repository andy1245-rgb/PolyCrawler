"""Tests for the lane weekly readout (laneWeekly.py)."""

import csv
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "laneWeekly", Path(__file__).resolve().parents[1] / "scripts" / "laneWeekly.py"
)
lw = importlib.util.module_from_spec(spec)
sys.modules["laneWeekly"] = lw
spec.loader.exec_module(lw)


def closeRow(horizon: int = 7, pnl: float = 10.0, **over) -> dict:
    r = {
        "lane": "lane3", "horizon": str(horizon), "alertTs": "2026-10-17 19:09:19",
        "account": "0xaaa", "eventSlug": "eslug", "copiedOutcome": "Yes",
        "entry": "0.73", "closeTs": "2026-10-24T19:09:19+00:00",
        "closeDate": "2026-10-24", "closeType": "mark", "closePrice": "0.80",
        "markAtClose": "0.80", "slippageBps": "50", "spend": "100.0",
        "shares": "136.99", "won": "", "pnl": str(pnl),
    }
    r.update(over)
    return r


# --- pre-registered lane-2 gate ------------------------------------------------

def test_gate2_pass_side() -> None:
    assert "PASS" in lw.gate2(8, 20.0, 0.25)
    assert "PASS" in lw.gate2(20, 50.0, 0.40)


def test_gate2_fail_side() -> None:
    assert "FAIL" in lw.gate2(8, -27.0, 0.30)
    assert "FAIL" in lw.gate2(8, 10.0, 0.15)
    assert "FAIL" in lw.gate2(100, -40.0, 0.0)


def test_gate2_thin_and_inconclusive() -> None:
    assert lw.gate2(7, 50.0, 0.40).startswith("INCONCLUSIVE-THIN")
    assert lw.gate2(7, 0.0, 0.0).startswith("INCONCLUSIVE-THIN")
    assert ("INCONCLUSIVE" in lw.gate2(8, 10.0, 0.20)
            and "FAIL" not in lw.gate2(8, 10.0, 0.20)
            and "PASS" not in lw.gate2(8, 10.0, 0.20))


# --- pre-registered lane-3 gate ------------------------------------------------

def test_gate3_kill_side() -> None:
    assert "KILL" in lw.gate3(20, 0.0, 0.55)
    assert "KILL" in lw.gate3(30, -5.0, 0.20)
    assert "KILL" not in lw.gate3(20, 0.0, 0.60)
    assert "KILL" not in lw.gate3(20, 0.01, 0.50)


def test_gate3_promo_side() -> None:
    assert "PROMOTION" in lw.gate3(20, 0.01, 0.65)
    assert "PROMOTION" in lw.gate3(25, 30.0, 0.80)
    assert "PROMOTION" not in lw.gate3(20, 10.0, 0.64)


def test_gate3_thin_and_inconclusive() -> None:
    assert "THIN" in lw.gate3(19, -10.0, 0.30)
    assert "INCONCLUSIVE" in lw.gate3(20, 10.0, 0.60)


# --- band bucketing edges -------------------------------------------------------

def test_bucket_edges() -> None:
    assert lw.bucket3(0.8499) == lw.BUCKET_MID
    assert lw.bucket3(0.85) == lw.BUCKET_HIGH
    assert lw.bucket3(0.8999) == lw.BUCKET_HIGH
    assert lw.bucket3(0.90) == lw.BUCKET_UNKNOWN
    assert lw.bucket3(0.55) == lw.BUCKET_MID
    assert lw.bucket3(0.5499) == lw.BUCKET_UNKNOWN


# --- fail-soft --------------------------------------------------------------

def test_read_csv_missing_empty(tmp_path: Path) -> None:
    assert lw.readCsvRows(tmp_path / "nope.csv") == []
    empty = tmp_path / "empty.csv"
    empty.write_text("alertTs,account,eventSlug\n")
    assert lw.readCsvRows(empty) == []


def test_report_missing_files_fail_soft(tmp_path: Path) -> None:
    (tmp_path / "data" / "live").mkdir(parents=True)
    lines = lw.buildReport(tmp_path)
    joined = "\n".join(lines)
    assert "lane1: no data yet" in joined
    assert "lane2: no data yet" in joined
    assert "lane3: no data yet" in joined
    assert "next decision date: 2026-11-14" in joined


# --- report assembly on a synthetic live tree ---------------------------------

SIGNAL3_FIELDS = ["alertTs", "account", "eventSlug", "question", "marketId",
                  "outcome", "burstUsd", "avgPrice", "ageDays", "marketsSeen",
                  "bestAsk", "askSize", "takeableShares"]

MARK_FIELDS = ["date", "lane", "alertTs", "account", "eventSlug",
               "copiedOutcome", "avgPrice", "entry", "mark", "openPnl",
               "spend", "shares", "valuedAt"]


def writeCsv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def seedLive(tmp_path: Path, signals: list[dict], closes: list[dict],
             marks: list[dict]) -> Path:
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True)
    writeCsv(live / "signalsLane3.csv", SIGNAL3_FIELDS, signals)
    if closes:
        writeCsv(live / "laneCloses.csv", list(closeRow().keys()), closes)
    writeCsv(live / "laneMarks.csv", MARK_FIELDS, marks)
    return tmp_path


def test_report_lane3_buckets(tmp_path: Path) -> None:
    sigA = {"alertTs": "2026-10-17 19:09:19", "account": "0xaaa",
            "eventSlug": "eslug", "question": "q", "marketId": "0xm",
            "outcome": "Yes", "burstUsd": "11000.0", "avgPrice": "0.60",
            "ageDays": "0.0", "marketsSeen": "1", "bestAsk": "0.73",
            "askSize": "1000.0", "takeableShares": "100.0"}
    sigB = {**sigA, "alertTs": "2026-10-18 19:09:19", "account": "0xbbb",
            "avgPrice": "0.86"}
    closeMid = closeRow(pnl=15.0, alertTs=sigA["alertTs"],
                        account=sigA["account"])
    closeHigh = closeRow(pnl=-10.0, alertTs=sigB["alertTs"],
                         account=sigB["account"])
    closeStale = closeRow(horizon=3, pnl=99.0, alertTs=sigA["alertTs"],
                          account=sigA["account"])
    markA = {"date": "2026-10-18", "lane": "lane3",
             "alertTs": sigA["alertTs"], "account": sigA["account"],
             "eventSlug": sigA["eventSlug"], "copiedOutcome": "Yes",
             "avgPrice": "0.60", "entry": "0.73", "mark": "0.80",
             "openPnl": "9.60", "spend": "100.0", "shares": "136.99",
             "valuedAt": "2026-10-18T19:15:25+00:00"}
    markOld = {**markA, "date": "2026-10-17", "openPnl": "-5.00"}
    root = seedLive(tmp_path, [sigA, sigB],
                    [closeMid, closeHigh, closeStale], [markA, markOld])
    lines = lw.buildReport(root)
    joined = "\n".join(lines)
    assert "lane1: no data yet" in joined
    assert "lane2: no data yet" in joined
    assert "rows=2 first=2026-10-17 last=2026-10-18" in joined
    assert "closes=" in joined
    assert "unrealized=$+9.60" in joined
    assert "closes=3 realized=$+104.00" in joined  # T+3d close realizes too
    assert "gate (T+7d, whole 0.55-0.90 book): INCONCLUSIVE-THIN (n=2 < 20)" in joined
    assert "mid [0.55,0.85): n=1 mean=+15.00/copy winRate=100%" in joined
    assert "high [0.85,0.90): n=1 mean=-10.00/copy winRate=0%" in joined
    assert "99.00" not in joined  # T+3d close never enters T+7d stats
    assert "lane3: needs 18 more T+7d" in joined
    assert "2026-11-14" in joined


def test_report_lane1_reads_open_book(tmp_path: Path) -> None:
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True)
    sigFields = ["alertTs", "account", "eventSlug", "burstUsd", "avgPrice"]
    writeCsv(live / "signals.csv", sigFields,
             [{"alertTs": "2026-10-14 23:43:32", "account": "0xaa",
               "eventSlug": "eslug", "burstUsd": "16358.22", "avgPrice": "0.18"}])
    openFields = ["alertTs", "account", "eventSlug", "copiedOutcome",
                  "burstUsd", "avgPrice", "entry", "mark", "spread", "spend",
                  "shares", "openPnl", "marketEnd", "valuedAt"]
    writeCsv(live / "openPositions.csv", openFields,
             [{"alertTs": "2026-10-14 23:43:32", "account": "0xaa",
               "eventSlug": "eslug", "copiedOutcome": "Yes",
               "burstUsd": "16358.22", "avgPrice": "0.18", "entry": "0.17",
               "mark": "0.155", "spread": "-0.015", "spend": "100.0",
               "shares": "588.24", "openPnl": "-8.82",
               "marketEnd": "2027-01-01", "valuedAt": "2026-10-17T04:00:02+00:00"}])
    lines = lw.buildReport(tmp_path)
    joined = "\n".join(lines)
    assert "lane1 (resolution book)" in joined
    assert "rows=1 first=2026-10-14 last=2026-10-14" in joined
    assert "unrealized=$-8.82 (1 open rows @valued 2026-10-17)" in joined


def test_stats_winrate() -> None:
    assert lw.stats([]) == (0, 0.0, 0.0)
    assert lw.stats([closeRow(pnl=5.0), closeRow(pnl=-1.0)]) == (2, 2.0, 0.5)


def test_unmatched_signal_close_bucketed_separately() -> None:
    prices = {}
    split = lw.bucketSplit([closeRow()], prices)
    assert split[lw.BUCKET_UNKNOWN] == [closeRow()]
    assert split[lw.BUCKET_MID] == []
