"""Parameter sensitivity sweep for the military fresh-big-bet rule, using
realistic fills (next taker price within 5 minutes). Goal: pick thresholds
that sit on a plateau, not a peak — the rule we ship live must be robust to
parameter drift, not tuned to the historical maximum.

Grid: minUsd {2k,5k,10k,20k} x maxPrice {0.35,0.50,0.65} x ageDays {2,3,5}.
Reported per cell: n, return at realistic fill, bootstrap P(>0), H1/H2,
and a stability score = mean of neighbor-cell returns.

Run:  uv run python scripts/research/militarySweep.py
"""

import random
import time
from datetime import datetime, timezone

import polars as pl

t0 = time.time()
MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela", "nato")
FILL_WINDOW_SEC = 300

dirs = ["data", "data/universe"]
markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
           .unique("marketId", keep="last")
           .select("marketId", "eventSlug", "winner", pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
militarySlugs = sorted({s for s in markets["eventSlug"].unique().to_list()
                        if any(k in (s or "").lower() for k in MILITARY)})
markets = markets.with_columns(isMilitary=pl.col("eventSlug").is_in(militarySlugs))

cols = ["ts", "account", "marketId", "outcome", "side", "size", "price"]
lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet").select(cols) for d in dirs])
firstSeen = lazy.group_by("account").agg(firstTs=pl.col("ts").min()).collect()
entries = (lazy.filter(pl.col("side") == "BUY").drop("side")
           .sort("account", "marketId", "outcome", "ts")
           .with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome").fill_null(pl.duration(days=1))
                                > pl.duration(minutes=10)).cum_sum().over("account", "marketId", "outcome"))
           .group_by("account", "marketId", "outcome", "burst")
           .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(), shares=pl.col("size").sum())
           .with_columns(price=pl.col("usd") / pl.col("shares"))
           .drop("burst", "shares")
           .collect())
entries = (entries.join(markets, on="marketId").join(firstSeen, on="account").sort("account", "ts")
           .with_columns(marketsSoFar=pl.col("marketId").is_first_distinct().cast(pl.Int32).cum_sum().over("account"),
                         ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                         won=pl.col("outcome") == pl.col("winner"),
                         ret=pl.when(pl.col("winner").is_null()).then(None)
                         .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1).otherwise(-1.0))
           .filter(pl.col("ret").is_not_null()))
tape = (lazy.filter(pl.col("side") == "BUY")
        .select("ts", "marketId", "outcome", "price").sort("marketId", "outcome", "ts").collect())
tape = (tape.with_columns(
    nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"),
    nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"),
).with_columns(
    fillPrice=pl.when((pl.col("nextTs") - pl.col("ts")).dt.total_seconds() <= FILL_WINDOW_SEC)
    .then(pl.col("nextPrice")).otherwise(pl.col("price")),
)
    .unique(subset=["ts", "marketId", "outcome"], keep="last"))
entries = (entries.drop("price")
           .join(tape.select("ts", "marketId", "outcome", "price", "fillPrice"),
                 on=["ts", "marketId", "outcome"], how="left")
           .with_columns(
               retReal=pl.when(pl.col("winner").is_null()).then(None)
               .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("fillPrice") - 1).otherwise(-1.0)))
print(f"entries {entries.height} ({time.time()-t0:.0f}s)", flush=True)

mil = entries.filter(pl.col("isMilitary"))
mid = datetime(2025, 6, 1, tzinfo=timezone.utc)
rng = random.Random(7)
base = mil.filter((pl.col("marketsSoFar") <= 3))

grid = {}
AXES = ([2000, 5000, 10000, 20000], [0.35, 0.50, 0.65], [2, 3, 5])
for iu, minUsd in enumerate(AXES[0]):
    for ip, maxPx in enumerate(AXES[1]):
        for ia, age in enumerate(AXES[2]):
            df = base.filter((pl.col("usd") >= minUsd) & (pl.col("price") <= maxPx)
                             & (pl.col("ageDays") <= age))
            if df.height < 20:
                grid[(iu, ip, ia)] = {"n": df.height, "ret": None, "p": 0}
                continue
            ev = (df.group_by("eventSlug").agg(pnl=(pl.col("retReal") * 100).sum(), cap=pl.len() * 100.0)
                  .with_columns(r=pl.col("pnl") / pl.col("cap")))
            events = list(ev.iter_rows(named=True))
            boots = []
            for _ in range(1000):
                samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
                boots.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
            grid[(iu, ip, ia)] = {
                "n": df.height,
                "ret": round(df["retReal"].mean(), 3),
                "p": sum(1 for b in boots if b > 0) / len(boots),
                "h1": round(df.filter(pl.col("ts") < mid)["retReal"].mean(), 3),
                "h2": round(df.filter(pl.col("ts") >= mid)["retReal"].mean(), 3),
            }

print(f"{'minUsd':>7} {'maxPx':>6} {'age':>4} {'n':>7} {'ret':>7} {'P(>0)':>6} {'H1':>7} {'H2':>7} {'stability':>9}")
for (iu, ip, ia), val in grid.items():
    header = f"{AXES[0][iu]:>7} {AXES[1][ip]:>6} {AXES[2][ia]:>4} {val['n']:>7}"
    if val["ret"] is None:
        print(f"{header} {'-':>7}")
        continue
    neighbors = []
    for du, dp, da in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)):
        n2 = grid.get((iu + du, ip + dp, ia + da))
        if n2 and n2["ret"] is not None:
            neighbors.append(n2["ret"])
    stab = sum(neighbors) / len(neighbors) if neighbors else float("nan")
    print(f"{header} {val['ret']:>+7.3f} {val['p']:>6.0%} "
          f"{val['h1']:>+7.3f} {val['h2']:>+7.3f} {stab:>+9.3f}")
print(f"done {time.time()-t0:.0f}s")
