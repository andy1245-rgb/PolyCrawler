import time
from datetime import datetime, timezone

import polars as pl

t0 = time.time()
dirs = ["data", "data/universe"]
markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
           .unique("marketId", keep="last")
           .select("marketId", "eventSlug", "tags", "winner", pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
iranVenezuela = pl.read_parquet("data/markets.parquet")["eventSlug"].unique().to_list()

# generic tags = on more than 25% of events
eventTags = markets.select("eventSlug", "tags").unique("eventSlug").explode("tags")
tagShare = eventTags.group_by("tags").agg(n=pl.col("eventSlug").n_unique()).with_columns(share=pl.col("n") / markets["eventSlug"].n_unique())
generic = tagShare.filter(pl.col("share") > 0.25)["tags"].to_list()
print("generic tags:", generic)
markets = markets.with_columns(topic=pl.col("tags").list.set_difference(pl.lit(generic)))

cols = ["ts", "account", "marketId", "outcome", "side", "size", "price"]
lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet").select(cols) for d in dirs])
entries = (lazy.filter(pl.col("side") == "BUY").drop("side")
           .sort("account", "marketId", "outcome", "ts")
           .with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome").fill_null(pl.duration(days=1))
                                > pl.duration(minutes=10)).cum_sum().over("account", "marketId", "outcome"))
           .group_by("account", "marketId", "outcome", "burst")
           .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(), shares=pl.col("size").sum())
           .with_columns(price=pl.col("usd") / pl.col("shares"))
           .drop("burst", "shares")
           .collect())
firstSeen = lazy.group_by("account").agg(firstTs=pl.col("ts").min()).collect()
entries = (entries.join(markets, on="marketId").join(firstSeen, on="account").sort("account", "ts")
           # point-in-time: distinct markets the account touched up to and including this entry
           .with_columns(marketsSoFar=pl.col("marketId").is_first_distinct().cast(pl.Int32).cum_sum().over("account"),
                         ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                         won=pl.col("outcome") == pl.col("winner"),
                         ret=pl.when(pl.col("winner").is_null()).then(None)
                         .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1).otherwise(-1.0))
           .filter(pl.col("ret").is_not_null()))
print(f"entries {entries.height} ({time.time()-t0:.0f}s)", flush=True)


def summarize(name, df):
    if df.height == 0:
        return {"set": name, "n": 0}
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")).sort("pnl", descending=True))
    exIv = df.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    exTop = (ev["pnl"].sum() - ev["pnl"][0]) / (ev["cap"].sum() - ev["cap"][0]) if ev.height > 1 else None
    exIvEv = ev.filter(~pl.col("eventSlug").is_in(iranVenezuela))
    return {"set": name, "n": df.height, "events": ev.height, "evPos": int((ev["pnl"] > 0).sum()),
            "winRate": round(df["won"].mean(), 3), "ret": round(df["ret"].mean(), 3),
            "medEvRet": round(ev["r"].median(), 3), "retExTop": None if exTop is None else round(exTop, 3),
            "nExIV": exIv.height, "retExIV": round(exIv["ret"].mean(), 3) if exIv.height else None,
            "evPosExIV": f"{int((exIvEv['pnl'] > 0).sum())}/{exIvEv.height}"}


rows = []
big = entries.filter(pl.col("usd") >= 1000)
rows.append(summarize("anyone >=1k <=0.30", big.filter(pl.col("price") <= 0.3)))
rows.append(summarize("anyone >=1k <=0.50", big.filter(pl.col("price") <= 0.5)))
rows.append(summarize("anyone >=1k any price", big))
for maxAge, maxMarkets in [(1, 1), (1, 3), (3, 3), (7, 5)]:
    fresh = big.filter((pl.col("ageDays") <= maxAge) & (pl.col("marketsSoFar") <= maxMarkets))
    for maxPrice in [0.3, 0.5, 1.01]:
        rows.append(summarize(f"fresh age<={maxAge}d mkts<={maxMarkets} <={maxPrice}", fresh.filter(pl.col("price") <= maxPrice)))
for minUsd in [5000, 20000]:
    fresh = entries.filter((pl.col("usd") >= minUsd) & (pl.col("ageDays") <= 3) & (pl.col("marketsSoFar") <= 3))
    rows.append(summarize(f"fresh age<=3d mkts<=3 >={minUsd} <=0.5", fresh.filter(pl.col("price") <= 0.5)))
    rows.append(summarize(f"fresh age<=3d mkts<=3 >={minUsd} any", fresh))

# same-topic copy: flagged (rule A, point-in-time monthly) accounts' later buys only in markets sharing a topic tag with the flag bet
months = pl.datetime_range(datetime(2024, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc), "1mo", eager=True).to_list()
same, other = [], []
for start, end in zip(months[:-1], months[1:]):
    past = entries.filter((pl.col("ts") < start) & (pl.col("resolvedAt") < start))
    nMarkets = past.group_by("account").agg(nMarkets=pl.col("marketId").n_unique())
    wins = (past.filter(pl.col("won") & (pl.col("usd") >= 1000) & (pl.col("price") <= 0.3) & (pl.col("ageDays") <= 14))
            .join(nMarkets, on="account").filter(pl.col("nMarkets") <= 15))
    flagTopics = wins.group_by("account").agg(flagTopic=pl.col("topic").list.explode(keep_nulls=False, empty_as_null=False).unique(), flagEvents=pl.col("eventSlug").unique())
    window = entries.filter((pl.col("ts") >= start) & (pl.col("ts") < end)).join(flagTopics, on="account")
    window = window.with_columns(sameTopic=(pl.col("topic").list.set_intersection("flagTopic").list.len() > 0)
                                 | pl.col("flagEvents").list.contains(pl.col("eventSlug")))
    same.append(window.filter("sameTopic").drop("flagTopic", "flagEvents", "sameTopic"))
    other.append(window.filter(~pl.col("sameTopic")).drop("flagTopic", "flagEvents", "sameTopic"))
same, other = pl.concat(same), pl.concat(other)
rows.append(summarize("flagged A: same-topic buys", same))
rows.append(summarize("flagged A: same-topic <=0.5", same.filter(pl.col("price") <= 0.5)))
rows.append(summarize("flagged A: other-topic buys", other))

with pl.Config(tbl_rows=60, tbl_cols=20, tbl_width_chars=260, fmt_str_lengths=40):
    print(pl.DataFrame(rows))
    fresh = big.filter((pl.col("ageDays") <= 1) & (pl.col("marketsSoFar") <= 1) & (pl.col("price") <= 0.5))
    print(fresh.filter(~pl.col("eventSlug").is_in(iranVenezuela)).group_by("eventSlug")
          .agg(n=pl.len(), pnl=(pl.col("ret") * 100).sum().round(0), winRate=pl.col("won").mean().round(2))
          .sort("pnl", descending=True).head(15))
print(f"done {time.time()-t0:.0f}s")
