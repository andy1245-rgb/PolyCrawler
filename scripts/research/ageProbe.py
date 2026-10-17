"""Methodology-attack check A4 (research/methodologyAttack.md): true-age probe
on the atAccFirst fraction of the OOS-expansion shipped cell.

A4's measured flaw: on the fetched-dir tapes, `ageDays`/`marketsSoFar` are
defined over the FETCH SCOPE only, and 40.6-72.7% of shipped-cell entries
begin at the account's first trade in the fetched tape — their "fresh" label
is unidentifiable from inside the data. This probe samples the doc's
pre-registered sample plan exactly: 50 accounts of the shipped cell
($5k/<=0.35/<=5d/<=3mkts) on [data/oosExpansion] whose entry sits at the
account's first fetched-tape trade (ageDays == 0), one Data API
`/activity?user=` call each, then compute true first-TRADE age at entry and
true distinct markets traded. If most are genuinely day-0 on Polymarket the
fetch-scope artifact is small; if they are weeks old, every cross-tape
freshness comparison must be re-derived from an out-of-tape source.

Responses are cached under data/raw/ageProbe/ (repo HttpSession convention,
append-only).

Run: uv run python scripts/research/ageProbe.py 2>&1 | tee -a logs/methodologyChecks.log
"""

import importlib.util
import json
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
DATA_API = "https://data-api.polymarket.com"
RATE = 2.0  # req/s on data-api, deliberately slower than Gamma pacing
PAGE = 500
MAX_PAGES = 2  # >=1000 pre-entry activity rows -> 'old' is certain enough


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "research" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from polycrawler.http import HttpSession  # noqa: E402


def main() -> None:
    t0 = time.time()
    d = _load("ageProbeTarget", "entrySweep.py")
    POPULATION = {"minUsd": 5000.0, "maxPrice": 0.35, "ageDays": 5.0, "marketsSoFar": 3}
    dirs = [str(ROOT / "data" / "oosExpansion")]
    entries = d.loadEntries(dirs, False)
    cell = d.filterCell(entries, POPULATION)
    atFirst = cell.filter(pl.col("ageDays") < 1e-9)
    accts = sorted(set(zip(atFirst["account"].to_list(), atFirst["ts"].to_list())))
    print(f"A4 probe: shipped cell n={cell.height}, atAccFirst fraction "
          f"{100 * atFirst.height / max(cell.height, 1):.1f}% ({atFirst.height}), "
          f"distinct (acct, entry) pairs {len(accts)}", flush=True)
    sample = random.Random(7).sample(accts, min(50, len(accts)))

    rows = []
    with httpx.Client(timeout=60.0,
                      headers={"User-Agent": "polycrawler2-age-probe"}) as client:
        session = HttpSession(client, hostRates={"data-api.polymarket.com": RATE},
                              dataDir="data")
        for i, (acct, entryTs) in enumerate(sample, 1):
            trades = []
            truncated = False
            for page in range(MAX_PAGES):
                entryUnix = int(entryTs.timestamp()) if isinstance(entryTs, datetime) else int(entryTs)
                key = f"user__{acct}__{entryUnix}__p{page}"
                payload = session.getJson(
                    f"{DATA_API}/activity", {"user": acct, "limit": PAGE,
                                             "offset": page * PAGE, "start": 0,
                                             "end": entryUnix - 1,
                                             "type": "TRADE"},
                    cacheKind="ageProbe", cacheKey=key)
                if not isinstance(payload, list):
                    print(f"  {i}/50 {acct}: bad payload, skipped raw", flush=True)
                    break
                if len(payload) < PAGE:
                    trades.extend(payload)
                    break
                trades.extend(payload)
                if page == MAX_PAGES - 1:
                    truncated = True
            if truncated:
                rows.append({"account": acct, "entryTs": entryTs, "status": "truncated"})
                print(f"  {i}/50 {acct}: >= {PAGE * MAX_PAGES} pre-entry trades "
                      f"-> certainly old (truncated)", flush=True)
                continue
            if not trades:
                rows.append({"account": acct, "entryTs": entryTs, "status": "no-data"})
                print(f"  {i}/50 {acct}: no pre-entry TRADE rows", flush=True)
                continue
            firstTs = min(r["timestamp"] for r in trades)
            nMarkets = len({r.get("conditionId") for r in trades if r.get("conditionId")})
            ageDays = (entryUnix - firstTs) / 86400
            rows.append({"account": acct, "entryTs": entryTs, "status": "ok",
                         "trueAgeDays": round(ageDays, 2), "trueMarkets": nMarkets,
                         "prevTrades": len(trades)})
            print(f"  {i}/50 {acct}: true age at entry {ageDays:.2f}d, "
                  f"{nMarkets} markets, {len(trades)} prev trades", flush=True)

    ok = [r for r in rows if r["status"] == "ok"]
    old = [r for r in ok if r["trueAgeDays"] > 5]
    mkt = [r for r in ok if r["trueMarkets"] > 3]
    fail = [r for r in ok if r["trueAgeDays"] > 5 or r["trueMarkets"] > 3]
    day0 = [r for r in ok if r["trueAgeDays"] <= 1]
    stat = {
        "dir": "data/oosExpansion", "sampled": len(sample),
        "ok": len(ok), "truncated": sum(r["status"] == "truncated" for r in rows),
        "noData": sum(r["status"] == "no-data" for r in rows),
        "trueAge_le1d": len(day0), "trueAge_1to5d": len(ok) - len(old) - len(day0),
        "trueAge_gt5d": len(old), "trueMarkets_gt3": len(mkt),
        "gateFail_either": len(fail),
        "medTrueAge_ok": sorted(r["trueAgeDays"] for r in ok)[len(ok) // 2] if ok else None,
        "medPrevTrades_ok": sorted(r["prevTrades"] for r in ok)[len(ok) // 2] if ok else None,
    }
    print("\n-- A4 verdict counts (shipped cell, atAccFirst, data/oosExpansion) --",
          flush=True)
    print(json.dumps(stat, indent=1), flush=True)
    out = ROOT / "data" / "raw" / "ageProbe" / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"stat": stat, "rows": rows},
                              default=str), )
    print(f"wrote {out} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
