import polars as pl
split = pl.datetime(2026, 3, 1, time_zone="UTC")
sus = pl.read_parquet("data/suspicious.parquet").filter("suspicious").select("account", "signalCount", "profitUsd")
m = pl.read_parquet("data/markets.parquet").select("marketId", "eventSlug", "question", "winner", "resolvedAt")
f = (pl.scan_parquet("data/fills.parquet")
     .filter(pl.col("account").is_in(sus["account"].implode()) & (pl.col("side") == "BUY") & (pl.col("ts") >= split))
     .collect().sort("ts"))
# one entry per account/market/outcome per 10-minute burst
f = f.with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome").fill_null(pl.duration(days=1)) > pl.duration(minutes=10)).cum_sum().over("account", "marketId", "outcome"))
e = (f.group_by("account", "marketId", "outcome", "burst")
     .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(), shares=pl.col("size").sum())
     .with_columns(price=pl.col("usd") / pl.col("shares"))
     .join(m, on="marketId").filter(pl.col("winner").is_not_null())
     .join(sus, on="account")
     .with_columns(ret=pl.when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1).otherwise(-1.0)))
# consensus: distinct flagged accounts buying the same market+outcome in the prior 24h (incl. self)
e = e.sort("ts")
cons = []
rows = e.select("marketId", "outcome", "ts", "account").to_dicts()
for r in rows:
    cons.append(len({x["account"] for x in rows if x["marketId"] == r["marketId"] and x["outcome"] == r["outcome"] and 0 <= (r["ts"] - x["ts"]).total_seconds() <= 86400}))
e = e.with_columns(consensus=pl.Series(cons))
def report(name, df):
    if df.height == 0:
        print(f"{name:38s} n=0"); return
    ev = df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum()).sort("pnl", descending=True)
    top = ev["pnl"][0]; tot = ev["pnl"].sum()
    print(f"{name:38s} n={df.height:4d} events={ev.height:2d} winRate={df['ret'].gt(0).mean():.0%} "
          f"pnl$100={tot:9.0f} ret={tot/(100*df.height):6.1%} exTopEvent={tot-top:8.0f}")
report("all", e)
for lo, hi in [(0, .1), (.1, .2), (.2, .35), (.35, .5), (.5, .7), (.7, 1.01)]:
    report(f"price {lo}-{hi}", e.filter((pl.col("price") >= lo) & (pl.col("price") < hi)))
for lo in [100, 1000, 5000, 20000]:
    report(f"insider usd >= {lo}", e.filter(pl.col("usd") >= lo))
for c in [1, 2, 3, 5]:
    report(f"consensus >= {c}", e.filter(pl.col("consensus") >= c))
report("price<=0.35 & usd>=1000", e.filter((pl.col("price") <= .35) & (pl.col("usd") >= 1000)))
report("price<=0.35 & consensus>=2", e.filter((pl.col("price") <= .35) & (pl.col("consensus") >= 2)))
report("price<=0.5 & consensus>=3", e.filter((pl.col("price") <= .5) & (pl.col("consensus") >= 3)))
# largest bet so far per account+event (point in time)
e2 = e.sort("ts").with_columns(runMax=pl.col("usd").cum_max().over("account", "eventSlug"))
report("largest-so-far per account/event", e2.filter(pl.col("usd") >= pl.col("runMax")))
print(e.group_by("eventSlug").agg(pl.len(), (pl.col("ret") * 100).sum().alias("pnl$100")).sort("pnl$100"))
