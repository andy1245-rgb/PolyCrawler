"""Optimization research on the shipped military fresh-big-bet rule
($5k burst, <=0.35, fresh <=5d, <=3 markets). Four questions:

1. DECAY: entry fill at the next tape price within {30s,60s,300s,900s} —
   how fast does the edge erode with delay?
2. EXITS: hold-to-resolution vs take-profit (+100%, +50% gain on entry
   price) vs stop-loss (-50%), evaluated on the tape's future prices.
3. LIQUIDITY: return by 5-minute post-entry tape volume quartile — is the
   edge only in markets too thin to size?
4. COTRADE: does a second fresh account buying the same (market,outcome)
   within 60s predict higher returns? (cluster confirmation)

Run:  uv run python scripts/research/militaryOptimize.py
"""

import time
from datetime import datetime, timezone

import polars as pl

t0 = time.time()
MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela", "nato")

dirs = ["data", "data/universe"]
markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
           .unique("marketId", keep="last")
           .select("marketId", "eventSlug", "winner", pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
milSlugs = {s for s in markets["eventSlug"].unique().to_list()
            if any(k in (s or "").lower() for k in MILITARY)}
markets = markets.with_columns(isMilitary=pl.col("eventSlug").is_in(list(milSlugs)))

cols = ["ts", "account", "marketId", "outcome", "side", "size", "price"]
lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet").select(cols) for d in dirs])
tape = lazy.filter(pl.col("side") == "BUY").select(
    "ts", "account", "marketId", "outcome", "size", "price").sort("marketId", "outcome", "ts").collect()

# burst entries (10-min window), same construction as the sweep
entries = (tape.sort("account", "marketId", "outcome", "ts")
           .with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome").fill_null(pl.duration(days=1))
                                > pl.duration(minutes=10)).cum_sum().over("account", "marketId", "outcome"))
           .group_by("account", "marketId", "outcome", "burst")
           .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(),
                shares=pl.col("size").sum())
           .with_columns(price=pl.col("usd") / pl.col("shares"))
           .drop("burst", "shares"))
firstSeen = tape.group_by("account").agg(firstTs=pl.col("ts").min())
entries = (entries.join(markets, on="marketId").join(firstSeen, on="account").sort("account", "ts")
           .with_columns(marketsSoFar=pl.col("marketId").is_first_distinct().cast(pl.Int32).cum_sum().over("account"),
                         ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                         won=pl.col("outcome") == pl.col("winner"))
           .filter(pl.col("winner").is_not_null()))

sig = entries.filter(pl.col("isMilitary") & (pl.col("marketsSoFar") <= 3)
                     & (pl.col("usd") >= 5000) & (pl.col("price") <= 0.35)
                     & (pl.col("ageDays") <= 5))
print(f"signals {sig.height} ({time.time()-t0:.0f}s)", flush=True)

# per-(market,outcome) tape for future-price lookups
book = (tape.group_by("marketId", "outcome", "ts").agg(
    px=pl.col("price").last(), vol=pl.col("size").sum())
    .sort("marketId", "outcome", "ts"))

# ---- 1. decay: next tape price within window W
print("\n== 1. entry decay (fill = next tape price within window) ==")
for w in (30, 60, 300, 900, 3600):
    joinable = book.select(
        pl.col("marketId"), pl.col("outcome"), pl.col("ts").alias("bTs"), pl.col("px").alias("bPx"))
    fut = (sig.select("account", "marketId", "outcome", "ts", "price", "won", "winner")
           .join(joinable, on=["marketId", "outcome"], how="left")
           .filter((pl.col("bTs") > pl.col("ts")) & ((pl.col("bTs") - pl.col("ts")).dt.total_seconds() <= w))
           .group_by("account", "marketId", "outcome", "ts", "price", "won")
           .agg(fillPx=pl.col("bPx").min()))
    df = (sig.join(fut, on=["account", "marketId", "outcome", "ts", "price", "won"], how="left")
          .with_columns(fillPx=pl.coalesce("fillPx", "price"))
          .with_columns(ret=pl.when(pl.col("won")).then(1 / pl.col("fillPx") - 1).otherwise(-1.0)))
    print(f"  <= {w:>5}s: n={df.height:>5} ret={df['ret'].mean():+.3f}")

# ---- 2. exits: on the tape, find the best price after entry
print("\n== 2. exit policies ==")
futAll = (sig.select("account", "marketId", "outcome", "ts", "price", "won", "winner")
          .join(book.select(pl.col("marketId"), pl.col("outcome"),
                            pl.col("ts").alias("bTs"), pl.col("px").alias("bPx")),
                on=["marketId", "outcome"], how="left")
          .filter(pl.col("bTs") > pl.col("ts"))
          .group_by("account", "marketId", "outcome", "ts", "price", "won")
          .agg(maxPx=pl.col("bPx").max(), minPx=pl.col("bPx").min()))
ex = (sig.join(futAll, on=["account", "marketId", "outcome", "ts", "price", "won"], how="left")
      .with_columns(pl.col("maxPx").fill_null(pl.col("price")), pl.col("minPx").fill_null(pl.col("price"))))
hold = ex.with_columns(ret=pl.when(pl.col("won")).then(1 / pl.col("price") - 1).otherwise(-1.0))
print(f"  hold-to-resolution: n={ex.height} ret={hold['ret'].mean():+.3f}")
for tp in (2.0, 1.5):
    # take profit sells at entry*tp if the tape ever traded there; else rides to resolution
    r = ex.with_columns(ret=pl.when(pl.col("maxPx") >= pl.col("price") * tp)
                        .then(tp - 1).otherwise(
                            pl.when(pl.col("won")).then(1 / pl.col("price") - 1).otherwise(-1.0)))
    print(f"  take-profit {tp}x: ret={r['ret'].mean():+.3f}")
for sl in (0.5,):
    r = ex.with_columns(ret=pl.when(pl.col("minPx") <= pl.col("price") * sl).then(-0.5).otherwise(
        pl.when(pl.col("won")).then(1 / pl.col("price") - 1).otherwise(-1.0)))
    print(f"  stop-loss {sl}x: ret={r['ret'].mean():+.3f}")

# ---- 3. liquidity: 5-min post-entry tape volume in the same market (both outcomes)
print("\n== 3. liquidity conditioning (post-entry 5-min market volume) ==")
mvol = (tape.group_by("marketId", "ts")
        .agg(vol=pl.col("size").sum())
        .sort("marketId", "ts"))
liq = (sig.select("account", "marketId", "outcome", "ts", "price", "won")
       .join(mvol, on="marketId", how="left")
       .filter((pl.col("ts_right") if "ts_right" in mvol.columns else pl.col("ts_b")) > pl.col("ts")) if False else None)
# simpler: join then filter
liq = (sig.select("account", "marketId", "outcome", "ts", "price", "won")
       .join(mvol.rename({"ts": "bTs"}), on="marketId", how="left")
       .filter((pl.col("bTs") > pl.col("ts")) & ((pl.col("bTs") - pl.col("ts")).dt.total_seconds() <= 300))
       .group_by("account", "marketId", "outcome", "ts", "price", "won")
       .agg(vol5m=pl.col("vol").sum()))
df = (sig.join(liq, on=["account", "marketId", "outcome", "ts", "price", "won"], how="left")
      .with_columns(pl.col("vol5m").fill_null(0.0))
      .with_columns(ret=pl.when(pl.col("won")).then(1 / pl.col("price") - 1).otherwise(-1.0)))
q = df.with_columns(bucket=pl.col("vol5m").cut([10, 100, 1000], labels=["<10", "10-100", "100-1k", ">1k"]))
for b in ("<10", "10-100", "100-1k", ">1k"):
    sub = q.filter(pl.col("bucket") == b)
    if sub.height:
        print(f"  vol {b:>7} shares/5m: n={sub.height:>4} ret={sub['ret'].mean():+.3f}")

# ---- 4. cotrade confirmation: another fresh (<=3d, <=3mkt) account buys same
#         (market,outcome) within 60s after our signal
print("\n== 4. cotrade confirmation ==")
freshAccts = (entries.filter((pl.col("ageDays") <= 3) & (pl.col("marketsSoFar") <= 3))
              .select("account", "marketId", "outcome", "ts").rename({"account": "other", "ts": "oTs"}))
cot = (sig.select("account", "marketId", "outcome", "ts", "price", "won")
       .join(freshAccts, on=["marketId", "outcome"], how="left")
       .filter((pl.col("oTs") > pl.col("ts")) & ((pl.col("oTs") - pl.col("ts")).dt.total_seconds() <= 60)
               & (pl.col("other") != pl.col("account")))
       .group_by("account", "marketId", "outcome", "ts", "price", "won")
       .agg(n=pl.len()))
df = (sig.with_columns(ret=pl.when(pl.col("won")).then(1 / pl.col("price") - 1).otherwise(-1.0))
      .join(cot, on=["account", "marketId", "outcome", "ts", "price", "won"], how="left")
      .with_columns(pl.col("n").fill_null(0)))
for label, sub in (("no cotrade", df.filter(pl.col("n") == 0)), ("cotrade <=60s", df.filter(pl.col("n") > 0))):
    print(f"  {label:14s}: n={sub.height:>4} ret={sub['ret'].mean():+.3f} winRate={sub['won'].mean():.0%}")

print(f"\ndone {time.time()-t0:.0f}s")
