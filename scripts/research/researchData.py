"""Shared research-data plumbing (design review: one owner instead of four
duplicated copies of the same three definitions).

Owns:
  RESEARCH_FETCH       the Config with fetch.dataDirs=[data, data/universe]
                       — the research scope of the military cells
  researchDataDirs()   CLI --data-dir > fetch.dataDirs > fetch.dataDir,
                       resolved against the repo root (engine precedence)
  MILITARY             the military/strike slug tuple (isMilitarySlug)
  militaryMarketsFrame(dirs)  markets.parquet across dirs, dedup'd to the
                       last marketId, military slugs only, resolution date
                       coalesced — the frame every annotate() join needs

Loaders use the same importlib-by-path pattern as the other research
scripts: spec_from_file_location("researchData", RESEARCH_DIR / "researchData.py").
"""

from pathlib import Path

import polars as pl

from polycrawler.backtest import dirsFromConfig
from polycrawler.config import Config, FetchConfig

ROOT = Path(__file__).resolve().parents[2]

# Research cells span the accrued universe, so both dirs by default; the
# resolution goes through the config system (fetch.dataDirs / --data-dir),
# same precedence as the engine side.
RESEARCH_FETCH = Config(fetch=FetchConfig(dataDirs=["data", "data/universe"]))

MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela",
            "nato", "strike")


def isMilitarySlug(slug: str) -> bool:
    return any(k in (slug or "").lower() for k in MILITARY)


def researchDataDirs(root: Path | None = None, requested=None) -> list[Path]:
    """CLI --data-dir wins over fetch.dataDirs, else fetch.dataDir, resolving
    against the repo root."""
    return dirsFromConfig(root or ROOT, requested, RESEARCH_FETCH)


def militaryMarketsFrame(dirs: list[Path]) -> pl.DataFrame:
    """markets.parquet across all dirs, unique'd keep='last', restricted to
    military/strike events: eventSlug joined winner + resolvedAt, exactly the
    column set annotate()/entries joins use."""
    markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet")
                          for d in dirs], how="diagonal_relaxed")
               .unique("marketId", keep="last")
               .select("marketId", "eventSlug", "winner",
                       pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
    return markets.filter(pl.col("eventSlug").map_elements(
        isMilitarySlug, return_dtype=pl.Boolean))
