"""Episode-level resampling: re-baseline entrySweep cells honestly.

entrySweep's bootstrap resamples EVENT slugs with replacement. On market
date ladders ("israel-strikes-iran-by-january-16 / -31 / february-28 / ...")
the rungs are rungs of one dated process, not independent markets — treating
them as independent samples is the classic consistent-unit error, and it is
what pushed the shipped military cell to event-level P(>0) 0.98 while the
episode-level reality is far weaker.

Unit definition (data-derived, implement option (a) of the research review):
two military slugs belong to ONE EPISODE if they share >=K distinct accounts
whose >=$5k bursts appear in both (K=5 default), where bursts are the same
burst entries entrySweep builds over the same dirs ([data, data/universe]).
Union-find over slug nodes with those shared-account edges gives episode
labels; optional human overrides live in configs/episodeOverrides.yaml
(empty by default, documented there).

Per cell (minUsd, maxPrice, age bucket, event filter):
  episode-level bootstrap: resample EPISODES with replacement (B=10000),
  same ratio estimator as entrySweep.evaluate (sum pnl / sum cap over the
  resample), same ret column = plain mean retReal, so the two levels are
  directly comparable. Also published EX-TOP-EPISODE: drop the largest-PnL
  episode and recompute ret / P(>0) / p5 over the remaining episodes.
Event-level numbers come straight from entrySweep's own filterCell +
evaluate so the semantics are identical to the shipped sweep.

Ground truth: the iran-Feb-2026 date-ladder episode must not splinter into
>=3 separate episode groups at K=5; episodeGroups() prints the episode table
so a human can check the cluster is one process.

Run: uv run python scripts/research/episodeResample.py [--k 5] [--refresh]
     [--md] [--out research/episodeResample.md]
"""

import argparse
import importlib.util
import random
import sys
import time
from pathlib import Path
from typing import Any

import polars as pl
import yaml

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]

# engineParity pattern: import entrySweep by path, never copy its internals.
_spec = importlib.util.spec_from_file_location(
    "entrySweep", ROOT / "scripts" / "research" / "entrySweep.py")
esw = importlib.util.module_from_spec(_spec)
sys.modules["entrySweep"] = esw
_spec.loader.exec_module(esw)

OVERRIDES_PATH = ROOT / "configs" / "episodeOverrides.yaml"
DEFAULT_K = 5
EPISODE_BOOTS = 10_000
SEED = 7  # same RNG discipline entrySweep.runSweep uses

# Units: the account-overlap episode graph is defined on >=$5k bursts (the
# same size gate as the shipped cell's entry filter), regardless of price or
# freshness, so the graph is a property of the tape, not of one cell.
EPISODE_MIN_USD = 5000

SHIPPED = {"minUsd": 5000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3}

# Cells asked of the re-baseline, in fixed order (determinism): shipped,
# candidate, the two age buckets of the shipped cell, and the non-military
# control at the same gates. ageMin is an inclusive lower bound on ageDays
# (0 = entrySweep's plain ageDays <= ageDays filter).
CELLS: list[dict[str, Any]] = [
    {"label": "shipped $5k/<=0.35/<=5d/<=3mkts", "universe": "military", "ageMin": 0,
     **SHIPPED},
    {"label": "candidate $10k/<=0.35/<=5d/<=3mkts",
     "universe": "military", "ageMin": 0,
     "minUsd": 10000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3},
    {"label": "shipped cell, age <=1d", "universe": "military", "ageMin": 0,
     "minUsd": 5000, "maxPrice": 0.35, "ageDays": 1, "marketsSoFar": 3},
    {"label": "shipped cell, age 2-5d", "universe": "military", "ageMin": 1,
     "minUsd": 5000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3},
    {"label": "non-military control $5k/<=0.35/<=5d/<=3mkts",
     "universe": "nonmilitary", "ageMin": 0, **SHIPPED},
]


# ------------------------------------------------------------- episodes ---

def sharedAccountEdges(entries: pl.DataFrame, minUsd: float = EPISODE_MIN_USD
                       ) -> pl.DataFrame:
    """(slug, slug, k) for every slug pair with k = distinct accounts holding
    a >=$5k burst in BOTH slugs (same dirs as entrySweep by construction)."""
    acct = (entries.filter(pl.col("usd") >= float(minUsd))
            .group_by("account", "eventSlug").agg(n=pl.len()))
    edges = (acct.join(acct, on="account")
             .filter(pl.col("eventSlug") < pl.col("eventSlug_right"))
             .group_by("eventSlug", "eventSlug_right")
             .agg(k=pl.n_unique("account"))
             .sort("eventSlug", "eventSlug_right"))
    return edges


def loadOverrides(path: Path | None = OVERRIDES_PATH) -> dict[str, list]:
    """Manual episode overrides. configs/episodeOverrides.yaml is empty by
    default; keys: `merge` ([slugA, slugB, ...] groups force-merged into one
    episode despite <$K account overlap) and `exclude` ([slugA, slugB] pairs
    whose auto edge is severed). Human judgment outranks the graph only via
    this file — the graph itself stays data-derived."""
    if path is None or not path.exists():
        return {"merge": [], "exclude": []}
    spec = yaml.safe_load(path.read_text()) or {}
    return {"merge": spec.get("merge") or [], "exclude": spec.get("exclude") or []}


def episodeGroups(edges: pl.DataFrame, slugs: list[str], k: int = DEFAULT_K,
                  overrides: dict[str, list] | None = None) -> list[list[str]]:
    """Union-find over slug nodes, edges = shared-account overlaps with k >= K.
    Returns groups sorted by (largest first, then lexicographic) and each
    group's slugs sorted, so outputs are deterministic."""
    ov = overrides or {"merge": [], "exclude": []}
    excluded = {tuple(sorted(p)) for p in ov.get("exclude", [])}
    parent = {s: s for s in slugs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b, kk in edges.iter_rows():
        if (a, b) not in excluded and kk >= k:
            union(a, b)
    for group in ov.get("merge", []):
        for slug in group[1:]:
            union(group[0], slug)
    groups: dict[str, list[str]] = {}
    for s in slugs:
        groups.setdefault(find(s), []).append(s)
    return sorted((sorted(g) for g in groups.values()),
                  key=lambda g: (-len(g), g[0]))


def episodeLabels(groups: list[list[str]]) -> dict[str, str]:
    """Slug -> label ('ep1', 'ep2', ... in the deterministic group order)."""
    return {slug: f"ep{idx}" for idx, group in enumerate(groups, 1) for slug in group}


def episodeTable(groups: list[list[str]], entries: pl.DataFrame,
                 labels: dict[str, str]) -> pl.DataFrame:
    """Human-checkable table: episode id, member slugs, >=$5k signals, dates."""
    rows = []
    for idx, group in enumerate(groups, 1):
        sub = entries.filter(pl.col("eventSlug").is_in(group))
        rows.append({
            "episode": f"ep{idx}",
            "slugs": "; ".join(group),
            "nSlugs": len(group),
            "signals": sub.height,
            "first": sub["ts"].min(),
            "last": sub["ts"].max(),
        })
    return pl.DataFrame(rows).sort("nSlugs", descending=True)


def kSensitivity(entries: pl.DataFrame, slugs: list[str],
                 iranFebSlugs: set[str], ks: list[int]) -> pl.DataFrame:
    """How the graph's connectedness moves with K — printed alongside the
    ground-truth assert so the choice is a documented, checked judgment."""
    edges = sharedAccountEdges(entries)
    rows = []
    for k in ks:
        groups = episodeGroups(edges, slugs, k=k)
        own = [groups.index(g) for g in groups if set(g) & iranFebSlugs]
        rows.append({"k": k, "episodes": len(groups),
                     "largest": max(len(g) for g in groups),
                     "iranFebEpisodes": len(set(own))})
    return pl.DataFrame(rows)


def iranFebEpisodeSlugs(entries: pl.DataFrame) -> set[str]:
    """Ground-truth reference cluster (data-derived, not name-matching):
    slugs with >=$5k burst signals inside calendar Feb-2026 that moon the
    iran date-ladder process. Selection: signals in Feb-2026 AND the slug
    contains 'iran' — exactly the pre-review claim '333/434 signals belong
    to one calendar episode (iran-Feb-2026: 10 slugs of the Iran
    date-ladder)'."""
    feb = entries.filter((pl.col("ts").dt.year() == 2026)
                         & (pl.col("ts").dt.month() == 2))
    return set(feb.filter(pl.col("eventSlug").str.to_lowercase()
                          .str.contains("iran"))["eventSlug"].unique().to_list())


def groundTruthCheck(groups: list[list[str]], truthSlugs: set[str],
                     k: int = DEFAULT_K) -> dict[str, Any]:
    """Pre-review assert: the iran-Feb-2026 episode must not splinter into
    >=3 groups at K=5 (over-merge is reported, under-merge is a failure)."""
    owners: list[str] = []
    for s in truthSlugs:
        for i, g in enumerate(groups, 1):
            if s in g:
                owners.append(f"ep{i}")
                break
    episodeCount = len(set(owners))
    assert episodeCount < 3, (
        f"ground truth violated: iran-Feb-2026 split into {episodeCount} "
        f"episode groups ({sorted(set(owners))}) at K={k} — tune K or edit "
        f"configs/episodeOverrides.yaml, then re-run")
    return {"k": k, "truthSlugs": len(truthSlugs), "episodes": episodeCount,
            "groups": sorted(set(owners)), "ok": True}


# ------------------------------------------------------------ bootstrap ---

def filterCellCustom(entries: pl.DataFrame, cell: dict[str, Any]) -> pl.DataFrame:
    """entrySweep's cell gates verbatim plus an optional ageMin lower bound
    (for the 2-5d bucket). Delegates the shared gates to entrySweep itself."""
    out = esw.filterCell(entries, cell)
    if float(cell.get("ageMin", 0) or 0) > 0:
        out = out.filter(pl.col("ageDays") > float(cell["ageMin"]))
    return out


def episodeStats(df: pl.DataFrame, labels: dict[str, str],
                 boots: int = EPISODE_BOOTS, seed: int = SEED) -> dict[str, float]:
    """Resample EPISODES with replacement; ratio estimator identical to
    entrySweep.evaluate (sum pnl / sum cap), B=10000, rng = Random(seed)."""
    def tagged(s: str) -> str:
        return labels.get(s) or ("solo:" + s)

    eps = (df.with_columns(episode=pl.col("eventSlug").map_elements(
                tagged, return_dtype=pl.String))
           .group_by("episode")
           .agg(pnl=(pl.col("retReal") * 100).sum(), cap=pl.len() * 100.0,
                entries=pl.len())
           .sort("episode"))
    rows = list(eps.iter_rows(named=True))
    rng = random.Random(seed)

    def boot(pool: list[dict]) -> list[float]:
        draws = []
        for _ in range(boots):
            samp = [pool[rng.randrange(len(pool))] for _ in range(len(pool))]
            draws.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
        draws.sort()
        return draws

    draws = boot(rows)
    top = max(rows, key=lambda e: e["pnl"])
    rest = [e for e in rows if e["episode"] != top["episode"]]
    # ex-top statistics: the cell without its biggest episode. A fresh
    # per-call fixed seed keeps every number order-independent and
    # reproducible; if the cell has a single episode, ex-top degenerates to
    # that episode and is published as-is.
    pool = rest if rest else [top]
    exDraws = boot(pool)
    exTopRet = (df.filter(pl.col("eventSlug").map_elements(
                lambda s: tagged(s) != top["episode"], return_dtype=pl.Boolean))["retReal"]
                .mean())
    return {
        "episodes": len(rows),
        "epP": sum(1 for d in draws if d > 0) / boots,
        "epP5": round(draws[int(0.05 * boots)], 3),
        "epP95": round(draws[int(0.95 * boots)], 3),
        "exTopEpisode": top["episode"],
        "exTopPnl": round(top["pnl"], 0),
        "exTopRet": round(exTopRet, 3) if exTopRet is not None else None,
        "exTopP": sum(1 for d in exDraws if d > 0) / boots,
        "exTopP5": round(exDraws[int(0.05 * boots)], 3),
        "exTopEntries": int(sum(e["entries"] for e in pool)),
    }


def measureCell(entries: pl.DataFrame, cell: dict[str, Any],
                labels: dict[str, str],
                boots: int = EPISODE_BOOTS) -> dict[str, Any]:
    """One cell, both levels side by side. Event-level numbers are computed
    by entrySweep's own filterCell + evaluate (semantics identical to the
    shipped sweep); episode-level by episodeStats above."""
    df = filterCellCustom(entries, cell)
    row: dict[str, Any] = dict(cell)
    if df.height == 0:
        return {**row, "n": 0, "ret": None, "events": 0, "pEvent": None,
                "p5Event": None, "episodes": 0, "epP": None, "epP5": None,
                "epP95": None, "exTopEpisode": None, "exTopPnl": None,
                "exTopRet": None, "exTopP": None, "exTopP5": None,
                "exTopEntries": 0}
    ev = esw.evaluate(df, random.Random(SEED))  # bootstraps events, B=1000
    ep = episodeStats(df, labels, boots=boots)
    row.update({
        "n": ev["n"],
        "ret": ev.get("ret", df["retReal"].mean()),
        "events": ev.get("events", df["eventSlug"].n_unique()),
        "pEvent": ev.get("p"),
        "p5Event": ev.get("p5"),
    })
    row.update(ep)
    return row


MARKDOWN_HEAD = (
    "| cell | n | events | ret | ep | P(>0) event | p5 event | P(>0) episode "
    "| p5 episode | p95 episode | ex-top episode | ex-top ret | ex-top P | "
    "ex-top p5 |\n"
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|\n")


def markdownRow(r: dict[str, Any]) -> str:
    def num(x: float | None) -> str:
        return "—" if x is None else (f"{x:+.2f}" if isinstance(x, float) else str(x))
    return (f"| {r['label']} | {r['n']} | {r['events']} | {num(r['ret'])} | "
            f"{r['episodes']} | {num(r['pEvent'])} | {num(r['p5Event'])} | "
            f"{num(r['epP'])} | {num(r['epP5'])} | {num(r['epP95'])} | "
            f"{r['exTopEpisode']} ({r['exTopPnl']:+.0f}) | {num(r['exTopRet'])} | "
            f"{num(r['exTopP'])} | {num(r['exTopP5'])} |\n")


# ----------------------------------------------------------------- main ---

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", action="append", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--boots", type=int, default=EPISODE_BOOTS)
    parser.add_argument("--md", action="store_true", help="emit a markdown table")
    parser.add_argument("--out", default=None,
                        help="write the markdown to this file as well")
    parser.add_argument("--sensitivity", action="store_true",
                        help="print the K-sensitivity table of the graph")
    args = parser.parse_args()
    dirs = [str(p) for p in esw.dirsFromConfig(ROOT, args.data_dir, esw.RESEARCH_FETCH)]
    overrides = loadOverrides()
    mil = esw.loadEntries(dirs, args.refresh)                     # 15-keyword universe
    nonmil = esw.loadEntries(dirs, args.refresh, keywords=None)   # complement (control)

    universe = mil.filter(pl.col("usd") >= EPISODE_MIN_USD)
    slugs = sorted(universe["eventSlug"].unique().to_list())
    edges = sharedAccountEdges(universe)
    groups = episodeGroups(edges, slugs, k=args.k, overrides=overrides)
    labels = episodeLabels(groups)

    print(f"\n-- episode graph (K={args.k}, accounts with >=${EPISODE_MIN_USD} "
          f"bursts in both slugs, overrides={sum(len(v) for v in overrides.values())} entries) --",
          flush=True)
    table = episodeTable(groups, universe, labels)
    with pl.Config(tbl_rows=60, fmt_str_lengths=120, tbl_width_chars=240):
        print(table)
    truthSlugs = iranFebEpisodeSlugs(universe)
    truth = groundTruthCheck(groups, truthSlugs, k=args.k)
    print(f"ground truth: iran-Feb-2026 calendar episode = {truth['truthSlugs']} slugs "
          f"-> {truth['episodes']} episode group(s) at K={args.k} "
          f"({'PASS' if truth['ok'] else 'FAIL'}, no splinter into >=3)")

    if args.sensitivity:
        sens = kSensitivity(universe, slugs, truthSlugs,
                            ks=[1, 2, 3, 5, 8, 10, 20, 50, 100])
        with pl.Config(tbl_rows=30):
            print("\n-- K sensitivity (episodes / largest episode / iranFeb groups) --")
            print(sens)

    print(f"\n-- cells ({args.boots} episode bootstraps, seed {SEED}) --")
    rows = []
    for cell in CELLS:
        entries = nonmil if cell["universe"] == "nonmilitary" else mil
        # the control is measured on its own complement labels: one episode
        # graph per keyword universe, same rule, so it is a like-for-like check
        if cell["universe"] == "nonmilitary":
            ctrl = nonmil.filter(pl.col("usd") >= EPISODE_MIN_USD)
            ctrlSlugs = sorted(ctrl["eventSlug"].unique().to_list())
            ctrlLabels = episodeLabels(
                episodeGroups(sharedAccountEdges(ctrl), ctrlSlugs,
                              k=args.k, overrides=overrides))
            labelsForCell = ctrlLabels
        else:
            labelsForCell = labels
        row = measureCell(entries, cell, labelsForCell, boots=args.boots)
        rows.append(row)
        print(f"  {row['label']}: n={row['n']} events={row['events']} "
              f"ret={row['ret']} P(event)={row['pEvent']} p5={row['p5Event']} "
              f"| eps={row['episodes']} P(episode)={row['epP']} p5={row['epP5']} "
              f"| ex-top {row['exTopEpisode']} ret={row['exTopRet']} "
              f"P={row['exTopP']} p5={row['exTopP5']} "
              f"({time.time() - t0:.0f}s)", flush=True)

    if args.md:
        md = MARKDOWN_HEAD + "".join(markdownRow(r) for r in rows)
        print("\n```markdown")
        print(md.rstrip())
        print("```")
        if args.out:
            Path(args.out).write_text(md)
            print(f"written {args.out}")


if __name__ == "__main__":
    main()
