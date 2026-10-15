"""Engine-vs-research parity, recomputed on the CURRENT tape.

The earlier parity claim (engine reproduces the military research cell, 429 vs
433 trades / +119.3% vs +116%) was measured on a specific data snapshot.
fills.parquet keeps moving under the daily watcher, so a pinned number drifts
silently. This script rebuilds BOTH sides on the same current data and reports
the residual buckets, so the claim can be re-established whenever the tape
changes.

Semantics side by side (militaryCategory.py conventions):
  research side = military burst cell: WHOLE-burst aggregate >= minNetUsd at
                  avg price <= maxEntryPrice, fresh (ageDays/marketsSoFar over
                  the full tape), ret = 1/price - 1
  engine side   = pc2 rule-mode replay: trigger at the first RUNNING PREFIX
                  satisfying usd+avg gates, entry delaySec later with
                  slippage, exitMode holdToResolution

Residual buckets:
  overlap                  picks on both sides
  enginePrefixDrift        engine entered on a legal prefix; later fills pushed
                           the final burst avg above the price gate
  clusterAlreadyCopied     pick whose accountGroup already produced the copy
                           from a sibling wallet in the same cluster
  notExecutedLegalPrefix   legal running prefix exists but the delayed entry
                           never landed inside the gates
  noLegalPrefix            final-aggregate-only picks no running rule can see

Run:  uv run python scripts/research/engineParity.py
      [--config configs/militaryBacktest.yaml]
"""

import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data" / "parity" / "engineResearchParity.json"
RUNS_DIR = ROOT / "runs"

spec = importlib.util.spec_from_file_location(
    "dob", ROOT / "scripts" / "research" / "duneOrderBurst.py")
dob = importlib.util.module_from_spec(spec)
sys.modules["dob"] = dob
spec.loader.exec_module(dob)

sys.path.insert(0, str(ROOT / "scripts"))
import backtest as backtestCli  # noqa: E402

from polycrawler.backtest import dirsFromConfig, loadInputs, runBacktest  # noqa: E402
from polycrawler.strategy import normalizeClusterMap  # noqa: E402


def marketsFrame(dirs: list[Path]) -> pl.DataFrame:
    markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet")
                          for d in dirs],
                         how="diagonal_relaxed")
               .unique("marketId", keep="last")
               .select("marketId", "eventSlug", "winner",
                       pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
    return markets.with_columns(
        isMilitary=pl.col("eventSlug").map_elements(
            lambda s: any(k in (s or "").lower() for k in dob.MILITARY),
            return_dtype=pl.Boolean))


def burstTape(dirs: list[Path], cols: list[str]) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet").select(cols)
                      for d in dirs])
    raw = (lazy.filter(pl.col("side") == "BUY")
           .sort("account", "marketId", "outcome", "ts")
           .with_columns(
               burstIdx=(pl.col("ts").diff().over("account", "marketId", "outcome")
                         .fill_null(pl.duration(days=1)) > pl.duration(minutes=10))
               .cast(pl.Int32).cum_sum().over("account", "marketId", "outcome")))
    firstSeen = lazy.group_by("account").agg(firstTs=pl.col("ts").min())
    return raw, firstSeen


def researchPicks(raw: pl.LazyFrame, firstSeen: pl.LazyFrame, markets: pl.DataFrame,
                  params) -> tuple[pl.DataFrame, dict]:
    """Whole-burst military cell + the unfiltered burst rows for the prefix pool."""
    milIds = set(markets.filter(pl.col("isMilitary"))["marketId"].to_list())
    bursts = (raw.with_columns(milHit=pl.col("marketId").is_in(list(milIds)))
              .select("ts", "account", "marketId", "outcome", "side", "size",
                      "price", "burstIdx", "milHit")
              .collect())
    final = (bursts.group_by("account", "marketId", "outcome", "burstIdx")
             .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(),
                  shares=pl.col("size").sum())
             .with_columns(price=pl.col("usd") / pl.col("shares"))
             .drop("shares"))
    fs = firstSeen.collect()
    keyed = (final.join(markets, on="marketId").join(fs, on="account")
             .sort("account", "ts")
             .with_columns(
                 marketsSoFar=pl.col("marketId").is_first_distinct()
                 .cast(pl.Int32).cum_sum().over("account"),
                 ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                 won=pl.col("outcome") == pl.col("winner"),
                 ret=pl.when(pl.col("winner").is_null()).then(None)
                 .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1)
                 .otherwise(-1.0))
             .filter(pl.col("ret").is_not_null())
             .filter(pl.col("isMilitary"))
             .filter((pl.col("usd") >= params.minNetUsd)
                     & (pl.col("price") <= params.maxEntryPrice)
                     & (pl.col("ageDays") <= params.maxAccountAgeDays)
                     & (pl.col("marketsSoFar") <= params.maxMarketsSoFar)))
    metrics = {"n": keyed.height,
               "winRate": round(keyed["won"].mean(), 4),
               "ret": round(keyed["ret"].mean(), 4)}
    return keyed, metrics


def prefixPool(bursts: pl.DataFrame, fs: pl.DataFrame, markets: pl.DataFrame,
               params) -> set[tuple[str, str, str]]:
    """Keys whose RUNNING prefix ever passed usd+avg+fresh gates at a
    fill boundary — what the fill-by-fill engine can legally enter."""
    running = (bursts.join(fs, on="account")
               .join(markets.select("marketId", "isMilitary").lazy(), on="marketId")
               .sort(["account", "marketId", "outcome", "ts"])
               .with_columns(
                   usdRun=(pl.col("size") * pl.col("price")).cum_sum()
                   .over(["account", "marketId", "outcome", "burstIdx"]),
                   sharesRun=pl.col("size").cum_sum()
                   .over(["account", "marketId", "outcome", "burstIdx"]))
               .filter(pl.col("isMilitary"))
               .filter(
                   (pl.col("usdRun") >= params.minNetUsd)
                   & ((pl.col("usdRun") / pl.col("sharesRun")) <= params.maxEntryPrice)
                   & ((pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400
                      <= params.maxAccountAgeDays))
               .with_columns(
                   marketsSoFar=pl.col("marketId").is_first_distinct()
                   .cast(pl.Int32).cum_sum().over("account")))
    running = running.filter(pl.col("marketsSoFar") <= params.maxMarketsSoFar)
    return set(map(tuple, running.select("account", "marketId", "outcome")
                   .collect().iter_rows()))


def residualBuckets(finalPicks: list[tuple], executedKeys: set, prefixKeys: set,
                    executedGroups: set, clusterMap: dict) -> dict:
    groups = normalizeClusterMap(clusterMap) or {}
    out: dict = {"overlap": 0, "clusterAlreadyCopied": [], "notExecutedLegalPrefix": [],
                 "noLegalPrefix": [], "enginePrefixDrift": 0}
    for account, marketId, outcome in finalPicks:
        if (account, marketId, outcome) in executedKeys:
            out["overlap"] += 1
            continue
        grp = groups.get(account, account)
        if (grp, marketId, outcome) in executedGroups:
            out["clusterAlreadyCopied"].append((account, marketId, outcome))
        elif (account, marketId, outcome) in prefixKeys:
            out["notExecutedLegalPrefix"].append((account, marketId, outcome))
        else:
            out["noLegalPrefix"].append((account, marketId, outcome))
    out["enginePrefixDrift"] = len(executedKeys - set(finalPicks))
    return out


def engineSide(params, dirs: list[Path], loaded) -> tuple[dict, Path, dict]:
    fills, markets, accounts, clusterMap = loadInputs(dirs)
    endTs = fills.select(pl.col("ts").max()).collect().item()
    startTs = datetime(loaded.splitDate.year, loaded.splitDate.month,
                       loaded.splitDate.day, tzinfo=timezone.utc)
    result = runBacktest(fills, markets, accounts, params, startTs, endTs,
                         clusterMap=clusterMap, runsDir=RUNS_DIR)
    runDir = RUNS_DIR / result.paramsHash
    summary = json.loads((runDir / "summary.json").read_text())
    return summary, runDir, clusterMap


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/militaryBacktest.yaml")
    parser.add_argument("--data-dir", action="append", default=None,
                        help="override the config's data dirs (repeatable)")
    args = parser.parse_args()
    configPath = Path(args.config)
    if not configPath.is_absolute():
        configPath = ROOT / configPath
    params, loaded = backtestCli.paramsFrom(configPath, [])
    # dir resolution is routed through the config system: CLI --data-dir >
    # fetch.dataDirs > fetch.dataDir. The pinned config spans both dirs, so
    # the default matches the old hardcoded [data, data/universe] scope.
    dirs = dirsFromConfig(ROOT, args.data_dir, loaded)

    markets = marketsFrame(dirs)
    raw, fs = burstTape(dirs, ["ts", "account", "marketId", "outcome", "side", "size", "price"])
    keyed, researchMetrics = researchPicks(raw, fs, markets, params)
    print(f"research cell: {researchMetrics} ({time.time() - t0:.0f}s)")
    prefixKeys = prefixPool(raw, fs, markets, params)
    print(f"prefix pool: {len(prefixKeys)} keys ({time.time() - t0:.0f}s)")

    summary, runDir, clusterMap = engineSide(params, dirs, loaded)
    print(f"engine: trades {summary['tradeCount']} winRate {summary['winRate']:.3f} "
          f"returnOnDeployed {summary['returnOnDeployed']:.3f} ({time.time() - t0:.0f}s)")
    trades = pl.read_parquet(runDir / "trades.parquet")
    executedKeys = set(map(tuple, trades.select("account", "marketId", "outcome").iter_rows()))
    executedGroups = set(map(tuple, trades.select("accountGroup", "marketId", "outcome").iter_rows()))
    finalPicks = [tuple(r) for r in keyed.select("account", "marketId", "outcome").iter_rows()]
    buckets = residualBuckets(finalPicks, executedKeys, prefixKeys, executedGroups, clusterMap)

    print("\n-- residual buckets (research-cell picks not executed) --")
    n = len(finalPicks)
    for name in ["overlap", "enginePrefixDrift", "clusterAlreadyCopied",
                 "notExecutedLegalPrefix", "noLegalPrefix"]:
        count = buckets[name] if isinstance(buckets[name], int) else len(buckets[name])
        print(f"  {name:>24}: {count:>5}  ({count / n:.1%} of {n})")

    out = {"research": researchMetrics,
           "engine": {k: summary[k] for k in ["tradeCount", "winRate", "returnOnDeployed",
                                              "totalPnl", "capitalDeployed", "endTs"]},
           "buckets": {k: (v if isinstance(v, int) else {"n": len(v), "keys": v[:25]})
                       for k, v in buckets.items()},
           "config": str(configPath.relative_to(ROOT)),
           "fillsEndTs": str(summary.get("endTs")),
           "generatedAt": datetime.now(timezone.utc).isoformat()}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwritten {OUT_PATH} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
