"""Tests for the lane mark-close accounting (research/paperLanes.md).

The gate thresholds, the 50bps sell slippage, and the resolution precedence
are the pre-registered conventions; close accounting reuses
paperMarkToMarket.copySpend (imported by the script under test). All file
activity happens on tmp roots via monkeypatched module paths.
"""

import csv
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import paperLaneMarks as plm
import paperLanes as pl


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

LIVE = "data/live"
SIG2_FIELDS = ["alertTs", "account", "eventSlug", "question", "marketId",
               "outcome", "burstUsd", "avgPrice", "ageDays", "marketsSeen",
               "bestAsk", "askSize", "takeableShares"]


def signalRow(alertTs="2026-10-01 12:00:00", bestAsk="0.60", takeable="0",
              mid="0xmm", account="0xw", outcome="Yes", eventSlug="fav"):
    return {"alertTs": alertTs, "account": account, "eventSlug": eventSlug,
            "question": "Q?", "marketId": mid, "outcome": outcome,
            "burstUsd": "12000.0", "avgPrice": "0.60", "ageDays": "0.0",
            "marketsSeen": "1", "bestAsk": bestAsk, "askSize": "500",
            "takeableShares": takeable}


def gammaMarket(closed=False, outs=None, prices=None):
    return {"closed": closed, "outcomes": json.dumps(outs or ["Yes", "No"]),
            "outcomePrices": json.dumps(prices or ["0.70", "0.30"])}


@pytest.fixture()
def tmpTree(tmp_path, monkeypatch):
    live = tmp_path / LIVE
    live.mkdir(parents=True)
    monkeypatch.setattr(plm, "ROOT", tmp_path)
    monkeypatch.setattr(plm, "CLOSES", live / "laneCloses.csv")
    monkeypatch.setattr(plm, "MARKS", live / "laneMarks.csv")
    cfg = {
        "lane2": {"enabled": True, "horizonsDays": [7], "sellSlippageBps": 50},
        "lane3": {"enabled": True, "horizonsDays": [3, 7], "sellSlippageBps": 50,
                  "minUsd": 10000.0, "priceMin": 0.55, "priceMax": 0.90,
                  "maxAlertsPerDay": 3, "skipFeeMarkets": True,
                  "tags": ["politics"], "maxMarkets": 600},
    }
    monkeypatch.setattr(pl, "loadConfig", lambda path=None: cfg)
    return tmp_path


def writeSignals(tmp, name, rows):
    with (tmp / LIVE / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SIG2_FIELDS)
        w.writeheader()
        w.writerows(rows)


def readCsv(path):
    if not Path(path).exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


class FakeClient:
    def get(self, url, params=None):
        raise AssertionError("network calls must go through plm.fetchMarket")


# --- close accounting ----------------------------------------------------------

def test_mark_close_applies_slippage(tmpTree):
    out = plm.closePosition(signalRow(), "lane2", 7, gammaMarket(), 50.0,
                            datetime.now(tz=UTC))
    assert out["closeType"] == "mark"
    assert abs(out["closePrice"] - 0.70 * (1 - 50 / 10000)) < 1e-9
    shares = 100.0 / 0.60
    assert out["spend"] == 100.0
    assert abs(out["shares"] - shares) < 1e-2
    assert abs(out["pnl"] - (shares * 0.70 * (1 - 50 / 10000) - 100.0)) < 0.01
    assert out["won"] == ""  # a mark exit is not a resolution win/loss


def test_resolution_close_precedes_marks(tmpTree):
    m = gammaMarket(closed=True, outs=["Yes", "No"], prices=["1.0", "0.0"])
    win = plm.closePosition(signalRow(), "lane2", 7, m, 50.0, datetime.now(tz=UTC))
    assert win["closeType"] == "resolution"
    assert win["closePrice"] == 1.0
    assert win["won"] is True
    assert abs(win["pnl"] - (100.0 / 0.60 - 100.0)) < 0.01
    lose = plm.closePosition(signalRow(outcome="No"), "lane2", 7, m, 50.0,
                             datetime.now(tz=UTC))
    assert lose["closePrice"] == 0.0
    assert lose["won"] is False
    assert lose["pnl"] == -100.0


def test_unmatchable_or_empty_entries_are_skipped(tmpTree):
    assert plm.closePosition(signalRow(bestAsk="0"), "lane2", 7,
                             gammaMarket(), 50.0, datetime.now(tz=UTC)) is None
    assert plm.closePosition(signalRow(outcome="Odd"), "lane2", 7,
                             gammaMarket(), 50.0, datetime.now(tz=UTC)) is None


# --- end-to-end: closes, snapshots, idempotent appends -------------------------

def test_run_closes_due_marks_and_snapshots_open(tmpTree, capsys):
    now = datetime.now(tz=UTC)
    old = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    mid = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")  # T+3d due, T+7d not
    sig3 = [signalRow(alertTs=old, mid="0xold"), signalRow(alertTs=mid, mid="0xmid")]
    writeSignals(tmpTree, "signalsLane3.csv", sig3)
    monkey_open = {"0xold": gammaMarket(prices=["0.80", "0.20"]),
                   "0xmid": gammaMarket(prices=["0.60", "0.40"])}
    plm.fetchMarket = lambda client, mid_: monkey_open.get(mid_)
    plm.run(FakeClient())
    closes = readCsv(tmpTree / LIVE / "laneCloses.csv")
    snaps = readCsv(tmpTree / LIVE / "laneMarks.csv")
    # lane 3: 0xold closes BOTH horizons (3+7), 0xmid closes T+3d and stays open
    assert [c["horizon"] for c in closes if c["lane"] == "lane3"] == ["3", "7", "3"]
    assert len([s for s in snaps if s["lane"] == "lane3"]) == 1
    out = capsys.readouterr().out
    assert "lane3 gate: INCONCLUSIVE-THIN" in out


def test_run_is_idempotent(tmpTree, capsys):
    now = datetime.now(tz=UTC)
    old = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    writeSignals(tmpTree, "signalsLane2.csv", [signalRow(alertTs=old)])
    writeSignals(tmpTree, "signalsLane3.csv", [signalRow(alertTs=old,
                                                        bestAsk="0.70")])
    plm.fetchMarket = lambda client, mid_: gammaMarket(prices=["0.80", "0.20"])
    plm.run(FakeClient())
    n1 = len(readCsv(tmpTree / LIVE / "laneCloses.csv"))
    s1 = len(readCsv(tmpTree / LIVE / "laneMarks.csv"))
    assert n1 == 3  # lane2 h7 + lane3 h3 + lane3 h7
    assert s1 == 0  # everything closed; nothing left to snapshot
    plm.run(FakeClient())
    n2 = len(readCsv(tmpTree / LIVE / "laneCloses.csv"))
    s2 = len(readCsv(tmpTree / LIVE / "laneMarks.csv"))
    assert (n2, s2) == (n1, 0)


def test_disabled_lane_runs_nothing(tmpTree, capsys, monkeypatch):
    cfg = pl.loadConfig()
    cfg = {**cfg,
           "lane2": {**cfg["lane2"], "enabled": False},
           "lane3": {**cfg["lane3"], "enabled": False}}
    monkeypatch.setattr(pl, "loadConfig", lambda path=None: cfg)
    now = datetime.now(tz=UTC)
    old = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    writeSignals(tmpTree, "signalsLane2.csv", [signalRow(alertTs=old)])
    writeSignals(tmpTree, "signalsLane3.csv", [signalRow(alertTs=old)])
    plm.fetchMarket = lambda client, mid_: gammaMarket()
    plm.run(FakeClient())
    assert not (tmpTree / LIVE / "laneCloses.csv").exists()
    assert "lane2: disabled" in capsys.readouterr().out


# --- pre-registered gate verdicts ----------------------------------------------

def test_verdict2_bands():
    assert plm.verdict2(3, 50.0, 0.5).startswith("INCONCLUSIVE-THIN")
    # in-sample-like: mean >= +20 and winRate >= 25%
    assert plm.verdict2(8, 30.0, 0.30).startswith("PASS")
    # holdout-like: mean <= -27 or winRate <= 15% decide FAIL even with n >= 8
    assert plm.verdict2(8, -50.0, 0.9).startswith("FAIL")
    assert plm.verdict2(8, 100.0, 0.10).startswith("FAIL")
    # between the bands
    assert plm.verdict2(8, 5.0, 0.5).startswith("INCONCLUSIVE")


def test_verdict3_bands():
    assert plm.verdict3(19, 30.0, 0.8).startswith("INCONCLUSIVE-THIN")
    assert plm.verdict3(20, -5.0, 0.4).startswith("KILL")
    assert plm.verdict3(20, -5.0, 0.57).startswith("INCONCLUSIVE")  # wr above kill
    assert plm.verdict3(20, 3.0, 0.70).startswith("PROMOTION SIGNAL")
    assert plm.verdict3(20, 3.0, 0.60).startswith("INCONCLUSIVE")


def test_gate_report_reads_closes_only(tmpTree, capsys):
    now = datetime.now(tz=UTC)
    old = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    writeSignals(tmpTree, "signalsLane2.csv", [signalRow(alertTs=old)])
    plm.fetchMarket = lambda client, mid_: gammaMarket(prices=["0.90", "0.10"])
    plm.run(FakeClient())
    out = capsys.readouterr().out
    assert "lane2 T+7d: n=1 mean=" in out
