"""Robustness checks for the copy-time lead gate result (copyLeadGate.py).

Variants tested: lead{3d,7d} x big{1k,5k}. Checks per variant:
  1. Return by time half (Oct 2024 - Jun 2025 vs Jun 2025 - Oct 2026)
  2. Event-level bootstrap: 2000 resamples of whole events, 5th/50th/95th pct
  3. Slippage: copy price paid = insider price x (1 + slip) for slip in 5/10/20%
  4. Profit concentration: top-3 events' share of total PnL ex-Iran/Venezuela

Run:  uv run python scripts/research/leadGateRobustness.py
"""

import random
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
variants = {("3d", 1000): 24 * 3, ("3d", 5000): 24 * 3, ("7d", 1000): 24 * 7, ("7d", 5000): 24 * 7}
chunks = {k: [] for k in variants}
for start, end in zip(months[:-1], months[1:]):
    accts = ruleA(start)
    window = entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end)
                            & pl.col("ret").is_not_null() & pl.col("account").is_in(accts.implode()))
    for (name, minUsd), hours in variants.items():
        chunks[(name, minUsd)].append(window.filter((pl.col("leadHours") <= hours) & (pl.col("usd") >= minUsd)))
copies = {k: pl.concat(v) for k, v in chunks.items()}
print(f"copies built ({time.time()-t0:.0f}s)", flush=True)

mid = datetime(2025, 6, 1, tzinfo=timezone.utc)
rng = random.Random(7)

for (name, minUsd), df in copies.items():
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")))
    exIv = df.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    evExIv = ev.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    n = exIv.height
    # event-level bootstrap on ex-IV mean return
    boots = []
    events = list(evExIv.iter_rows(named=True))
    for _ in range(2000):
        samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
        boots.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
    boots.sort()
    # slippage on the copy price
    slips = {}
    for slip in (0.05, 0.10, 0.20):
        r = df.with_columns(p2=pl.col("price") * (1 + slip))
        r = r.with_columns(ret2=pl.when(pl.col("winner").is_null()).then(None)
                           .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("p2") - 1).otherwise(-1.0))
        slips[slip] = round(r.filter(~pl.col("eventSlug").is_in(iranVenezuela))["ret2"].mean(), 3)
    # profit concentration ex-IV
    tot = evExIv["pnl"].sum()
    top3 = evExIv.sort("pnl", descending=True)["pnl"][:3].sum() if evExIv.height else 0
    h1 = exIv.filter(pl.col("ts") < mid)
    h2 = exIv.filter(pl.col("ts") >= mid)
    print(f"\n=== lead{name} big{minUsd}: n={df.height} exIV n={n} ===")
    print(f"  exIV ret all={round(exIv['ret'].mean(),3)}  H1(Oct24-Jun25)={round(h1['ret'].mean(),3) if h1.height else None}"
          f"  H2(Jun25-Oct26)={round(h2['ret'].mean(),3) if h2.height else None}")
    print(f"  exIV bootstrap mean ret: p5={boots[100]:+.3f} p50={boots[1000]:+.3f} p95={boots[1899]:+.3f}"
          f"  P(>0)={sum(1 for b in boots if b > 0)/len(boots):.0%}")
    print(f"  slippage exIV ret: +5%={slips[0.05]} +10%={slips[0.10]} +20%={slips[0.20]}")
    print(f"  top-3 events share of exIV PnL: {top3/tot:.0%} of ${tot:,.0f}")

print(f"\ndone {time.time()-t0:.0f}s")
