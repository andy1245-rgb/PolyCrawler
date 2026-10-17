"""Methodology-attack check A8 (research/methodologyAttack.md): fee-mark
crawl + fee-net regrade of the graded cells.

A8's flaw: no fee term exists anywhere in the graded returns — the
markets.parquet schema has no feesEnabled column (confirmed, this run) and
every burst ret formula is gross. The spec asked for a Gamma
/markets?condition_ids= batch crawl; Gamma no longer supports condition-id
queries at all (verified 2026-10-16: `condition_ids` returns 0 rows,
`condition_id` misparses), so the crawl resolves fee fields per condition id
from the CLOB API instead (GET /markets/<conditionId> -> maker_base_fee /
taker_base_fee / neg_risk), rates-capped at 4 req/s. Fee-mark flag := any
nonzero fee field. Regrade: on fee markets the winner side pays 10% of
winnings — ret_adj = 0.9/fillPrice - 1 — computed on the cached entry tapes
(in-sample [data, data/universe] and OOS [data/oosExpansion], SEPARATELY as
always); losers and non-fee winners unchanged.

INCONCLUSIVE is an allowed outcome: reported with coverage share.

Run: uv run python scripts/research/feeMarkRegrade.py 2>&1 \
        | tee -a logs/methodologyChecks.log
"""

import importlib.util
import json
import sys
import time
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
CLOB = "https://clob.polymarket.com"
RATE = 4.0  # req/s cap per the check spec


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "research" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from polycrawler.http import HttpSession, cachePath, writeJson  # noqa: E402


def crawlFeeMarks(ids: list[str]) -> dict[str, dict]:
    with httpx.Client(timeout=60.0,
                      headers={"User-Agent": "polycrawler2-fee-mark-regrade"}) as client:
        session = HttpSession(client, hostRates={CLOB.replace("https://", ""): RATE},
                              dataDir="data")
        out: dict[str, dict] = {}
        for i, mid in enumerate(ids, 1):
            path = cachePath("data", "feeMarkRegrade", f"clob__{mid}")
            if path.exists():
                payload = json.loads(path.read_text())
            else:
                r = session.getJson(f"{CLOB}/markets/{mid}")
                if not isinstance(r, dict):
                    payload = {"error": r}
                else:
                    payload = {k: r.get(k) for k in
                               ["condition_id", "question", "maker_base_fee",
                                "taker_base_fee", "neg_risk", "is_50_50_outcome"]}
                path.parent.mkdir(parents=True, exist_ok=True)
                writeJson(path, payload)
            if i % 250 == 0:
                print(f"  crawled/cached {i}/{len(ids)} ({time.time() - t0:.0f}s)", flush=True)
            out[mid] = payload
        return out


def feeFlag(m: dict) -> int:
    if "error" in m or not m:
        return 0
    return int((m.get("maker_base_fee") or 0) != 0 or (m.get("taker_base_fee") or 0) != 0)


def feeNetRet(entries: pl.DataFrame, feeMap: dict[str, dict], dirTag: str) -> dict:
    mk = entries.group_by("marketId").agg(n=pl.len()).to_dicts()
    mids = [r["marketId"] for r in mk]
    fee = {mid: feeFlag(feeMap.get(mid, {"error": 1})) for mid in mids}
    df = entries.with_columns(
        feeMark=pl.col("marketId").map_elements(lambda x: fee.get(x, 0), return_dtype=pl.Int32))
    entFeeShare = 100 * df["feeMark"].mean()
    winFeeShare = 100 * df.filter(pl.col("won"))["feeMark"].mean()
    df = df.with_columns(
        retRealFee=pl.when(pl.col("won") & (pl.col("feeMark") == 1))
        .then(0.9 / pl.col("fillPrice") - 1).otherwise(pl.col("retReal")))
    import random
    esw = _load("feeMarkRegradeEs", "entrySweep.py")
    gross = esw.evaluate(df, random.Random(7))
    net = esw.evaluate(df.with_columns(pl.col("retRealFee").alias("retReal")), random.Random(7))
    print(f"  [{dirTag}] entries on fee markets: {entFeeShare:.1f}% | winners on fee "
          f"markets: {winFeeShare:.1f}% | retReal {gross.get('ret'):+.3f} -> "
          f"fee-net {net.get('ret'):+.3f} (drag {100 * (gross.get('ret', 0) - net.get('ret', 0)):.1f}pp) "
          f"| p5 {gross.get('p5')} -> {net.get('p5')} | P>0 {gross.get('p')} -> {net.get('p')}",
          flush=True)
    return {"entriesFeeShare": round(entFeeShare, 1),
            "winnersFeeShare": round(winFeeShare, 1),
            "grossRet": gross.get("ret"), "netRet": net.get("ret"),
            "grossP5": gross.get("p5"), "netP5": net.get("p5"),
            "grossP": gross.get("p"), "netP": net.get("p")}


t0 = time.time()


def main() -> None:
    esw = _load("feeMarkRegradeEs", "entrySweep.py")
    rd = _load("feeMarkRegradeRd", "researchData.py")
    dirsets = {
        "in-sample": ([str(p) for p in rd.researchDataDirs()], "shipped"),
        "oosExpansion": ([str(ROOT / "data" / "oosExpansion")], "shipped"),
    }
    results: dict[str, dict] = {}
    for name, (dirs, cellKind) in dirsets.items():
        print(f"\n-- fee-mark crawl [{name}]: {dirs} ({time.time() - t0:.0f}s) --", flush=True)
        mk = pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs],
                       how="diagonal_relaxed")
        ids = sorted(mk["marketId"].unique().to_list())
        feeMap = crawlFeeMarks(ids)
        flags = [feeFlag(v) for v in feeMap.values() if "error" not in v]
        errs = sum(1 for v in feeMap.values() if "error" in v)
        print(f"  markets crawled {len(feeMap)} (errors {errs}) | fee-marked "
              f"{sum(flags)}/{len(flags)} = {100 * sum(flags) / max(len(flags), 1):.1f}%",
              flush=True)
        fees = [v.get("taker_base_fee") or 0 for v in feeMap.values() if "error" not in v]
        print(f"  taker_base_fee distribution: 0-share "
              f"{100 * sum(1 for f in fees if f == 0) / max(len(fees), 1):.1f}%, "
              f"nonzero median {sorted(f for f in fees if f != 0 or True)[len(fees) // 2] if fees else None}",
              flush=True)
        entries = esw.loadEntries(dirs, False)
        for label, cell in [("shipped $5k/<=0.35", {"minUsd": 5000.0, "maxPrice": 0.35,
                                                    "ageDays": 5, "marketsSoFar": 3}),
                            ("flagship $10k/<=0.35", {"minUsd": 10000.0, "maxPrice": 0.35,
                                                      "ageDays": 5, "marketsSoFar": 3})]:
            df = esw.filterCell(entries, cell)
            print(f"  cell {label}: n={df.height} ({time.time() - t0:.0f}s)", flush=True)
            results[f"{name}:{label}"] = feeNetRet(df, feeMap, label)
    out = ROOT / "data" / "raw" / "feeMarkRegrade" / "summary.json"
    out.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {out} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
