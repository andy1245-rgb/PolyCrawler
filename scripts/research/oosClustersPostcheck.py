"""OOS expansion post-check: cluster look is empty (parents.parquet = 0 rows),
so answer the battery recall + post-split questions at account level.

1. Flag fresh-big-bet accounts on the PRE-split window with the battery rule
   (fresh <=5d by tape, <=3 markets so far, >=$5k one-market burst, avg px <=0.35,
   military tags) and check overlap with the 14 step-1 suspicious accounts and
   with clusters (none exist).
2. Post-split: net exposure per account per market resolved after 2026-01-01
   for the 14 suspicious accounts, resolution PnL from the tape.
"""
from datetime import date

import polars as pl

DD = "data/oosExpansion"
SPLIT = pl.datetime(2026, 1, 1, 0, 0, 0, time_zone="UTC")

fills = pl.read_parquet(f"{DD}/fills.parquet")
mk = pl.read_parquet(f"{DD}/markets.parquet")

milset = [
    "iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
    "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela",
    "nato", "strike",
]


def isMil(tags, slug):
    if tags is not None and any(
        t.lower() in milset or any(k in t.lower() for k in milset) for t in tags
    ):
        return True
    return any(s.lower().find(k) >= 0 for s in [slug] for k in milset)


mstyle = mk.with_columns(
    eventSlug=pl.col("eventSlug").fill_null(""),
).with_columns(
    _mil=pl.struct(pl.col("tags"), pl.col("eventSlug")).map_elements(
        lambda s: isMil(s["tags"], s["eventSlug"]), return_dtype=pl.Boolean
    )
)
milIds = set(mstyle.filter("_mil")["marketId"].to_list())
resolved = mk.drop_nulls("resolvedAt")
pre = resolved.filter(pl.col("resolvedAt") < SPLIT)
post = resolved.filter(pl.col("resolvedAt") >= SPLIT)
preIds, postIds = set(pre["marketId"]), set(post["marketId"])
winner = {r["marketId"]: r["winner"] for r in mk.drop_nulls("winner").to_dicts()}

# --- battery-rule flagging on the pre-split tape
preBets = fills.filter(
    pl.col("side") == "BUY",
    pl.col("marketId").is_in(list(preIds)),
    pl.col("marketId").is_in(list(milIds)),
)
preBets = preBets.with_columns(usd=pl.col("size") * pl.col("price"))
firstAny = preBets.group_by("account").agg(
    firstTs=pl.col("ts").min(), markets=pl.col("marketId").n_unique()
)
burst = (
    preBets.group_by(["account", "marketId", "outcome"])
    .agg(burstUsd=pl.col("usd").sum(), px=pl.col("price").mean())
    .join(preBets.group_by("account").agg(firstTs=pl.col("ts").min()), on="account")
    .join(firstAny.select(["account", "firstTs"]), on="account", suffix="_any")
)
burst = burst.with_columns(ageDays=(pl.col("firstTs_any") - pl.col("firstTs")))
flagRule = burst.filter(
    pl.col("burstUsd") >= 5000,
    pl.col("px") <= 0.35,
    pl.col("ageDays").dt.total_days() <= 5.0,
)
# markets so far at first burst must be <=3 by the tape definition; conservatively
# drop accounts that already traded >3 pre-split markets
mktsFar = firstAny.filter(pl.col("markets") <= 3)
flagRule = flagRule.join(mktsFar.select("account"), on="account")
flagged = set(flagRule["account"].to_list())

sus = pl.read_parquet(f"{DD}/suspicious.parquet").filter(pl.col("suspicious"))
suss = set(sus["account"].to_list())

parents = pl.read_parquet(f"{DD}/parents.parquet")
clusters = pl.read_parquet(f"{DD}/clusterAccounts.parquet")
print("clusters", parents.height, "clusterAccounts", clusters.height)
print("batteryRule flagged (pre-split, military)", len(flagged))
for r in flagRule.sort("burstUsd", descending=True).to_dicts():
    print(
        f"  {r['account']} burst=${r['burstUsd']:.0f} px={r['px']:.3f} "
        f"age={r['ageDays'].total_seconds()/86400:.1f}d "
        f"inStep1={'yes' if r['account'] in suss else 'no'}"
    )
print("overlap flagged ∩ step1 suspicious", len(flagged & suss))
# do flagged fresh-big-bet accounts land in clusters?
ca = set(clusters["account"].to_list())
print("flagged landing in clusters", len(flagged & ca), "(clusters total accounts:", len(ca), ")")

# --- post-split pre-split-flagged accounts keep winning?
print()
print("post-split activity of the 14 step-1 suspicious accounts:")
accts = sorted(suss)
postFills = fills.filter(
    pl.col("ts") >= SPLIT,
    pl.col("account").is_in(accts),
).with_columns(usd=pl.col("size") * pl.col("price"), usdSigned=pl.when(pl.col("side") == "BUY").then(pl.col("size") * pl.col("price")).otherwise(-pl.col("size") * pl.col("price")))
tot = 0
pos = (
    postFills.with_columns(nb=pl.when(pl.col("outcome") == "Yes").then(
        pl.when(pl.col("side") == "BUY").then(pl.col("size")).otherwise(-pl.col("size"))
    ).otherwise(0), nn=pl.when(pl.col("outcome") == "No").then(
        pl.when(pl.col("side") == "BUY").then(pl.col("size")).otherwise(-pl.col("size"))
    ).otherwise(0))
    .group_by(["account", "marketId"])
    .agg(netYes=pl.col("nb").sum(), netNo=pl.col("nn").sum(), cash=pl.col("usdSigned").sum())
    .join(mk.select(["marketId", "winner", "question"]), on="marketId")
)
resolvedIds = set(mk.drop_nulls("winner")["marketId"])
posR = pos.filter(pl.col("marketId").is_in(list(resolvedIds))).with_columns(
    pnl=pl.when(pl.col("winner") == "Yes").then(pl.col("netYes")).otherwise(
        pl.when(pl.col("winner") == "No").then(pl.col("netNo")).otherwise(0.0)
    ) - pl.col("cash")
)
for r in posR.sort("pnl", descending=True).to_dicts():
    tot += r["pnl"]
    print(
        f"  {r['account'][:10]}… netYes={r['netYes']:.0f} netNo={r['netNo']:.0f} "
        f"cash={r['cash']:.0f} winner={r['winner']} pnl={r['pnl']:.0f} "
        f"{(r['question'] or '')[:45]}"
    )
print("post-split PnL of suspicious accounts (remaining-at-resolution):", round(tot))
