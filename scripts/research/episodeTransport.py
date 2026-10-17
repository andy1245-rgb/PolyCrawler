"""Episode-level regrouping wired into the sweep/transport evaluation.

Additive port of the absorbed feature/episodeScope machinery
(scripts/research/episodeResample.py + research/episodeResample.md) into the
transport evaluation path: per-event p5 ranking stays untouched; with the
flag on, every cell additionally gets its events regrouped into
account-overlap EPISODES (units: slugs sharing >=K distinct >=$5k-burst
accounts; K is data-derived, K* = the largest K in the fine sensitivity grid
that keeps the iran-Feb-2026 ground-truth reference at <=2 episode groups),
and the falsification bar (episode-level P(>0) >= 0.80 at K*, >=3 episodes
in the cell — a <3-partition is the degenerate over-merge whose P(>0) "is
the one big episode positive" and carries no distribution meaning) composes
the verdict: PASS only if the pre-registered per-event gate (p5 > 0 AND
P(>0) >= 85%) AND the episode gate both clear. Regrouping pools correlated
dated-ladder rungs into single units, which raises resample variance and so
can only DEFLATE the stability check — a per-event FAIL can never turn into
an episode PASS (verified on the regraded $10k/<=0.35 OOS cell, see
research/episodeTransport.md).

Nothing here re-implements the graph or the bootstrap: sharedAccountEdges /
episodeGroups / episodeStats / the K* derivation all come from
episodeResample by importlib-by-path, exactly the reuse discipline
entrySweep/oosTransport already follow.

Run: never standalone (no main) — imported by entrySweep (--episodes flag)
and oosTransport (--episodes flag). CLI behavior with the flag off is
byte-identical to before.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[2]

# episodeResample owns the machinery; its by-path load also brings
# entrySweep's module instance along (episodeResample imports it), but this
# module never reaches through it — filterCell is loaded explicitly below.
_spec = importlib.util.spec_from_file_location(
    "episodeResample", ROOT / "scripts" / "research" / "episodeResample.py")
ers = importlib.util.module_from_spec(_spec)
sys.modules["episodeResample"] = ers
_spec.loader.exec_module(ers)

_spec = importlib.util.spec_from_file_location(
    "entrySweepTransport", ROOT / "scripts" / "research" / "entrySweep.py")
esw = importlib.util.module_from_spec(_spec)
sys.modules["entrySweepTransport"] = esw
_spec.loader.exec_module(esw)

# The falsification bar published in research/episodeResample.md (>=0.80 at
# the gate) and the pre-registered per-event transport bar (P(>0) >= 85%,
# research/status.md 9.2). Both are policy constants pinned here, not data.
EPISODE_BAR = 0.80
EVENT_BAR = 0.85
MIN_EPISODES = 3          # below this the episode view is degenerate over-merge
SWEEP_BOOTS = 1000        # episode resample draws in the sweep path: same B as
SEED = ers.SEED           # the per-event evaluate bootstrap (7), fixed per call
RESEARCH_K_STAR = 34      # the in-sample tape's data-derived gate; the pin
                          # when derivation is impossible on the local tape

EPISODE_COLS = ["episodes", "epP", "epP5", "epP95", "exTopP", "exTopRet",
                "exTopP5", "kStar", "epVerdict", "verdict"]


def buildUnits(entries: pl.DataFrame, k: int | None = None,
               overrides_path: Path | None = ers.OVERRIDES_PATH) -> dict[str, Any]:
    """Tape-level episode graph: the edges are computed over the whole
    >=$5k universe (the unit definition is a property of the tape, not of a
    cell), and the gate K* is data-derived from the iran-Feb-2026
    reference splinter point on THIS tape. When the reference is missing or
    splinters at every grid K (a tape with no welded ladder at all), the
    gate pins to the in-sample K* = 34 and says so — the gate is then
    policy-anchored, not data-derived. `k` pins the gate explicitly and
    disables derivation (tests, ad-hoc analysis)."""
    universe = entries.filter(pl.col("usd") >= ers.EPISODE_MIN_USD)
    slugs = sorted(universe["eventSlug"].unique().to_list())
    edges = ers.sharedAccountEdges(universe)
    overrides = ers.loadOverrides(overrides_path)
    truth = ers.iranFebEpisodeSlugs(universe)
    gate: str
    if k is not None:
        kStar, gate = k, "pinned (explicit --k)"
    else:
        if truth:
            derived = ers.dataDerivedK(
                ers.kSensitivity(universe, slugs, truth, ers.sensitivityKs()))
            if derived is not None:
                kStar, gate = derived, "data-derived"
            else:
                kStar, gate = RESEARCH_K_STAR, "pinned (reference splinters at every K)"
        else:
            kStar, gate = RESEARCH_K_STAR, "pinned (no iran-Feb reference on tape)"
    groups = ers.episodeGroups(edges, slugs, k=kStar, overrides=overrides)
    labels = ers.episodeLabels(groups)
    units = {"k": kStar, "gate": gate, "labels": labels, "truthSlugs": len(truth),
             "nSlugs": len(slugs), "nGroups": len(groups), "edges": edges.height,
             "universeRows": universe.height,
             "overrides": sum(len(v) for v in overrides.values())}
    if truth:
        owners: set[int] = set()
        for s in truth:
            for i, g in enumerate(groups, 1):
                if s in g:
                    owners.add(i)
                    break
        units["truthGroups"] = len(owners)
    return units


def printUnits(units: dict[str, Any], tapeRows: int) -> None:
    print(f"\n-- episode units (K*={units['k']}, {units['gate']}; graph over "
          f"{units['universeRows']} >=$5k bursts / {units['nSlugs']} slugs -> "
          f"{units['nGroups']} groups, {units['overrides']} overrides) --")
    if units.get("truthGroups") is not None:
        print(f"ground truth: {units['truthSlugs']} iran-Feb reference slugs -> "
              f"{units['truthGroups']} group(s) at K* "
              f"({'PASS' if units['truthGroups'] <= 2 else 'SPLINTERED'}; "
              f"bar is <=2)")


def episodeGate(df: pl.DataFrame, units: dict[str, Any],
                boots: int = SWEEP_BOOTS, bar: float = EPISODE_BAR,
                seed: int = SEED) -> dict[str, Any]:
    """One cell, episode view: regroup the cell's entries into the tape
    labels, resample EPISODES (episodeResample.episodeStats: same ratio
    estimator as entrySweep.evaluate), and apply the K* gate. Verdicts:
    PASS = >=MIN_EPISODES episodes and P(>0) >= bar; DEGENERATE = fewer
    episodes than MIN_EPISODES (published, never counts as PASS — the
    single-mega-episode read has no distribution meaning); FAIL otherwise."""
    if df.height == 0:
        return {"episodes": 0, "epP": None, "epP5": None, "epP95": None,
                "exTopP": None, "exTopRet": None, "exTopP5": None,
                "epVerdict": "INCON"}
    ep = ers.episodeStats(df, units["labels"], boots=boots, seed=seed)
    bloated = ep["episodes"] < MIN_EPISODES
    return {"episodes": ep["episodes"], "epP": ep["epP"], "epP5": ep["epP5"],
            "epP95": ep["epP95"], "exTopP": ep["exTopP"], "exTopRet": ep["exTopRet"],
            "exTopP5": ep["exTopP5"],
            "kStar": units["k"],
            "epVerdict": "DEGENERATE" if bloated
            else ("PASS" if ep["epP"] is not None and ep["epP"] >= bar else "FAIL")}


def eventGate(p5: float | None, p: float | None, bar: float = EVENT_BAR) -> str:
    """Pre-registered per-event transport bar restricted to what a sweep row
    carries (doc-faithful 9.2 trace: PASS iff p5 > 0 AND P(>0) >= 85%; the
    delay-realistic / top-event-share clauses live in oosTransport, whose
    composed verdict adds its own dr clause on top)."""
    if p5 is None or p is None:
        return "INCON"
    return "PASS" if (p5 > 0 and p >= bar) else "FAIL"


def composeVerdict(event: str, episode: str) -> str:
    """The honest composition: the episode gate can only ever ADD a FAIL.
    PASS requires both views; DEGENERATE over-merge never grants PASS."""
    if event == "INCON":
        return "INCON"
    return "PASS" if (event == "PASS" and episode == "PASS") else "FAIL"


def attach(ranked: pl.DataFrame, entries: pl.DataFrame, units: dict[str, Any],
           boots: int = SWEEP_BOOTS, bar: float = EPISODE_BAR,
           seed: int = SEED) -> pl.DataFrame:
    """Append the episode columns to an entrySweep.runSweep ranking WITHOUT
    touching its columns order or its sort (the per-event p5 ranking is the
    shipped behavior; the episode view rides along side-by-side)."""
    rows = []
    for cell in ranked.iter_rows(named=True):
        df = esw.filterCell(entries, cell)
        row = dict(cell)
        row.update(episodeGate(df, units, boots=boots, bar=bar, seed=seed))
        row["verdict"] = composeVerdict(
            eventGate(row.get("p5"), row.get("p")), row["epVerdict"])
        rows.append(row)
    return pl.DataFrame(rows)


def episodeSummary(ranked: pl.DataFrame, units: dict[str, Any],
                   limit: int = 0) -> None:
    """Side-by-side readout for --episodes runs: per-event floor cell vs its
    episode view + composed verdict, on the cell, in ranked order."""
    cols = ["episodes", "epP", "epP5", "exTopP", "exTopRet", "kStar",
            "epVerdict", "verdict"]
    with pl.Config(tbl_rows=40, fmt_str_lengths=40, tbl_width_chars=220):
        front = [c for c in ranked.columns
                 if c in ("minUsd", "maxPrice", "ageDays", "marketsSoFar")]
        print(f"\n-- episode view at K*={units['k']} ({units['gate']}); "
              f"side-by-side with the per-event p5 ranking --")
        print(ranked.select(front + ["n", "ret", "p5", "p"] + cols).head(limit or 40))
        if "verdict" in ranked.columns:
            counts = ranked.group_by("verdict").len().sort("verdict")
            print(f"verdicts across all {ranked.height} cells:")
            print(counts)
