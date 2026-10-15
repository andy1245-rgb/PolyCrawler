"""ops-extension first-look evaluator (commit 3).

Pre-registration: research/opsExtensionPreRegistration.md +
configs/opsExtensionKeywords.yaml (committed BEFORE this script existed).

Reuses scripts/research/entrySweep internals via importlib — NO copied cell
logic. The only local patch is the slug-match table used at ENTRY-BUILD
time (entrySweep.militaryMarketsTable matches only the shipped MILITARY
tuple; the extension surface is unknown to it), plus a cache dir redirect
out of the read-only data tree:

  * entrySweep.militaryMarketsTable -> broadened to shipped ∪ extension
  * entrySweep.CACHE_DIR -> <worktree>/.cacheOpsExtensionEntrySweep
  * entrySweep.buildEntries / loadEntries / filterCell / evaluate: untouched
    (evaluate() is reused EVENT LEVEL as-is, and reused EPISODE LEVEL by
    overwriting the grouping column "eventSlug" with the episode name)

Reporting is INCREMENTAL-ONLY per the pre-registration: every cell is the
extension-matched sample set MINUS the shipped-matched samples. No ranking,
no winners: first look numbers, all tried cells disclosed including n<MIN
failures.

Run: uv run python scripts/research/opsExtensionEval.py [--refresh]
"""

import importlib.util
import random
import re
import sys
import time
from pathlib import Path

import polars as pl
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from polycrawler.backtest import dirsFromConfig
from polycrawler.config import Config, FetchConfig

t0 = time.time()

_spec = importlib.util.spec_from_file_location(
    "entrySweep", ROOT / "scripts" / "research" / "entrySweep.py")
entrySweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entrySweep)  # noqa: F401  (may self-run main only under __main__)

SHIPPED = tuple(entrySweep.MILITARY)
_ext = yaml.safe_load((ROOT / "configs" / "opsExtensionKeywords.yaml").read_text())
EXT = tuple(_ext["extension"])
BOTH = SHIPPED + EXT

# ---- entry-build patches (the ONLY overrides; cell logic untouched) -------

def opsMarketsTable(markets: pl.DataFrame) -> pl.DataFrame:
    _bases = markets.unique("marketId", keep="last").select(
        "marketId", "eventSlug", "winner",
        pl.coalesce("resolvedAt", "endDate").alias("resolvedAt"))
    return _bases.filter(pl.col("eventSlug").map_elements(
        lambda s: any(k in (s or "").lower() for k in BOTH),
        return_dtype=pl.Boolean))


entrySweep.militaryMarketsTable = opsMarketsTable
entrySweep.CACHE_DIR = ROOT / ".cacheOpsExtensionEntrySweep"

RESEARCH_FETCH = Config(fetch=FetchConfig(dataDirs=["data", "data/universe"]))

# Pre-registered cell shapes: the shipped grid's release-relevant corner
# (militaryEntryGrid.yaml axes; the shipped live rule is 5000/0.35/5/3 and
# the §9 p5-floor candidates are 10000/0.35/...). Fixed BEFORE the run by
# the pre-registration; not tuned against results.
PRE_REG_CELLS = [
    {"minUsd": 500, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3},
    {"minUsd": 1000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3},
    {"minUsd": 5000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3},
    {"minUsd": 10000, "maxPrice": 0.35, "ageDays": 5, "marketsSoFar": 3},
]

FEE_SLIPPAGE_HAIRCUT = 0.10  # pre-registered stress, in place of un-modeable per-category taker fees


def matchSet(frame: pl.DataFrame, keywords: tuple) -> pl.Expr:
    sl = pl.col("eventSlug").fill_null("").str.to_lowercase()
    return sl.map_elements(lambda s: any(k in s for k in keywords),
                           return_dtype=pl.Boolean)


def episodeSlug(column: str = "eventSlug") -> pl.Expr:
    def _ep(s: str | None) -> str:
        s = (s or "").lower()
        return re.sub(r"-by-.*$", "", s)
    return pl.col(column).map_elements(_ep, return_dtype=pl.String)


def main() -> None:
    args = sys.argv[1:]
    refresh = "--refresh" in args
    dirs = [str(p) for p in dirsFromConfig(ROOT, None, RESEARCH_FETCH)]
    entries = entrySweep.loadEntries(dirs, refresh)

    extMask = matchSet(entries, EXT)
    shippedMask = matchSet(entries, SHIPPED)
    delta = entries.filter(extMask & ~shippedMask)
    combined = entries.filter(extMask)

    print(f"\n=== sample accounting ({time.time() - t0:.0f}s) ===")
    print(f"extension-matched (this is the ∪-build; shipped ⊆ matched) entries: "
          f"{combined.height}")
    print(f"DELTA entries (ext minus shipped)      : {delta.height}")
    print(f"delta events: {delta.select(pl.col('eventSlug').n_unique()).item()}, "
          f"delta episodes: {delta.select(pl.col('eventSlug').n_unique()).item()}")

    # G5 behavior preservation: the shipped matched set must be unchanged —
    # recompute it on the broadened build and compare counts to a build with
    # the shipped tuple unchanged (identical expression, same data).
    shippedOnBroadenedBuild = entries.filter(shippedMask)
    print(f"shipped-matched entries on broadened build: {shippedOnBroadenedBuild.height} "
          f"(events {shippedOnBroadenedBuild.select(pl.col('eventSlug').n_unique()).item()})")

    rng = random.Random(7)
    rows: list[dict] = []
    for cell in PRE_REG_CELLS:
        cellDelta = entrySweep.filterCell(delta, cell)
        row: dict[str, object] = dict(
            family="opsExtensionDelta", minUsd=cell["minUsd"],
            maxPrice=cell["maxPrice"], ageDays=cell["ageDays"],
            marketsSoFar=cell["marketsSoFar"])
        row.update(entrySweep.evaluate(cellDelta, rng))          # event level

        # episode level: reuse evaluate() with the grouping column
        # overwritten by the episode name (no copied evaluate logic)
        epLevel = cellDelta.with_columns(episodeSlug().alias("eventSlug"))
        rowE = entrySweep.evaluate(epLevel, random.Random(7))
        for k in ["ret", "p5", "p95", "p", "h1", "h2", "events"]:
            row[f"ep_{k}"] = rowE.get(k)
        # honest n below MIN_CELL => evaluate() returns None metrics; keep n
        if cellDelta.height:
            # incremental-events criterion inputs
            row["deltaEvents"] = cellDelta.select(pl.col("eventSlug").n_unique()).item()
            row["deltaEpisodes"] = (epLevel
                                    .select(pl.col("eventSlug").n_unique()).item())
            # LOEO: leave out the largest group's samples
            biggest = (cellDelta.group_by("eventSlug").agg(n=pl.len())
                       .sort("n", descending=True).item(0, 0) if cellDelta.height else None)
            if biggest is not None:
                exTop = cellDelta.filter(pl.col("eventSlug") != biggest)
                loeo = entrySweep.evaluate(exTop, random.Random(7)) if exTop.height else None
                if loeo:
                    row["loeo_n"] = loeo["n"]
                    row["loeo_ret"] = loeo.get("ret")
                    row["loeo_p5"] = loeo.get("p5")
            # per-episode P(>0) list (every episode disclosed)
            perEp = []
            for ep in epLevel.select("eventSlug").unique().to_series().to_list():
                sub = epLevel.filter(pl.col("eventSlug") == ep)
                r = entrySweep.evaluate(sub, random.Random(7))
                perEp.append({"episode": ep, "n": r["n"], "ret": r.get("ret"),
                              "p": r.get("p"), "p5": r.get("p5")})
            row["perEpisode"] = perEp
            # fee/slippage stress: +10% one-way haircut on retReal
            # (fills.parquet has no fee column — DISCLOSED GAP, see docs)
            stressed = cellDelta.with_columns(
                retReal=((1 + pl.col("retReal")) * (1 - FEE_SLIPPAGE_HAIRCUT) - 1))
            srow = entrySweep.evaluate(stressed, random.Random(7))
            row["stress_n"] = srow["n"]
            row["stress_ret"] = srow.get("ret")
            row["stress_p5"] = srow.get("p5")
            row["stress_p"] = srow.get("p")
        rows.append(row)

    print("\n=== first look: DELTA cells (incremental-only metric) ===")
    tbl = []
    for row in rows:
        perEp = row.pop("perEpisode", None)
        tbl.append(row)
        if perEp:
            print("  per-episode: "
                  + "; ".join(f"{e['episode']} n={e['n']} ret={e['ret']} "
                              f"P(>0)={e['p']} p5={e['p5']}" for e in perEp))
    with pl.Config(tbl_cols=40, tbl_width_chars=240, fmt_str_lengths=40):
        print(pl.DataFrame(tbl))
    print(f"\n(table rows: {len(rows)}; "
          f"n<MIN_CELL({entrySweep.MIN_CELL}) cells report ret=None by design — "
          f"disclosed, not pruned) ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
