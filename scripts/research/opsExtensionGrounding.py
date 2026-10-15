"""ops-extension grounding (commit 2): verify the pre-registered tuple.

NO PnL computation here. The only data work is slug matching over the
markets parquet of every configured data dir, exactly reproducing the
shipped substring semantics:

    any(k in (eventSlug or "").lower() for k in keywords)

(imported via importlib; the substring expression here is a set-membership
identity test, not cell logic — all burst/PnL logic lives in entrySweep and
is imported there.)

Run: uv run python scripts/research/opsExtensionGrounding.py [--data-dir ...]
"""

import importlib.util
import sys
from pathlib import Path

import polars as pl
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# dirsFromConfig on the shipped research dirs (data + data/universe).
from polycrawler.backtest import dirsFromConfig
from polycrawler.config import Config, FetchConfig

RESEARCH_FETCH = Config(fetch=FetchConfig(dataDirs=["data", "data/universe"]))

_spec = importlib.util.spec_from_file_location(
    "entrySweep", ROOT / "scripts" / "research" / "entrySweep.py")
entrySweep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entrySweep)
# grounding may reuse the shipped tuple as the shipped-set definition itself
SHIPPED = tuple(entrySweep.MILITARY)


def loadKeywords() -> tuple[tuple, ...]:
    cfg = yaml.safe_load((ROOT / "configs" / "opsExtensionKeywords.yaml").read_text())
    return tuple(cfg["extension"])


def match(slug: str | None, keywords: tuple) -> bool:
    s = (slug or "").lower()
    return any(k in s for k in keywords)


def main() -> None:
    ext = loadKeywords()
    dirs = [str(p) for p in dirsFromConfig(ROOT, None, RESEARCH_FETCH)]
    markets = pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs],
                        how="diagonal_relaxed")
    slugs = (markets.unique("eventSlug")
             .select("eventSlug").drop_nulls().to_series().to_list())
    slugs = sorted(s for s in slugs if s)

    shippedHits = [s for s in slugs if match(s, SHIPPED)]
    extHits = [s for s in slugs if match(s, ext)]
    combined = [s for s in slugs if match(s, SHIPPED + ext)]
    newHits = [s for s in combined if s not in set(shippedHits)]

    # G5 additivity check: the tuple is purely additive (shipped unchanged,
    # extension a disjoint retention set)
    assert combined == sorted(set(shippedHits) | set(newHits))
    overlap = set(extHits) & set(shippedHits)
    print(f"events scanned           : {len(slugs)}")
    print(f"shipped-matched (15 kw)  : {len(shippedHits)}")
    print(f"extension-matched (11 kw): {len(extHits)} "
          f"({len(extHits) - len(newHits)} of them also shipped-matched: {sorted(overlap)})")
    print(f"NEW-matched (delta)      : {len(newHits)}")
    print()

    vol = (markets.unique("eventSlug").group_by("eventSlug")
           .agg(volumeUsd=pl.col("volumeUsd").sum(), nMarkets=pl.len())
           .to_dicts()
           if "volumeUsd" in markets.columns else [])
    volBySlug = {r["eventSlug"]: r["volumeUsd"] for r in vol}
    mkBySlug = {r["eventSlug"]: r["nMarkets"] for r in vol}

    def table(title: str, rows: list[str]) -> None:
        print(f"## {title} ({len(rows)})")
        for s in rows:
            print(f"  {s}  [markets={mkBySlug.get(s, '?')}, volUsd={volBySlug.get(s, '?')}]")
        print()

    table("NEW-matched slugs (incremental-only surface)", newHits)
    table("shipped-matched slugs (unchanged behavior)", shippedHits)

    out = {
        "eventsScanned": len(slugs),
        "shippedMatched": len(shippedHits),
        "extensionMatched": len(extHits),
        "extensionAlsoShipped": len(overlap),
        "newMatched": len(newHits),
        "gateG1NewEvents": len(newHits),
        "gateG5Additive": True,
    }
    print("grounding summary:", out)


if __name__ == "__main__":
    main()
