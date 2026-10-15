"""Dossiers for a 20-account manual-verdict sample from the universe.

Sample: seed=8 from the 89 flagged accounts in data/universe/suspicious.parquet.
For each account: the flag bet, ladder behavior in the flag event, all other
activity (other events, sports/gaming tells), and timing vs resolution.

Run:  uv run python scripts/research/universeDossiers.py > /tmp/dossiers.txt
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]

sus = pl.read_parquet(ROOT / "data/universe/suspicious.parquet").filter(pl.col("suspicious"))
sample = sus.sample(20, seed=8)
markets = pl.read_parquet(ROOT / "data/universe/markets.parquet").select(
    "marketId", "question", "winner", "resolvedAt", "eventSlug"
)


def loadActivity(wallet):
    path = ROOT / f"data/universe/raw/activity/{wallet}.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return raw if isinstance(raw, list) else raw.get("rows", raw.get("data", []))


for i, r in enumerate(sample.iter_rows(named=True), 1):
    acct = r["account"]
    best = markets.filter(pl.col("marketId") == r["bestMarketId"]).row(0, named=True)
    hours = ((best["resolvedAt"] - r["firstBuyTs"]).total_seconds() / 3600
             if best["resolvedAt"] else None)
    print(f"\n=== #{i} {acct} signals={r['signalCount']} age={r['accountAgeDays']:.1f}d mkts={r['marketsTraded']}")
    print(f"  FLAG: {best['eventSlug']} | {best['question'][:70]}")
    print(f"        {r['bestOutcome']} @ {r['avgBuyPrice']:.3f} ${r['buyUsd']:,.0f} -> +${r['profitUsd']:,.0f}"
          + (f" | {hours:.0f}h before resolve" if hours is not None else ""))
    acts = loadActivity(acct)
    trades = [a for a in acts if a.get("type") == "TRADE"]
    byEvent = defaultdict(lambda: {"usd": 0.0, "mkts": set(), "wins": 0, "total": 0,
                                   "first": None, "last": None, "prices": [], "titles": {}})
    for a in trades:
        ev = a.get("eventSlug") or a.get("slug") or "?"
        d = byEvent[ev]
        side = (a.get("side") or "").upper()
        usd = float(a.get("usdcSize") or a.get("size", 0)) * float(a.get("price", 0) or 0)
        if side == "BUY":
            d["usd"] += usd
            d["mkts"].add(a.get("marketSlug") or a.get("asset") or "?")
            d["total"] += 1
            outcome = (a.get("outcome") or "?")
            key = a.get("marketSlug") or "?"
            d["titles"].setdefault(key, f"{(a.get('title') or a.get('slug') or '?')[:40]}|{outcome}")
            d["prices"].append(float(a.get("price", 0) or 0))
            ts = int(a.get("timestamp", 0))
            d["first"] = min(d["first"] or ts, ts)
            d["last"] = max(d["last"] or ts, ts)
    print(f"  activity: {len(trades)} trades, {len(byEvent)} events")
    for ev, d in sorted(byEvent.items(), key=lambda kv: -kv[1]["usd"]):
        mkts = ", ".join(sorted(d["titles"].values())[:4])
        more = f" (+{len(d['titles'])-4} more)" if len(d["titles"]) > 4 else ""
        span = ((d["last"] - d["first"]) / 3600) if d["first"] else 0
        print(f"    {ev[:45]:45s} ${d['usd']:>10,.0f} {len(d['mkts']):>3d}mkt span={span:5.0f}h  {mkts}{more}")
