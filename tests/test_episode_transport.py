"""Tests for the episodeTransport port: the tape-level unit build (derived /
pinned K*), the additive attach into runSweep (regrouping, sort untouched,
flag-off identical), and the K* gate verdict composition (the episode gate
can only ever ADD a FAIL; over-merge degeneracy never grants PASS). All on
synthetic frames — no tape, no cache dependency."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

RESEARCH = Path(__file__).resolve().parents[1] / "scripts" / "research"


def _load(name: str, key: str):
    spec = importlib.util.spec_from_file_location(key, RESEARCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module

epT = _load("episodeTransport", "episodeTransportTest")
esw = _load("entrySweep", "entrySweepTestPort")

T0 = datetime(2026, 2, 10, tzinfo=UTC)
GRID = {"minUsd": [5000], "maxPrice": [0.35], "ageDays": [5], "marketsSoFar": [3]}
CELL = {"minUsd": 5000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3}


def burst(account: str, slug: str, retReal: float = 0.5, day: int = 0,
          usd: float = 8000.0, entries: int = 1) -> list[dict]:
    """One burst of `entries` >=$5k entries on one (account, market, outcome);
    each entry is its own 10-minute window so cap counts are per-entry."""
    ts = T0 + timedelta(days=day)
    return [{"account": account, "eventSlug": slug, "ts": ts + timedelta(hours=i),
             "usd": usd, "retReal": retReal, "price": 0.2, "ageDays": 1.0,
             "marketsSoFar": 1} for i in range(entries)]


def flat(*chunks: list[dict]) -> list[dict]:
    return [d for chunk in chunks for d in chunk]


# ------------------------------------------------------------- unit build ---

def test_buildUnits_prefers_explicit_k_and_reports_graph() -> None:
    rows = flat(*[burst(f"pro{i}", "s-run-16", day=0) for i in range(5)],
                *[burst(f"pro{i}", "s-run-31", day=1) for i in range(5)],
                burst("lone", "s-lone", day=2))
    units = epT.buildUnits(pl.DataFrame(rows), k=5)
    assert units["k"] == 5 and units["gate"].startswith("pinned (explicit")
    assert units["nSlugs"] == 3
    labels = units["labels"]
    assert labels["s-run-16"] == labels["s-run-31"] != labels["s-lone"]


def test_buildUnits_derives_kStar_from_welded_iranFeb_ladder() -> None:
    # two iran-Feb rungs welded by 150 shared >=$5k accounts: the reference
    # never splinters on the fine grid (max K = 100), so the data-derived
    # gate is the grid's largest K and the gate source says so
    rows = flat(*[burst(f"pro{i}", "us-strikes-iran-by-feb-rung", day=0)
                  for i in range(150)],
                *[burst(f"pro{i}", "israel-strikes-iran-by-feb-rung", day=3)
                  for i in range(150)],
                burst("lone", "unrelated-venezuela-bill", day=9))
    units = epT.buildUnits(pl.DataFrame(rows))
    assert units["gate"] == "data-derived"
    assert units["k"] == 100
    assert units["truthGroups"] == 1
    # the unrelated slug is NOT welded into the iran episode even at max K
    assert units["labels"]["unrelated-venezuela-bill"] != \
        units["labels"]["us-strikes-iran-by-feb-rung"]


def test_buildUnits_pins_when_no_reference_on_tape() -> None:
    rows = flat(burst("a", "s-one"), burst("b", "s-two", day=1))
    units = epT.buildUnits(pl.DataFrame(rows))
    assert units["k"] == epT.RESEARCH_K_STAR == 34
    assert units["gate"] == "pinned (no iran-Feb reference on tape)"
    assert units.get("truthGroups") is None


def test_buildUnits_pins_when_reference_splinters_every_k() -> None:
    # iran-Feb slugs with ZERO account overlap: >=3 truth groups at every K,
    # so derivation fails and the gate pins to the in-sample K*, saying so
    rows = flat(burst("a1", "f-iran-one"), burst("a2", "s-iran-two", day=1),
                burst("a3", "t-iran-three", day=2))
    units = epT.buildUnits(pl.DataFrame(rows))
    assert units["k"] == 34
    assert units["gate"] == "pinned (reference splinters at every K)"
    assert units["truthGroups"] == 3


# ---------------------------------------------- regrouping through attach ---

def _cell_tape() -> pl.DataFrame:
    """One cell's worth: a BIG positive rung welded (5 shared pro accounts)
    to a SMALL negative rung, plus three independent winners. Capping the
    welded episode at K=5 pools their pnl/cap first (+4000/11000), so any
    drawn sample stays positive (epP = 1.0); at K=100 the negative rung is
    its own unit again and the episode pool flips (1-0.8^5 ~ 0.672 -> FAIL).
    The per-event view never saw either pool shape the way the episodes do."""
    rows = []
    for i in range(5):
        rows += burst(f"pro{i}", "rung-a", retReal=0.5, day=0, entries=20)
    for i in range(5):
        rows += burst(f"pro{i}", "rung-b", retReal=-1.0, day=5, entries=2)
    for j in range(3):
        rows += burst(f"indep{j}", f"solo-{j}", retReal=0.5, day=10 + j)
    return pl.DataFrame(rows)


def test_attach_regroups_and_keeps_the_per_event_sort() -> None:
    frame = _cell_tape()
    units = epT.buildUnits(frame, k=5)
    plain = esw.runSweep(frame, GRID)
    withEpisodes = esw.runSweep(frame, GRID, episodeUnits=units)

    # flag off: the default path is exactly the shipped behavior
    assert plain.columns == ["minUsd", "maxPrice", "ageDays", "marketsSoFar",
                             "n", "ret", "p", "p5", "p95", "h1", "h2", "events"]
    # flag on: additive columns only, and the shipped ranking order untouched
    assert withEpisodes.columns[:len(plain.columns)] == plain.columns
    assert withEpisodes["p5"].to_list() == plain["p5"].to_list()
    assert withEpisodes["ret"].to_list() == plain["ret"].to_list()
    row = withEpisodes.row(0, named=True)
    # the two rungs really are ONE unit: 113 entries over 5 events -> 4
    # episodes (rungA+rungB welded, plus 3 solos)
    assert row["events"] == 5 and row["episodes"] == 4
    assert row["kStar"] == 5
    # welded pool first: every drawn sample is pnl-positive -> P = 1.0,
    # while the per-event pool still carries the -1.0 rung as one of 5
    # equal-weighted units (P(event) ~ 0.737 < 85%)
    assert row["epP"] == 1.0
    assert row["epVerdict"] == "PASS"
    assert row["p"] == pytest.approx(0.737, abs=0.03)
    assert row["verdict"] == "FAIL"  # composed: episode gate can't rescue the event FAIL
    # K flip: at K=100 the negative rung splinters out and the gate verdict
    # flips PASS -> FAIL (it fails whenever no rung-a draw lands: 1-0.8^5)
    soloUnits = epT.buildUnits(frame, k=100)
    soloRow = epT.attach(esw.runSweep(frame, GRID), frame, soloUnits).row(0, named=True)
    assert soloRow["episodes"] == 5
    assert soloRow["epVerdict"] == "FAIL"
    assert soloRow["epP"] == pytest.approx(0.761, abs=0.01)  # seed-7 realized
    # (the i.i.d. ideal would be 1-0.8^5 = 0.672; the first 1000 Random(7)
    # draws cluster — both views below consume the same stream anyway)
    # at K=100 every episode is exactly one event -> the episode bootstrap
    # is the per-event one, to the digit (same Random(7), same unit order)
    assert soloRow["epP"] == withEpisodes["p"].item()
    # ret is unit-invariant (episodeResample.md lesson 1)
    assert round(withEpisodes["ret"].item(), 9) == round(soloRow["ret"], 9)


def test_attach_degenerate_over_merge_never_grants_pass() -> None:
    # two positive independent events -> 2 episodes: the event view passes
    # cleanly, but with fewer than MIN_EPISODES episodes the episode view is
    # the degenerate "is the one big episode positive" read -> no PASS.
    frame = pl.DataFrame(flat(burst("w1", "epA", retReal=0.4),
                              burst("w2", "epB", retReal=0.6, day=40)))
    units = epT.buildUnits(frame, k=5)
    gated = epT.episodeGate(frame, units)
    assert gated["episodes"] == 2
    assert gated["epVerdict"] == "DEGENERATE"  # despite epP == 1.0
    assert epT.composeVerdict("PASS", gated["epVerdict"]) == "FAIL"


# ------------------------------------------------------------ gate + gates ---

def test_episodeGate_applies_the_published_falsification_bar() -> None:
    # 3 solo episodes with ratios (+1.0, -1.0, -1.0): P(>0) = 4/27 < 0.80
    rows = flat(burst("w1", "epA", retReal=1.0),
                burst("w2", "epB", retReal=-1.0, day=1),
                burst("w3", "epC", retReal=-1.0, day=2))
    units = epT.buildUnits(pl.DataFrame(rows), k=5)
    gated = epT.episodeGate(pl.DataFrame(rows), units, boots=4000, seed=7)
    assert gated["episodes"] == 3
    assert gated["epVerdict"] == "FAIL"
    # ex-top: dropping the +1.0 episode leaves the two losers -> P = 0
    assert gated["exTopP"] == 0.0
    # an all-positive 3-episode cell clears the bar (+/- the ex-top stats)
    rows2 = flat(burst("w1", "epA", retReal=0.5),
                 burst("w2", "epB", retReal=0.6, day=1),
                 burst("w3", "epC", retReal=0.7, day=2))
    units2 = epT.buildUnits(pl.DataFrame(rows2), k=5)
    ok = epT.episodeGate(pl.DataFrame(rows2), units2, boots=1000, seed=7)
    assert ok["epVerdict"] == "PASS" and ok["epP"] == 1.0
    assert ok["exTopP"] == 1.0
    # ex-top drops the largest-PNL episode (+0.7): mean ret of what remains
    assert ok["exTopRet"] == pytest.approx(0.55)


def test_episodeGate_empty_cell_is_incon() -> None:
    frame = _cell_tape()
    units = epT.buildUnits(frame, k=5)
    gated = epT.episodeGate(frame.filter(pl.col("usd") > 1e9), units)
    assert gated["episodes"] == 0 and gated["epVerdict"] == "INCON"


def test_eventGate_matches_the_pre_registered_transport_bar() -> None:
    assert epT.eventGate(0.3, 0.9) == "PASS"      # p5 > 0 AND P >= 85%
    assert epT.eventGate(0.3, 0.80) == "FAIL"     # P misses the bar
    assert epT.eventGate(-0.3, 0.99) == "FAIL"    # p5 floor negative
    assert epT.eventGate(None, None) == "INCON"   # below MIN_CELL


def test_composeVerdict_can_only_add_a_fail() -> None:
    assert epT.composeVerdict("PASS", "PASS") == "PASS"
    assert epT.composeVerdict("PASS", "FAIL") == "FAIL"
    assert epT.composeVerdict("FAIL", "PASS") == "FAIL"
    assert epT.composeVerdict("FAIL", "FAIL") == "FAIL"
    assert epT.composeVerdict("INCON", "PASS") == "INCON"
    assert epT.composeVerdict("PASS", "DEGENERATE") == "FAIL"


def test_policy_constants_match_the_published_bars() -> None:
    # pinned to the docs: 0.80 falsification bar at K* (episodeResample.md),
    # 85% per-event transport bar (status.md 9.2), K*=34 research gate
    assert epT.EPISODE_BAR == 0.80 and epT.EVENT_BAR == 0.85
    assert epT.MIN_EPISODES == 3 and epT.SEED == 7 and epT.SWEEP_BOOTS == 1000


def test_episode_summary_prints_without_touching_the_frame(
        capsys: pytest.CaptureFixture) -> None:
    frame = _cell_tape()
    units = epT.buildUnits(frame, k=5)
    ranked = epT.attach(esw.runSweep(frame, GRID), frame, units)
    before = ranked.columns
    epT.episodeSummary(ranked, units)
    assert ranked.columns == before  # readout only
    out = capsys.readouterr().out
    assert "episode view at K*=5" in out and "verdicts across all" in out
