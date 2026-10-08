import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

labeled = {r["wallet"] for r in csv.DictReader(open("research/knownWallets.csv"))}
sus = pl.read_parquet("data/suspicious.parquet").filter(pl.col("suspicious") & ~pl.col("account").is_in(list(labeled)))
sample = sus.sample(20, seed=7)
markets = pl.read_parquet("data/markets.parquet").select("marketId", "question", "winner", "resolvedAt", "eventSlug")


def loadActivity(wallet):
    path = Path(f"data/raw/activity/{wallet}.json")
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    rows = raw if isinstance(raw, list) else raw.get("rows", raw.get("data", []))
    return rows


def fmtTs(sec):
    return datetime.fromtimestamp(int(sec), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


for i, r in enumerate(sample.iter_rows(named=True), 1):
    acct = r["account"]
    best = markets.filter(pl.col("marketId") == r["bestMarketId"]).row(0, named=True)
    hoursBefore = (best["resolvedAt"] - r["firstBuyTs"]).total_seconds() / 3600 if best["resolvedAt"] else None
    print(f"\n#{i} {acct}  signals={r['signalCount']} ageDays={r['accountAgeDays']:.1f} marketsBeforeSplit={r['marketsTraded']}")
    print(f"  FLAG BET: {best['question'][:70]} | {r['bestOutcome']} @ {r['avgBuyPrice']:.3f} ${r['buyUsd']:,.0f} -> profit ${r['profitUsd']:,.0f}"
          f" | first buy {r['firstBuyTs']:%Y-%m-%d %H:%M} | {hoursBefore:.1f}h before resolve" if hoursBefore is not None else "")
    acts = loadActivity(acct)
    name = next((a.get("name") or a.get("pseudonym") for a in acts if a.get("name") or a.get("pseudonym")), "?")
    trades = [a for a in acts if a.get("type") == "TRADE"]
    redeems = [a for a in acts if a.get("type") == "REDEEM"]
    byMarket = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "title": "", "outcomes": set(), "first": None, "prices": []})
    for a in trades:
        m = byMarket[a.get("conditionId")]
        usd = float(a.get("usdcSize") or 0)
        m["title"] = a.get("title", "")[:60]
        m["outcomes"].add(a.get("outcome"))
        m["first"] = min(m["first"] or a["timestamp"], a["timestamp"])
        if a.get("side") == "BUY":
            m["buy"] += usd
            m["prices"].append(float(a.get("price") or 0))
        else:
            m["sell"] += usd
    redeemed = defaultdict(float)
    for a in redeems:
        redeemed[a.get("conditionId")] += float(a.get("usdcSize") or 0)
    first = min((a["timestamp"] for a in trades), default=None)
    print(f"  name={name} firstTrade={fmtTs(first) if first else '?'} activityRows={len(acts)} marketsInHistory={len(byMarket)}"
          f" totalBuy=${sum(m['buy'] for m in byMarket.values()):,.0f} totalRedeem=${sum(redeemed.values()):,.0f}")
    top = sorted(byMarket.items(), key=lambda kv: -kv[1]["buy"])[:8]
    for cid, m in top:
        avgP = sum(m["prices"]) / len(m["prices"]) if m["prices"] else 0
        print(f"    {fmtTs(m['first'])} buy ${m['buy']:>9,.0f} sell ${m['sell']:>8,.0f} redeem ${redeemed.get(cid, 0):>9,.0f}"
              f" avgP {avgP:.2f} {sorted(o for o in m['outcomes'] if o)} | {m['title']}")
