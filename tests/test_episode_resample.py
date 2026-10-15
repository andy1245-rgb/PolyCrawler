"""Tests for episode-level resampling: the account-overlap union-find, the
per-call determinism of the episode bootstrap, and the iran-Feb-2026
ground-truth sanity assert (on synthetic frames — no tape dependency)."""

import importlib.util
import random
import sys
from datetime import datetime, timedelta, timezone
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

ers = _load("episodeResample", "episodeResampleTest")

T0 = datetime(2026, 1, 20, tzinfo=timezone.utc)


def burst(account: str, slug: str, usd: float = 8000.0, day: int = 0,
          retReal: float = 0.5, age: float = 1.0) -> dict:
    ts = T0 + timedelta(days=day)
    return {"account": account, "eventSlug": slug, "ts": ts, "usd": usd,
            "retReal": retReal, "price": 0.2, "ageDays": age,
            "marketsSoFar": 1}


# --------------------------------------------------------- union logic ---

def test_shared_account_edges_count_overlap() -> None:
    # a1..a5 hold >=$5k bursts in BOTH slugs; b1 holds bursts in one only.
    rows = ([burst(f"a{i}", "slug-a") for i in range(5)]
            + [burst(f"a{i}", "slug-b", day=1) for i in range(5)]
            + [burst("c1", "slug-c")])
    edges = ers.sharedAccountEdges(pl.DataFrame(rows))
    pairs = {(r[0], r[1], r[2]) for r in edges.iter_rows()}
    assert ("slug-a", "slug-b", 5) in pairs
    # slug-c shares nothing -> no edge at all
    assert not any("slug-c" in (p[0], p[1]) for p in pairs)


def test_episodeGroups_merges_only_connected_slugs() -> None:
    rows = ([burst(f"x{i}", "s-run-16") for i in range(5)]
            + [burst(f"x{i}", "s-run-31", day=1) for i in range(5)]
            + [burst("y1", "s-lone")])
    frame = pl.DataFrame(rows)
    edges = ers.sharedAccountEdges(frame)
    slugs = sorted(frame["eventSlug"].unique().to_list())
    groups = ers.episodeGroups(edges, slugs, k=5)
    ladder = next(g for g in groups if "s-run-16" in g)
    assert ladder == ["s-run-16", "s-run-31"]  # five shared accounts -> one episode
    assert ["s-lone"] in groups


def test_episodeGroups_k_gate_is_inclusive_and_clean() -> None:
    # only 4 shared accounts: must NOT merge at K=5, must be one group at K=4
    rows = ([burst(f"a{i}", "s-one", day=0) for i in range(4)]
            + [burst(f"a{i}", "s-two", day=1) for i in range(4)]
            + [burst("b9", "s-two", day=1)])
    frame = pl.DataFrame(rows)

    def groups_for(k: int) -> list[list[str]]:
        slugs = sorted(frame["eventSlug"].unique().to_list())
        return ers.episodeGroups(ers.sharedAccountEdges(frame), slugs, k=k)

    g5 = groups_for(5)
    g4 = groups_for(4)
    assert ["s-one"] in g5 and ["s-two"] in g5      # splintered at K=5
    assert next(g for g in g4 if "s-one" in g) == ["s-one", "s-two"]


def test_episodeGroups_overrides_merge_and_exclude(tmp_path: Path) -> None:
    rows = ([burst("a1", "s-one"), burst("a2", "s-one")]
            + [burst("a1", "s-two", day=1), burst("a2", "s-two", day=1)]
            + [burst("a3", "s-two", day=1), burst("a3", "s-two", day=2)]
            + [burst("a3", "s-three", day=1), burst("a3", "s-three", day=2)])
    frame = pl.DataFrame(rows)
    slugs = sorted(frame["eventSlug"].unique().to_list())
    edges = ers.sharedAccountEdges(frame)
    auto = ers.episodeGroups(edges, slugs, k=2)
    assert next(g for g in auto if "s-one" in g) == ["s-one", "s-two"]  # a1+a2 shared
    # severing the a-edges: exclude the s-one <-> s-two edge only
    severed = ers.episodeGroups(edges, slugs, k=2,
                                overrides={"merge": [], "exclude": [["s-one", "s-two"]]})
    assert ["s-one"] in severed
    # force-merge without any shared account
    forced = ers.episodeGroups(edges, slugs, k=2,
                               overrides={"merge": [["s-one", "s-three"]],
                                          "exclude": []})
    merged = next(g for g in forced if "s-one" in g)
    assert "s-three" in merged and "s-two" in merged  # s-two rode in via its own edge


def test_episode_labels_and_table() -> None:
    groups = [["s-big", "s-small"], ["s-lone"]]
    labels = ers.episodeLabels(groups)
    assert labels == {"s-big": "ep1", "s-small": "ep1", "s-lone": "ep2"}
    rows = [burst("a1", "s-big", day=0), burst("a1", "s-small", day=1)]
    table = ers.episodeTable(groups, pl.DataFrame(rows), labels)
    byEp = {r["episode"]: r for r in table.iter_rows(named=True)}
    assert byEp["ep1"]["nSlugs"] == 2 and byEp["ep1"]["signals"] == 2


# --------------------------------------------------------- bootstrap ---

def _cell_frame(episodePnl: dict[str, float], perEpisode: int = 3) -> pl.DataFrame:
    """Each slug's entries share one constant retReal; slugs in one episode
    must be resampled together."""
    rows = []
    for slug, ret in episodePnl.items():
        rows += [burst(f"acct-{slug}", slug, retReal=ret, day=len(rows))
                 for _ in range(perEpisode)]
    return pl.DataFrame(rows)


def test_episodeStats_resamples_by_episode_and_is_deterministic() -> None:
    labels = {"rung-16": "ep1", "rung-31": "ep1", "other-event": "ep2"}
    df = _cell_frame({"rung-16": 2.0, "rung-31": -5.0, "other-event": 99.0})
    a = ers.episodeStats(df, labels, boots=2000, seed=7)
    b = ers.episodeStats(df, labels, boots=2000, seed=7)
    assert a == b  # fixed seed -> identical numbers every call

    # episode-level pools the rungs: ep1 = (600 + -1500)/600 = -1.5, ep2 = +99.
    # The -1.5 episode is so small relative to +99 that ANY draw containing
    # ep2 stays positive; only ep1+ep1 fails -> P(>0) = 0.75 (3 of 4 combos),
    # while a naive event-level resample treats 3 slugs as 3 units.
    assert a["episodes"] == 2
    assert a["epP"] == pytest.approx(0.75, abs=0.05)
    # the resample really pools the two rungs into one unit
    assert a["exTopEpisode"] == "ep2"
    # ex-top: only ep1 remains (its entry-level mean is (2-5)/2 = -1.5)
    assert a["exTopP"] == 0.0
    assert a["exTopRet"] == pytest.approx(-1.5, abs=1e-6)

    # a slug with no label falls into its own solo episode, never silently
    # joins a labeled one
    df2 = _cell_frame({"rung-16": 2.0, "rung-31": 5.0, "solo-guy": -0.5})
    labels2 = {"rung-16": "ep1", "rung-31": "ep1"}
    c = ers.episodeStats(df2, labels2, boots=2000, seed=7)
    assert c["episodes"] == 2
    assert c["exTopEpisode"] == "ep1" and c["exTopP"] == 0.0  # solo loser can't save it


def test_filterCellCustom_age_min_lower_bound() -> None:
    rows = [burst("a1", "s", day=0, age=0.2), burst("a2", "s", day=3, age=3.2)]
    frame = pl.DataFrame(rows)
    got = ers.filterCellCustom(frame, {"minUsd": 5000, "maxPrice": 0.35,
                                       "ageDays": 5, "marketsSoFar": 3, "ageMin": 1})
    assert got["ageDays"].min() > 1.0  # the 0-day entry is gone


# ------------------------------------------------- ground truth + gates ---

def _synthetic_truth_frame() -> pl.DataFrame:
    """iran-Feb-2026 ladder: 4 rungs sharing 10 big accounts, plus a busy
    non-iran trader's other market. Ground truth: rungs are one episode."""
    rows = []
    # 10 shared professional accounts fire >=$5k in every iran-Feb rung
    for i in range(10):
        for j, day in enumerate(range(4, 25, 6)):  # Jan .. Feb 2026 rungs
            rows.append(burst(f"pro{i}",
                              f"us-strikes-iran-by-feb-world-{j}",
                              usd=9000, day=day, retReal=0.3))
    rows += [burst("tail", "unrelated-venezuela-bill", usd=8000, day=40)]
    return pl.DataFrame(rows)


def test_syntheticIranFebLadder_checks_and_gate() -> None:
    frame = _synthetic_truth_frame()
    edges = ers.sharedAccountEdges(frame)
    slugs = sorted(frame["eventSlug"].unique().to_list())
    groups = ers.episodeGroups(edges, slugs, k=5)
    truth = {s for s in slugs if "iran" in s}
    truthCount = len(truth)
    out = ers.groundTruthCheck(groups, truth, k=5)
    assert out["ok"] is True
    assert out["truthSlugs"] == truthCount
    assert out["episodes"] == 1  # the four rungs stay ONE episode at K=5
    # the unrelated tail event is NOT absorbed into the iran episode
    assert ["unrelated-venezuela-bill"] in groups


def test_groundTruthCheck_fails_on_splinter() -> None:
    # not a bare assert anymore: the diagnostic is printed and the process
    # exits nonzero (SystemExit), so a failing run can't vanish silently
    groups = [["iran-a"], ["iran-b"], ["iran-c"], ["other"]]
    with pytest.raises(SystemExit, match="split into 3"):
        ers.groundTruthCheck(groups, {"iran-a", "iran-b", "iran-c"}, k=50)
    assert ers.groundTruthCheck(groups, {"iran-a", "iran-b"}, k=50)["ok"] is True


def test_dataDerivedK_reads_the_fine_grid() -> None:
    ks = ers.sensitivityKs()
    # the fine grid covers the published gap that verdict-flipping cells
    # lived in: step-2 coverage of 1..40 plus the 50/100 spots, and the
    # K=5 / K=20 anchors of the old tables
    assert ks[:5] == [1, 2, 3, 4, 5] and 20 in ks and 30 in ks
    assert ks[-2:] == [50, 100] and all(k in ks for k in range(6, 41, 2))
    frame = pl.DataFrame({"k": [1, 3, 5, 8, 20, 30], "iranFebEpisodes":
                          [1, 1, 1, 2, 2, 3]})
    assert ers.dataDerivedK(frame) == 20   # largest admissible K
    frame2 = pl.DataFrame({"k": [5, 10], "iranFebEpisodes": [3, 4]})
    assert ers.dataDerivedK(frame2) is None  # nothing admissible


def test_main_cells_constant_and_self_consistent() -> None:
    # the reported cells exist, pins the gates so the doc numbers denote
    # stable configs, and the required shipped/control both present
    labels = [c["label"] for c in ers.CELLS]
    assert labels == ["shipped $5k/<=0.35/<=5d/<=3mkts",
                      "candidate $10k/<=0.35/<=5d/<=3mkts",
                      "shipped cell, age <=1d",
                      "shipped cell, age 2-5d",
                      "non-military control $5k/<=0.35/<=5d/<=3mkts"]
    assert ers.DEFAULT_K == 5 and ers.SEED == 7 and ers.EPISODE_BOOTS == 10_000
    # determinism of the whole deterministic path: measureCell twice on the
    # same synthetic labelled rows must agree
    labelsEp = {"s-one": "ep1", "s-two": "ep1"}
    df = _cell_frame({"s-one": 1.0, "s-two": -0.5})
    df = df.with_columns(price=pl.lit(0.2), ageDays=pl.lit(1.0),
                         marketsSoFar=pl.lit(1))
    r1 = ers.measureCell(df, {"minUsd": 5000, "maxPrice": 0.35, "ageDays": 5,
                              "marketsSoFar": 3, "ageMin": 0}, labelsEp)
    r2 = ers.measureCell(df, {"minUsd": 5000, "maxPrice": 0.35, "ageDays": 5,
                              "marketsSoFar": 3, "ageMin": 0}, labelsEp)
    assert r1 == r2
