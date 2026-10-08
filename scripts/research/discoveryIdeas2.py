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
# second-resolution buy keys for co-trade detection
buySeconds = (lazy.filter(pl.col("side") == "BUY").select("ts", "account", "marketId", "outcome").unique().collect())
print(f"entries {entries.height} ({time.time()-t0:.0f}s)", flush=True)


def flagBets(cutoff):
    """Rule A flag bets with review features, point-in-time."""
    past = entries.filter((pl.col("ts") < cutoff) & (pl.col("resolvedAt") < cutoff) & pl.col("winner").is_not_null())
    nMarkets = past.group_by("account").agg(nMarkets=pl.col("marketId").n_unique())
    wins = (past.filter(pl.col("won") & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.3)
                        & ((pl.col("ts") - pl.col("firstTs")) <= pl.duration(days=14)))
            .join(nMarkets, on="account").filter(pl.col("nMarkets") <= 15))
    eventUsd = past.group_by("account", "eventSlug").agg(eventUsd=pl.col("usd").sum(),
                                                         losingBets=(~pl.col("won")).sum())
    winUsd = past.filter(pl.col("won")).group_by("account", "marketId").agg(winUsd=pl.col("usd").sum())
    return (wins.join(eventUsd, on=["account", "eventSlug"]).join(winUsd, on=["account", "marketId"])
            .with_columns(precision=pl.col("winUsd") / pl.col("eventUsd"),
                          leadHours=(pl.col("resolvedAt") - pl.col("ts")).dt.total_seconds() / 3600)
            .group_by("account").agg(pl.col("precision").max(), pl.col("losingBets").min(), pl.col("leadHours").min()))


def coTraders(cutoff, accounts, minShared=2):
    sec = buySeconds.filter((pl.col("ts") < cutoff) & pl.col("account").is_in(accounts.implode()))
    pairs = sec.join(sec, on=["ts", "marketId", "outcome"]).filter(pl.col("account") < pl.col("account_right"))
    counts = pairs.group_by("account", "account_right").agg(n=pl.len()).filter(pl.col("n") >= minShared)
    return pl.concat([counts["account"], counts["account_right"]]).unique()


variants = {
    "A base": lambda f, c: f["account"],
    "A + precision>=0.5": lambda f, c: f.filter(pl.col("precision") >= 0.5)["account"],
    "A + no losing ladder bets": lambda f, c: f.filter(pl.col("losingBets") == 0)["account"],
    "A + lead<=72h": lambda f, c: f.filter(pl.col("leadHours") <= 72)["account"],
    "A + precision & lead": lambda f, c: f.filter((pl.col("precision") >= 0.5) & (pl.col("leadHours") <= 72))["account"],
    "A + co-trader": lambda f, c: coTraders(c, f["account"]),
}
months = pl.datetime_range(datetime(2024, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc),
                           "1mo", eager=True).to_list()
copies = {name: [] for name in variants}
for start, end in zip(months[:-1], months[1:]):
    window = entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end) & pl.col("ret").is_not_null())
    feats = flagBets(start)
    counts = []
    for name, pick in variants.items():
        accts = pick(feats, start)
        copies[name].append(window.filter(pl.col("account").is_in(accts.implode())))
        counts.append(str(accts.len()))
    print(start.date(), " ".join(counts), f"({time.time()-t0:.0f}s)", flush=True)


def summarize(name, df):
    if df.height == 0:
        return {"set": name, "n": 0}
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")).sort("pnl", descending=True))
    exIv = df.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    exTop = (ev["pnl"].sum() - ev["pnl"][0]) / (ev["cap"].sum() - ev["cap"][0]) if ev.height > 1 else None
    return {"set": name, "n": df.height, "accts": df["account"].n_unique(), "events": ev.height,
            "evPos": int((ev["pnl"] > 0).sum()), "winRate": round(df["won"].mean(), 3), "ret": round(df["ret"].mean(), 3),
            "medEvRet": round(ev["r"].median(), 3), "retExTop": None if exTop is None else round(exTop, 3),
            "nExIV": exIv.height, "retExIV": round(exIv["ret"].mean(), 3) if exIv.height else None}


rows = []
for name in variants:
    df = pl.concat(copies[name])
    rows.append(summarize(name, df))
    rows.append(summarize(f"{name} | <=0.5", df.filter(pl.col("price") <= 0.5)))
with pl.Config(tbl_rows=40, tbl_cols=20, tbl_width_chars=250, fmt_str_lengths=40):
    print(pl.DataFrame(rows))
print(f"done {time.time()-t0:.0f}s")
