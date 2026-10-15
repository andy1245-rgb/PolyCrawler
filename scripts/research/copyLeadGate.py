"""Copy-time lead gate: does only copying flagged accounts' bets that resolve
soon make the copy strategy profitable?

Flag rule = A (fresh longshot, same as discoveryIdeas.py). Difference vs the
earlier "A + bet placed <= 72h before resolution" variant: there the gate was
on the flag bet (hindsight, about the past). Here the gate is on the bet we
copy, at the moment we copy it — observable in real time, since the market's
resolution date is known when the bet lands.

Run:  uv run python scripts/research/copyLeadGate.py
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
gates = {"noGate": None, "lead7d": 24 * 7, "lead3d": 24 * 3, "lead24h": 24}
sizeGates = {"any": None, "big1k": 1000, "big5k": 5000}
copies = {(g, s): [] for g in gates for s in sizeGates}
for start, end in zip(months[:-1], months[1:]):
    accts = ruleA(start)
    window = entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end)
                            & pl.col("ret").is_not_null() & pl.col("account").is_in(accts.implode()))
    for g, hours in gates.items():
        gw = window if hours is None else window.filter(pl.col("leadHours") <= hours)
        for s, minUsd in sizeGates.items():
            sw = gw if minUsd is None else gw.filter(pl.col("usd") >= minUsd)
            copies[(g, s)].append(sw)
    print(start.date(), f"flagged={accts.len()}", f"({time.time()-t0:.0f}s)", flush=True)


def summarize(name, df):
    if df.height == 0:
        return {"set": name, "n": 0}
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")).sort("pnl", descending=True))
    exIv = df.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    exTop = (ev["pnl"].sum() - ev["pnl"][0]) / (ev["cap"].sum() - ev["cap"][0]) if ev.height > 1 else None
    return {"set": name, "n": df.height, "events": ev.height, "evPos": int((ev["pnl"] > 0).sum()),
            "winRate": round(df["won"].mean(), 3), "ret": round(df["ret"].mean(), 3),
            "medEvRet": round(ev["r"].median(), 3), "retExTop": None if exTop is None else round(exTop, 3),
            "nExIV": exIv.height, "retExIV": round(exIv["ret"].mean(), 3) if exIv.height else None}


rows = []
for (g, s), chunks in copies.items():
    rows.append(summarize(f"A copy {g} {s}", pl.concat(chunks)))
with pl.Config(tbl_rows=40, tbl_cols=20, tbl_width_chars=250):
    print(pl.DataFrame(rows).sort("n", descending=True))
print(f"done {time.time()-t0:.0f}s")
