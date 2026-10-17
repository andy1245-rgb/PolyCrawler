"""Mid-band top-up roster: fresh military-extension event cohort for
research/midbandTopup.md (option a — pre-registered there BEFORE this run).

Crawls gamma /events/keyset per military-adjacent tag (closed=true,
volume_min=100000 server-side slice), keeping events that are ALL of:
resolved-only (thirdUniverseScan.eventResolved recipe), slug matches the
SHIPPED 15-keyword military tuple (researchData.MILITARY), volume >= $100k,
and NOT already carried by data/, data/universe, data/oos, data/oosExpansion
or any existing roster config. Rendered into configs/midbandTopup.yaml
(~150 slugs, <=5-per-stem diversity cap, deterministic stem rule from the
pre-registration) for a pure pc2 fetch into data/midTopup.

Selection honesty: gamma EVENT METADATA only at this stage — no fills,
trades or burst content of any candidate is looked at (the cohort must not
be burst-selected; see the pre-registration).

Reused read-only: scripts/research/thirdUniverseScan.py (keysetChain —
after_cursor keyset pagination with the id-regression guard —, eventResolved,
eventVolume, gammaApi/gammaHost, PAGE) and scripts/research/researchData.py
(MILITARY / isMilitarySlug). Session paced ≤4 req/s via polycrawler HttpSession.

Run: uv run python scripts/research/midbandTopupRoster.py 2>&1 | tee logs/midbandTopupRoster.log
"""

import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path

import httpx

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location(
    "tus", ROOT / "scripts" / "research" / "thirdUniverseScan.py")
tus = importlib.util.module_from_spec(_spec)
sys.modules["tus"] = tus
_spec.loader.exec_module(tus)  # keysetChain / eventResolved / eventVolume / gamma*

_spec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_spec)
sys.modules["researchData"] = researchData
_spec.loader.exec_module(researchData)  # MILITARY / isMilitarySlug

from polycrawler.http import HttpSession  # HttpSession pacing adapter

TAGS = [
    "geopolitics", "middle-east", "israel", "iran", "gaza", "ukraine",
    "russia", "venezuela", "foreign-policy", "diplomacy-ceasefire",
    "lebanon", "syria", "hezbollah", "yemen", "israel-x-iran", "khamenei",
    "ukraine-peace-deal", "military-strikes", "india-pakistan", "hamas",
    "peace-deal", "war", "strike", "military-action", "nato", "taiwan",
]
VOLUME_FLOOR = 100_000.0
ROSTER_CAP = 150
STEM_CAP = 5
PAGE_CAP = 60  # per tag, mirrors the pre-registration

EXCLUDE_DIRS = ["data", "data/universe", "data/oos", "data/oosExpansion",
                "data/midTopup"]
EXCLUDE_CONFIGS = ["configs/oosFetch.yaml", "configs/oosExpansionFetch.yaml",
                   "configs/militaryUniverse.yaml", "configs/eventUniverse.yaml"]

STEM_CUT = re.compile(r"-(?:by|on|before|in|through|during|next|this)-")
STEM_TRAIL_NUM = re.compile(r"-\d+(?:-\d+)*$")


def log(msg: str) -> None:
    print(f"[MBR][{time.time() - t0:6.1f}s] {msg}", flush=True)


def stem(slug: str) -> str:
    """Pre-registered deterministic stem: cut at the first
    -(by|on|before|in|through|during|next|this)- tail, then strip trailing
    numeric qualifiers repeatedly."""
    m = STEM_CUT.search(slug)
    out = slug[:m.start()] if m else slug
    while True:
        m2 = STEM_TRAIL_NUM.search(out)
        if not m2:
            break
        out = out[:m2.start()]
    return out or slug


def excludedSlugs() -> set[str]:
    import polars as pl

    out: set[str] = set()
    for d in EXCLUDE_DIRS:
        p = ROOT / d / "markets.parquet"
        if p.exists():
            got = pl.read_parquet(p, columns=["eventSlug"])["eventSlug"].unique().to_list()
            out.update(g for g in got if g)
            log(f"excluded-from {d}: {len(got)} event slugs")
    for c in EXCLUDE_CONFIGS:
        p = ROOT / c
        if not p.exists():
            continue
        spec = _readYaml(p)
        slugs = (spec.get("fetch") or {}).get("eventSlugs") or spec.get("eventSlugs") or []
        out.update(slugs)
        log(f"excluded-from {c}: {len(slugs)} event slugs")
    return out


def _readYaml(p: Path) -> dict:
    import yaml

    return yaml.safe_load(p.read_text()) or {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", type=float, default=VOLUME_FLOOR,
                    help="gamma volume floor (pre-registered default 100k; "
                         "the pre-registered starved-cohort fallback is 30k)")
    ap.add_argument("--cap", type=int, default=ROSTER_CAP)
    args = ap.parse_args()
    floor, cap = args.floor, args.cap

    excluded = excludedSlugs()
    events: dict[str, dict] = {}
    pagesPerTag: dict[str, int] = {}
    with httpx.Client(timeout=60.0,
                      headers={"User-Agent": "polycrawler2-midband-topup-roster"}) as client:
        session = HttpSession(client, hostRates={tus.gammaHost: tus.GAMMA_RATE})
        for tag in TAGS:
            rows = tus.keysetChain(session, tag, {"volume_min": "100000"},
                                   "mb100k", slim=False, force=False)
            pagesPerTag[tag] = len(rows)
            for ev in rows:
                events[str(ev.get("id"))] = ev
            log(f"{tag}: {len(rows)} events >=$100k closed (cum unique {len(events)})")
    log(f"crawl dedup across {len(TAGS)} tags: {len(events)} closed events >=$100k")

    resolved = [ev for ev in events.values() if tus.eventResolved(ev)]
    log(f"resolved-only: {len(resolved)}")
    military = [ev for ev in resolved
                if researchData.isMilitarySlug(str(ev.get("slug")))]
    log(f"military-tuple slugs ({len(researchData.MILITARY)} shipped keywords): "
        f"{len(military)}")
    fresh = [ev for ev in military if str(ev.get("slug")) not in excluded]
    log(f"not carried by data dirs / roster configs: {len(fresh)} "
        f"({len(military) - len(fresh)} excluded)")

    ranked = sorted(fresh, key=lambda ev: (-tus.eventVolume(ev),
                                           str(ev.get("slug"))))
    perStem: dict[str, int] = {}
    roster: dict[str, dict] = {}
    for ev in ranked:
        slug = str(ev.get("slug"))
        s = stem(slug)
        if perStem.get(s, 0) >= STEM_CAP:
            continue
        perStem[s] = perStem.get(s, 0) + 1
        roster[slug] = ev
        if len(roster) >= cap:
            break
    log(f"roster after <= {STEM_CAP}-per-stem cap: {len(roster)} slugs "
        f"(stem pool {len(perStem)}); volume floor ${floor:,.0f}")

    totalVol = sum(tus.eventVolume(ev) for ev in roster.values())
    log(f"roster total gamma volume ${totalVol:,.0f}")

    ordered = [str(roster[s]["slug"]) for s in sorted(roster)]
    header = "\n".join(
        f"# {line}".rstrip() for line in [
            "Mid-band top-up roster: fresh military-extension cohort for",
            f"research/midbandTopup.md (option a, pre-registered). {len(ordered)}",
            f"resolved military slugs, gamma volume >= ${floor:,.0f},",
            f"<= {STEM_CAP}-per-stem cap, excluding data/, data/universe, data/oos,",
            "data/oosExpansion, data/midTopup and every existing roster config.",
            "Selected on gamma event metadata ONLY (no fill/burst content seen).",
            "Pure target: data/midTopup (R16's mid-band [0.55,0.85) cell top-up).",
        ])
    stemOf = {slug: stem(slug) for slug in ordered}
    body = []
    for s in sorted(set(stemOf.values())):
        group = [g for g in ordered if stemOf[g] == s]
        body.append(f"    # stem: {s} ({len(group)})")
        body.extend(f"    - {g}" for g in group)
    out = ROOT / "configs" / "midbandTopup.yaml"
    out.write_text(
        f"{header}\nsplitDate: '2026-01-01'\n\nfetch:\n"
        f"  dataDir: data/midTopup\n  eventSlugs:\n" + "\n".join(body) + "\n")
    log(f"wrote {out} ({len(ordered)} slugs)")


if __name__ == "__main__":
    main()
