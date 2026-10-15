"""Military-category test: fresh-big-bet copying restricted to military and
strike-timing events (the "next test" from research/freshAccountSignal.md).

Universe: data/ + data/universe/ (including the military siblings from
configs/militaryUniverse.yaml). Military events are selected by slug keyword.
Comparison sets:
  - fresh big bet on military events (>= $1k / $5k, <= 0.50)
  - anyone big bet on military events (benchmark)
  - fresh big bet on non-military events (the old result, for contrast)
Robustness: event-level bootstrap (2000 resamples), time-half split,
slippage on the copy price.

Run:  uv run python scripts/research/militaryCategory.py
"""

import random
import time
from datetime import datetime, timezone

import polars as pl

t0 = time.time()
MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela",
            "nato", "strike")

dirs = ["data", "data/universe"]
markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
           .unique("marketId", keep="last")
           .select("marketId", "eventSlug", "winner", pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
militarySlugs = sorted({s for s in markets["eventSlug"].unique().to_list()
                        if any(k in (s or "").lower() for k in MILITARY)})
print(f"military events: {len(militarySlugs)}")
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
# Realistic fill: pay the NEXT taker price seen in the same (marketId, outcome)
# within fillWindowSec of our copy, instead of the insider's own price. This is
# a data-driven impact/slippage estimate. Fills with no follow-up trade in the
# window keep their own price (quiet market ~= no impact).
FILL_WINDOW_SEC = 300
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

fresh = (pl.col("ageDays") <= 3) & (pl.col("marketsSoFar") <= 3)
mid = datetime(2025, 6, 1, tzinfo=timezone.utc)
rng = random.Random(7)


def report(name: str, df: pl.DataFrame) -> dict:
    if df.height == 0:
        return {"set": name, "n": 0}
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")))
    events = list(ev.iter_rows(named=True))
    boots = []
    for _ in range(2000):
        samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
        boots.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
    boots.sort()
    h1 = df.filter(pl.col("ts") < mid)["ret"].mean()
    h2 = df.filter(pl.col("ts") >= mid)["ret"].mean()
    slips = {}
    for slip in (0.05, 0.10):
        r = (df.with_columns(p2=pl.col("price") * (1 + slip))
             .with_columns(ret2=pl.when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("p2") - 1).otherwise(-1.0)))
        slips[slip] = round(r["ret2"].mean(), 3)
    retReal = df["retReal"].mean()
    row = {"set": name, "n": df.height, "events": ev.height,
           "evPos": int((ev["pnl"] > 0).sum()), "winRate": round(df["won"].mean(), 3),
           "ret": round(df["ret"].mean(), 3), "retReal": round(retReal, 3) if retReal is not None else None,
           "boot p5": round(boots[100], 3), "boot p95": round(boots[1899], 3),
           "P(>0)": f"{sum(1 for b in boots if b > 0) / len(boots):.0%}",
           "H1": round(h1, 3), "H2": round(h2, 3),
           "slip5%": slips[0.05], "slip10%": slips[0.10]}
    print(row, flush=True)
    return row


rows = []
mil = entries.filter(pl.col("isMilitary"))
nonmil = entries.filter(~pl.col("isMilitary"))
rows.append(report("mil anyone >=1k <=0.50", mil.filter((pl.col("usd") >= 1000) & (pl.col("price") <= 0.50))))
rows.append(report("mil fresh >=1k <=0.50", mil.filter(fresh & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.50))))
rows.append(report("mil fresh >=5k <=0.50", mil.filter(fresh & (pl.col("usd") >= 5000) & (pl.col("price") <= 0.50))))
rows.append(report("mil fresh >=5k any px", mil.filter(fresh & (pl.col("usd") >= 5000))))
rows.append(report("nonmil fresh >=5k <=0.50", nonmil.filter(fresh & (pl.col("usd") >= 5000) & (pl.col("price") <= 0.50))))

print("\nTop military events by PnL (fresh >=5k):")
df = mil.filter(fresh & (pl.col("usd") >= 5000))
ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), n=pl.len(),
                                   px=pl.col("price").mean(), span=(pl.col("resolvedAt") - pl.col("ts")).dt.total_seconds().mean() / 3600)
      .sort("pnl", descending=True))
print(ev.head(15))
print(f"\ndone {time.time()-t0:.0f}s")
