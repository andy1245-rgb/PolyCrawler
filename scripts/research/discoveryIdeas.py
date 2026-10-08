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
                         .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1).otherwise(-1.0)))
print(f"entries {entries.height} accounts {entries['account'].n_unique()} ({time.time()-t0:.0f}s)", flush=True)


def resolvedPast(cutoff):
    return entries.filter((pl.col("ts") < cutoff) & (pl.col("resolvedAt") < cutoff) & pl.col("winner").is_not_null())


def ideaFreshLongshot(cutoff):
    past = resolvedPast(cutoff)
    nMarkets = past.group_by("account").agg(nMarkets=pl.col("marketId").n_unique())
    wins = past.filter(pl.col("won") & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.3)
                       & ((pl.col("ts") - pl.col("firstTs")) <= pl.duration(days=14)))
    return wins.join(nMarkets, on="account").filter(pl.col("nMarkets") <= 15)["account"].unique()


def ideaRepeatWinner(cutoff):
    longshots = resolvedPast(cutoff).filter((pl.col("price") <= 0.35) & (pl.col("usd") >= 500))
    stats = longshots.group_by("account").agg(
        winEvents=pl.col("eventSlug").filter(pl.col("won")).n_unique(), winRate=pl.col("won").mean())
    return stats.filter((pl.col("winEvents") >= 2) & (pl.col("winRate") >= 0.5))["account"]


def ideaLateInformed(cutoff):
    past = resolvedPast(cutoff)
    late = past.filter(pl.col("won") & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.3)
                       & ((pl.col("resolvedAt") - pl.col("ts")) <= pl.duration(hours=48)))
    return late["account"].unique()


def ideaHighReturn(cutoff):
    bets = resolvedPast(cutoff).filter(pl.col("usd") >= 500)
    stats = bets.group_by("account").agg(n=pl.len(), r=(pl.col("ret") * pl.col("usd")).sum() / pl.col("usd").sum())
    return stats.filter((pl.col("n") >= 3) & (pl.col("r") >= 1.0))["account"]


def ideaConcentrated(cutoff):
    past = resolvedPast(cutoff)
    share = (past.group_by("account", "eventSlug").agg(usd=pl.col("usd").sum())
             .with_columns(share=pl.col("usd") / pl.col("usd").sum().over("account"))
             .group_by("account").agg(topShare=pl.col("share").max()))
    wins = past.filter(pl.col("won") & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.3))["account"].unique()
    return share.filter((pl.col("topShare") >= 0.8) & pl.col("account").is_in(wins.implode()))["account"]


ideas = {"A freshLongshot": ideaFreshLongshot, "B repeatWinner": ideaRepeatWinner,
         "C lateInformed": ideaLateInformed, "D highReturn": ideaHighReturn, "E concentrated": ideaConcentrated}

months = pl.datetime_range(datetime(2024, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc),
                           "1mo", eager=True).to_list()
copies = {name: [] for name in ideas}
baseline = []
for start, end in zip(months[:-1], months[1:]):
    window = entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end) & pl.col("ret").is_not_null())
    baseline.append(window.filter((pl.col("usd") >= 1000) & (pl.col("price") <= 0.3)))
    counts = []
    for name, idea in ideas.items():
        accts = idea(start)
        copies[name].append(window.filter(pl.col("account").is_in(accts.implode())))
        counts.append(f"{name.split()[0]}={accts.len()}")
    print(start.date(), " ".join(counts), f"({time.time()-t0:.0f}s)", flush=True)


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


rows = [summarize("baseline anyone >=1k <=0.30", pl.concat(baseline))]
for name in ideas:
    df = pl.concat(copies[name])
    rows.append(summarize(f"{name} all", df))
    rows.append(summarize(f"{name} <=0.35", df.filter(pl.col("price") <= 0.35)))
with pl.Config(tbl_rows=40, tbl_cols=20, tbl_width_chars=250):
    print(pl.DataFrame(rows))
for name in ideas:
    pl.concat(copies[name]).write_parquet(f"/tmp/pc2scratch/copies_{name.split()[0]}.parquet")
print(f"done {time.time()-t0:.0f}s")
