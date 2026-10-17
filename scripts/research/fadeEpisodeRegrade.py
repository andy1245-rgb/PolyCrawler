"""Methodology-attack check #0 (research/methodologyAttack.md A3 follow-up on
research/oosFailureDiagnosis.md Q2): regrade the OOS fade-line PASS under
episode-level regrouping. The oosFailureDiagnosis bottom line pre-registered
exactly this step: "grade the fade line with episode-level regrouping +
top-event share — the 30 fade events MUST not be secretly 2-3 factories".

Recipe: rebuild the fade population exactly per oosFailureDiagnosis.q2Fade
(importlib-by-path, zero re-implementation), then run the R7 episode
machinery over it — epT.buildUnits on the OOS entry tape (per-tape K*
derivation), epT.episodeGate (K* bar >= 0.80, >=3 episodes), and the
composed verdict against the pre-registered per-event bar (p5 > 0 AND
P(>0) >= 85%). Top-episode PnL share is computed on the same labels — the
fade candidate is an artifact if it collapses to <3 episodes or the top
episode owns >=60% of total PnL.

Run: uv run python scripts/research/fadeEpisodeRegrade.py 2>&1 \
        | tee -a logs/methodologyChecks.log
"""

import importlib.util
import random
import sys
from pathlib import Path

import polars as pl

t0 = 0.0
ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "research" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    import time
    t0 = time.time()
    diag = _load("esw", "entrySweep.py")
    d = _load("oosFailureDiagnosis", "oosFailureDiagnosis.py")
    epT = _load("episodeTransport", "episodeTransport.py")

    dirs = [str(ROOT / "data" / "oosExpansion")]
    entries = d.esw.loadEntries(dirs, False)
    cell = d.esw.filterCell(entries, d.FLAGSHIP)
    print(f"flagship cell n={cell.height} events={cell['eventSlug'].n_unique()} "
          f"({time.time() - t0:.0f}s)", flush=True)

    _, fade = d.q2Fade(dirs, cell)
    ev = d.esw.evaluate(fade, random.Random(7))
    print(f"\n-- fade population (q2Fade recipe verbatim): n={fade.height} "
          f"events={ev.get('events')} ret={ev.get('ret')} "
          f"compWin={100 * fade['fadeWon'].mean():.1f}% "
          f"p5={ev.get('p5')} P>0={ev.get('p')} --", flush=True)

    units = epT.buildUnits(entries)
    epT.printUnits(units, entries.height)

    gate = epT.episodeGate(fade, units)
    eventGate = epT.eventGate(ev.get("p5"), ev.get("p"))
    verdict = epT.composeVerdict(eventGate, gate["epVerdict"])

    label = units["labels"]
    eps = (fade.with_columns(episode=pl.col("eventSlug").map_elements(
                lambda s: label.get(s) or ("solo:" + s), return_dtype=pl.String))
           .group_by("episode")
           .agg(pnl=(pl.col("retReal") * 100).sum(), n=pl.len(),
                slugs=pl.col("eventSlug").unique().sort())
           .sort("pnl", descending=True))
    total = eps["pnl"].sum()
    top = eps.row(0, named=True)
    topShare = round(100 * top["pnl"] / total, 1) if total > 0 else 100.0
    print(f"\n-- episode regrade of the OOS fade population "
          f"(K*={units['k']}, {units['gate']}) --", flush=True)
    with pl.Config(fmt_str_lengths=80, tbl_width_chars=200, tbl_rows=40):
        print(eps.select("episode", "pnl", "n", "slugs"))
    print(f"episodes={gate['episodes']} epP={gate['epP']} epP5={gate['epP5']} "
          f"exTopP={gate['exTopP']} exTopRet={gate['exTopRet']}", flush=True)
    print(f"top episode: {top['episode']} pnl={top['pnl']:.0f} "
          f"({-top['pnl'] / total * 100 if total < 0 else topShare:.1f}% of total "
          f"{total:.0f}) share={topShare}%", flush=True)
    print(f"per-event gate: {eventGate} (p5={ev.get('p5')} P>0={ev.get('p')})", flush=True)
    print(f"episode gate: {gate['epVerdict']}", flush=True)
    artifact = gate["episodes"] < 3 or topShare >= 60.0
    print(f"fades={fade.height} verdict={verdict} "
          f"artifact(collapse to <3 episodes or top-share >=60%): "
          f"{'YES' if artifact else 'no'} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
