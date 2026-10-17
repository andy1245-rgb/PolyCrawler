"""Benchmark step-1 flag variants against the 20-account manual verdicts.

Ground truth: research/sampleVerdicts.csv (manual review, see sampleReview.md).
Sample: the same 20 accounts drawn with seed=7 from the 236 flagged on
configs/insiderCases.yaml, so the current rule's precision here is exact.

Positive class definitions:
  loose  = insider | likely_insider   (8 of 20)
  strict = insider only               (5 of 20)

Run:  uv run python scripts/research/verdictBenchmark.py
"""

import csv
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]

verdicts = {}
for r in csv.DictReader(open(ROOT / "data/research/sampleVerdicts.csv")):
    verdicts[r["account"]] = r["verdict"]

labeled = {r["wallet"] for r in csv.DictReader(open(ROOT / "data/research/knownWallets.csv"))}
sus = pl.read_parquet(ROOT / "data/suspicious.parquet").filter(
    pl.col("suspicious") & ~pl.col("account").is_in(list(labeled))
)
sample = sus.sample(20, seed=7).with_columns(
    pl.col("account").replace(verdicts).alias("verdict")
)

LOOSE = {"insider", "likely_insider"}
STRICT = {"insider"}


def score(name: str, mask) -> None:
    flagged = sample.filter(mask)
    for label, truth in (("loose", LOOSE), ("strict", STRICT)):
        tp = sum(1 for v in flagged["verdict"] if v in truth)
        n_truth = sum(1 for v in sample["verdict"] if v in truth)
        rec = tp / n_truth if n_truth else float("nan")
        prec = tp / flagged.height if flagged.height else float("nan")
        print(f"  {name:38s} {label:6s} flagged={flagged.height:3d} prec={prec:5.0%} recall={rec:5.0%}")


print(f"Sample: {sample.height} accounts (seed=7). Verdicts: "
      f"{sum(1 for v in sample['verdict'] if v in LOOSE)} loose-positive, "
      f"{sum(1 for v in sample['verdict'] if v in STRICT)} strict-positive\n")

print("Current rule (all 20 are flagged by construction):")
score("rule A as-is", pl.lit(True))

print("\nSingle-feature gates on the flagged sample:")
score("marketsTraded <= 1 (one-shot)", pl.col("marketsTraded") <= 1)
score("marketsTraded <= 2", pl.col("marketsTraded") <= 2)
score("accountAgeDays <= 3", pl.col("accountAgeDays") <= 3)
score("accountAgeDays <= 7", pl.col("accountAgeDays") <= 7)
score("buyUsd >= 5000", pl.col("buyUsd") >= 5000)
score("buyUsd >= 10000", pl.col("buyUsd") >= 10000)
score("avgBuyPrice <= 0.20", pl.col("avgBuyPrice") <= 0.20)

print("\nCombined variants:")
score("one-shot + big (>=5k)", (pl.col("marketsTraded") <= 1) & (pl.col("buyUsd") >= 5000))
score("fresh (<=7d) + big (>=5k)", (pl.col("accountAgeDays") <= 7) & (pl.col("buyUsd") >= 5000))
score("one-shot + any price", pl.col("marketsTraded") <= 1)
score("concentrated (isFocused)", pl.col("isFocused"))
score("focused + big (>=5k)", pl.col("isFocused") & (pl.col("buyUsd") >= 5000))
score("signalCount >= 5" if "signalCount" in sample.columns else "n/a", pl.col("signalCount") >= 5)

print("\nPer-account features vs verdict (sorted worst-first by verdict severity):")
cols = ["account", "verdict", "accountAgeDays", "marketsTraded", "buyUsd", "avgBuyPrice", "profitUsd"]
print(sample.select(cols).sort("verdict", "marketsTraded"))

# ---------------------------------------------------------------------------
# Universe sample: seed=8 from the 89 flagged on the 72-event universe.
# Verdicts made from activity dossiers (scripts/research/universeDossiers.py).
# ---------------------------------------------------------------------------
print("\n=== Universe sample (seed=8, non-military events) ===")

uverd = {}
for r in csv.DictReader(open(ROOT / "data/research/universeVerdicts.csv")):
    uverd[r["account"]] = r["verdict"]

usus = pl.read_parquet(ROOT / "data/universe/suspicious.parquet").filter(
    pl.col("suspicious") & ~pl.col("account").is_in(list(labeled))
)
usample = usus.sample(20, seed=8).with_columns(pl.col("account").replace(uverd).alias("verdict"))
umarkets = pl.read_parquet(ROOT / "data/universe/markets.parquet").select("marketId", "resolvedAt")
usample = usample.join(umarkets, left_on="bestMarketId", right_on="marketId").with_columns(
    (pl.col("resolvedAt") - pl.col("firstBuyTs")).dt.total_seconds().truediv(3600).alias("leadHours")
)

for label, truth in (("loose", LOOSE), ("strict", STRICT)):
    n_truth = sum(1 for v in usample["verdict"] if v in truth)
    print(f"\n  {label}: {n_truth} positives of {usample.height}")


def uscore(name: str, mask) -> None:
    flagged = usample.filter(mask)
    line = f"  {name:38s}"
    for label, truth in (("loose", LOOSE), ("strict", STRICT)):
        tp = sum(1 for v in flagged["verdict"] if v in truth)
        n_truth = sum(1 for v in usample["verdict"] if v in truth)
        prec = tp / flagged.height if flagged.height else float("nan")
        rec = tp / n_truth if n_truth else float("nan")
        line += f" | {label} p={prec:4.0%} r={rec:4.0%}"
    print(line)


uscore("rule A as-is", pl.lit(True))
uscore("leadHours <= 24", pl.col("leadHours") <= 24)
uscore("leadHours <= 72", pl.col("leadHours") <= 72)
uscore("leadHours <= 168 (7d)", pl.col("leadHours") <= 168)
uscore("leadHours <= 336 (14d)", pl.col("leadHours") <= 336)
uscore("marketsTraded <= 3", pl.col("marketsTraded") <= 3)
uscore("marketsTraded <= 1", pl.col("marketsTraded") <= 1)
uscore("lead<=168 + mkts<=3", (pl.col("leadHours") <= 168) & (pl.col("marketsTraded") <= 3))
uscore("lead<=336 + mkts<=3", (pl.col("leadHours") <= 336) & (pl.col("marketsTraded") <= 3))

print("\nUniverse per-account:")
print(usample.select(
    "account", "verdict", "leadHours", "marketsTraded", "buyUsd", "avgBuyPrice", "profitUsd"
).sort("verdict", "leadHours"))
