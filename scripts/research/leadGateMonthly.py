"""When does the lead-gate edge die? Monthly PnL of lead3d big5k copies,
plus flag-pool size per month, to see if the Mar 2026 pool jump changed
the quality of copied bets.

Run:  uv run python scripts/research/leadGateMonthly.py
"""

import time
from datetime import datetime, timezone

import polars as pl

t0 = time.time()
dirs = ["data", "data/universe"]
markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
           .unique("marketId", keep="last")
           .select("marketId", "eventSlug", "winner", pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
iranVenezuela = pl.read_parquet("data/markets.parquet")["eventSlug"].unique().to_list()

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
entries = (entries.join(markets, on="marketId").join(firstSeen, on="account")
           .with_columns(won=pl.col("outcome") == pl.col("winner"),
                         ret=pl.when(pl.col("winner").is_null()).then(None)
                         .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1).otherwise(-1.0),
                         leadHours=(pl.col("resolvedAt") - pl.col("ts")).dt.total_seconds() / 3600))
print(f"entries {entries.height} ({time.time()-t0:.0f}s)", flush=True)


def ruleA(cutoff):
    past = entries.filter((pl.col("ts") < cutoff) & (pl.col("resolvedAt") < cutoff) & pl.col("winner").is_not_null())
    nMarkets = past.group_by("account").agg(nMarkets=pl.col("marketId").n_unique())
    wins = past.filter(pl.col("won") & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.3)
                       & ((pl.col("ts") - pl.col("firstTs")) <= pl.duration(days=14)))
    return wins.join(nMarkets, on="account").filter(pl.col("nMarkets") <= 15)["account"].unique()


months = pl.datetime_range(datetime(2024, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc),
                           "1mo", eager=True).to_list()
rows = []
for start, end in zip(months[:-1], months[1:]):
    accts = ruleA(start)
    w = entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end) & pl.col("ret").is_not_null()
                       & pl.col("account").is_in(accts.implode())
                       & (pl.col("leadHours") <= 72) & (pl.col("usd") >= 5000))
    exIv = w.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    rows.append({"month": start.date(), "flagged": accts.len(), "copies": w.height, "exIVcopies": exIv.height,
                 "ret": round(w["ret"].mean(), 3) if w.height else None,
                 "retExIV": round(exIv["ret"].mean(), 3) if exIv.height else None})
print(pl.DataFrame(rows))

# where do the late-copies land: copied events ex-IV by half, with avg price
copies = []
for start, end in zip(months[:-1], months[1:]):
    accts = ruleA(start)
    copies.append(entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end) & pl.col("ret").is_not_null()
                                 & pl.col("account").is_in(accts.implode())
                                 & (pl.col("leadHours") <= 72) & (pl.col("usd") >= 5000)))
df = pl.concat(copies).filter(~pl.col("eventSlug").is_in(iranVenezuela))
mid = datetime(2025, 6, 1, tzinfo=timezone.utc)
for label, half in (("H1", df.filter(pl.col("ts") < mid)), ("H2", df.filter(pl.col("ts") >= mid))):
    ev = (half.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), n=pl.len(),
                                         px=pl.col("price").mean())
          .sort("pnl", descending=True))
    print(f"\n{label}: {half.height} copies, {ev.height} events, ret={half['ret'].mean():+.3f}, avgPx={half['price'].mean():.3f}")
    print(ev.head(8))
print(f"\ndone {time.time()-t0:.0f}s")
