"""Dune order_hash burst rebuild: test whether the >= $5k threshold should be
defined at the signed-order level instead of the 10-minute fill-burst level
(research/ideasResearch.md #2).

Why: Dune's polymarket_polygon.market_trades carries order_hash, the EIP-712
hash of each signed order, so one order's partial fills can be reassembled
across time. The shipped rule (burst = sum of BUY fills inside a 10-minute
window >= $5k) can miss an $8k order executed as sub-$5k chunks spread over
half an hour, and can fire on a "$5k burst" assembled from unrelated $1k
orders. This script rebuilds the shipped military cell
(research/militaryCategory.py: fresh >= $5k <= 0.50) both ways on the SAME
Dune BUY-fills data and reports the deltas plus overlap counts.

Data pull (needs DUNE_API_KEY in the environment; results cached under
data/raw/dune/ so reruns are offline):
  POST /api/v1/sql/execute -> poll /api/v1/execution/{id}/status
  -> GET /api/v1/execution/{id}/results/csv (follow x-dune-next-uri)
BUY fill per wallet = maker_side = 'BUY' with wallet = the maker column
(the taker leg's maker column holds the aggressor; the maker leg's holds the
resting wallet — per the Dune schema both legs read side off maker_side).

Run:  uv run python scripts/research/duneOrderBurst.py [--refresh]
"""

import importlib.util
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[2]

# shared research-data plumbing (dirs, military slugs, markets frame)
_researchDataSpec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_researchDataSpec)
sys.modules["researchData"] = researchData
_researchDataSpec.loader.exec_module(researchData)

t0 = time.time()
DUNE_DIR = ROOT / "data" / "raw" / "dune"
DUNE_API = "https://api.dune.com/api/v1"
COND_BATCH = 300           # condition ids per SQL execution
POLL_SECS = 5
POLL_TIMEOUT = 600

RULE_MIN_USD = 5000
BURST_WINDOW_SEC = 600
FILL_WINDOW_SEC = 300


def buildSql(conditionIds: list[str]) -> str:
    ids = ",\n    ".join(f"X'{m[2:]}'" for m in conditionIds)
    return f"""
SELECT
  lower(encode(condition_id, 'hex')) AS condition_id,
  lower(encode(order_hash, 'hex')) AS order_hash,
  lower(encode(asset_id, 'hex')) AS asset_id,
  lower(encode(maker, 'hex')) AS account,
  block_time,
  price,
  shares,
  amount
FROM polymarket_polygon.market_trades
WHERE block_time >= TIMESTAMP '2023-10-01'
  AND maker_side = 'BUY'
  AND condition_id IN (
    {ids}
  )
"""


def duneExecute(client: httpx.Client, key: str, sql: str) -> str:
    r = client.post(f"{DUNE_API}/sql/execute", json={"sql": sql, "performance": "medium"},
                    headers={"x-dune-api-key": key})
    r.raise_for_status()
    body = r.json()
    if "execution_id" not in body:
        raise RuntimeError(f"dune execute failed: {str(body)[:200]}")
    return body["execution_id"]


def duneWait(client: httpx.Client, key: str, executionId: str) -> None:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = client.get(f"{DUNE_API}/execution/{executionId}/status",
                       headers={"x-dune-api-key": key})
        r.raise_for_status()
        state = r.json().get("state")
        if state == "COMPLETED":
            return
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"dune execution {executionId}: {state}")
        time.sleep(POLL_SECS)
    raise TimeoutError(f"dune execution {executionId} not done in {POLL_TIMEOUT}s")


def duneCsv(client: httpx.Client, key: str, executionId: str) -> str:
    url = f"{DUNE_API}/execution/{executionId}/results/csv"
    lines = []
    page = 0
    while url:
        r = client.get(url, headers={"x-dune-api-key": key})
        r.raise_for_status()
        pageLines = r.text.rstrip("\n").split("\n")
        if page > 0:
            pageLines = pageLines[1:]  # repeated header row
        lines.extend(pageLines)
        url = r.headers.get("x-dune-next-uri")
        page += 1
    return "\n".join(lines)


def pullDune(client: httpx.Client, key: str, conditionIds: list[str]) -> pl.DataFrame:
    DUNE_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    batches = [conditionIds[i:i + COND_BATCH] for i in range(0, len(conditionIds), COND_BATCH)]
    for n, batch in enumerate(batches):
        cache = DUNE_DIR / f"militaryBuys_{n:03d}.csv"
        if cache.exists():
            print(f"batch {n + 1}/{len(batches)}: cached {cache.name}")
        else:
            sql = buildSql(batch)
            execId = duneExecute(client, key, sql)
            print(f"batch {n + 1}/{len(batches)}: execution {execId}, polling...", flush=True)
            duneWait(client, key, execId)
            cache.write_text(duneCsv(client, key, execId))
        frames.append(pl.read_csv(cache, infer_schema_length=0).with_columns(
            pl.col("price").cast(pl.Float64), pl.col("shares").cast(pl.Float64),
            pl.col("amount").cast(pl.Float64),
            pl.col("block_time").str.to_datetime(time_zone="UTC")))
    return pl.concat(frames, how="vertical")


def burstEntries(fills: pl.DataFrame) -> pl.DataFrame:
    """Shipped definition: BUY fills grouped into bursts by a >10-minute gap
    (per account/market/outcome)."""
    return (fills.sort("account", "marketId", "outcome", "ts")
            .with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome")
                                 .fill_null(pl.duration(days=1)) > pl.duration(seconds=BURST_WINDOW_SEC))
                          .cum_sum().over("account", "marketId", "outcome"))
            .group_by("account", "marketId", "outcome", "burst")
            .agg(ts=pl.col("ts").min(), usd=pl.col("usd").sum(), shares=pl.col("shares").sum())
            .with_columns(price=pl.col("usd") / pl.col("shares"))
            .drop("burst", "shares"))


def orderEntries(fills: pl.DataFrame) -> pl.DataFrame:
    """Order-level definition: one entry per signed order (order_hash), its
    partial fills reassembled across any time span."""
    return (fills.group_by("account", "marketId", "outcome", "orderHash")
            .agg(ts=pl.col("ts").min(), usd=pl.col("usd").sum(), shares=pl.col("shares").sum())
            .with_columns(price=pl.col("usd") / pl.col("shares"))
            .drop("shares"))


def annotate(entries: pl.DataFrame, markets: pl.DataFrame, firstSeen: pl.DataFrame) -> pl.DataFrame:
    return (entries.join(markets, on="marketId").join(firstSeen, on="account").sort("account", "ts")
            .with_columns(marketsSoFar=pl.col("marketId").is_first_distinct().cast(pl.Int32).cum_sum().over("account"),
                          ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                          won=pl.col("outcome") == pl.col("winner"),
                          ret=pl.when(pl.col("winner").is_null()).then(None)
                          .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1).otherwise(-1.0))
            .filter(pl.col("ret").is_not_null()))


def report(name: str, df: pl.DataFrame, rng: random.Random) -> dict:
    if df.height == 0:
        row = {"set": name, "n": 0}
        print(row, flush=True)
        return row
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col("ret") * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")))
    events = list(ev.iter_rows(named=True))
    boots = []
    for _ in range(2000):
        samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
        boots.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
    boots.sort()
    mid = datetime(2025, 6, 1, tzinfo=timezone.utc)
    h1 = df.filter(pl.col("ts") < mid)["ret"].mean()
    h2 = df.filter(pl.col("ts") >= mid)["ret"].mean()
    retReal = df["retReal"].mean()
    row = {"set": name, "n": df.height, "events": ev.height,
           "evPos": int((ev["pnl"] > 0).sum()), "winRate": round(df["won"].mean(), 3),
           "ret": round(df["ret"].mean(), 3),
           "retReal": round(retReal, 3) if retReal is not None else None,
           "boot p5": round(boots[100], 3), "boot p95": round(boots[1899], 3),
           "P(>0)": f"{sum(1 for b in boots if b > 0) / len(boots):.0%}",
           "H1": round(h1, 3) if h1 is not None else None,
           "H2": round(h2, 3) if h2 is not None else None}
    print(row, flush=True)
    return row


def main() -> None:
    import argparse
    args = argparse.ArgumentParser()
    args.add_argument("--data-dir", action="append", default=None)
    args = args.parse_args()
    dirs = researchData.researchDataDirs(requested=args.data_dir)
    key = ""
    import os
    if os.environ.get("DUNE_API_KEY"):
        key = os.environ["DUNE_API_KEY"]
    cached = list(DUNE_DIR.glob("militaryBuys_*.csv")) if DUNE_DIR.exists() else []
    if not key and not cached:
        sys.exit("DUNE_API_KEY not set and no cached batches under data/raw/dune/; "
                 "export DUNE_API_KEY and rerun")

    markets = researchData.militaryMarketsFrame(dirs)
    conditionIds = sorted(markets["marketId"].to_list())
    print(f"military markets: {len(conditionIds)} across {markets['eventSlug'].n_unique()} events")

    if cached and not os.environ.get("DUNE_REFRESH"):
        fillsRaw = pl.concat(
            [pl.read_csv(p, infer_schema_length=0).with_columns(
                pl.col("price").cast(pl.Float64), pl.col("shares").cast(pl.Float64),
                pl.col("amount").cast(pl.Float64),
                pl.col("block_time").str.to_datetime(time_zone="UTC")) for p in sorted(cached)],
            how="vertical")
        print(f"loaded {fillsRaw.height} cached Dune rows from {len(cached)} batch(es)")
    else:
        with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
            fillsRaw = pullDune(client, key, conditionIds)
        print(f"pulled {fillsRaw.height} Dune rows ({time.time() - t0:.0f}s)")

    # map asset_id (0x hex) -> outcome label via Gamma clobTokenIds on markets.parquet
    tokmap: dict[str, str] = {}
    allMarkets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet")
                             for d in dirs], how="diagonal_relaxed")
                  .unique("marketId", keep="last"))
    for m in allMarkets.iter_rows(named=True):
        try:
            ids = json.loads(m.get("clobTokenIds") or "[]")
            outs = json.loads(m.get("outcomes") or "[]")
        except (ValueError, TypeError):
            continue
        for o, t in zip(outs, ids):
            tid = str(t).lower()
            if tid.isdigit():  # decimal clob token id -> 0x hex
                tid = "0x" + format(int(tid), "x")
            tokmap.setdefault(tid, str(o))
    fills = (fillsRaw.select(
        ts=pl.col("block_time"),
        account=pl.col("account"),
        marketId="0x" + pl.col("condition_id"),
        outcome=pl.col("asset_id").map_elements(
            lambda a: tokmap.get("0x" + a if not a.startswith("0x") else a, "?"),
            return_dtype=pl.String),
        shares=pl.col("shares"),
        price=pl.col("price"),
        usd=pl.col("amount"),
        orderHash=pl.col("order_hash")))
    unmatched = fills.filter(pl.col("outcome") == "?").height
    print(f"fills: {fills.height} BUY rows, {unmatched} with unmapped outcome")
    fills = fills.filter(pl.col("outcome") != "?")
    fills = fills.filter(pl.col("marketId").is_in(conditionIds))

    # realistic fill: next BUY price in the same (market, outcome) within 5 min
    tape = (fills.sort("marketId", "outcome", "ts")
            .with_columns(nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"),
                          nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"))
            .with_columns(fillPrice=pl.when(
                (pl.col("nextTs") - pl.col("ts")).dt.total_seconds() <= FILL_WINDOW_SEC)
                .then(pl.col("nextPrice")).otherwise(pl.col("price")))
            .unique(subset=["ts", "marketId", "outcome"], keep="last"))
    firstSeen = fills.group_by("account").agg(firstTs=pl.col("ts").min())

    base = annotate(burstEntries(fills), markets, firstSeen)
    orders = annotate(orderEntries(fills), markets, firstSeen)
    base = (base.drop("price")
            .join(tape.select("ts", "marketId", "outcome", "price", "fillPrice"),
                  on=["ts", "marketId", "outcome"], how="left")
            .with_columns(retReal=pl.when(pl.col("winner").is_null()).then(None)
                          .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("fillPrice") - 1)
                          .otherwise(-1.0)))
    orders = (orders.drop("price")
              .join(tape.select("ts", "marketId", "outcome", "price", "fillPrice"),
                    on=["ts", "marketId", "outcome"], how="left")
              .with_columns(retReal=pl.when(pl.col("winner").is_null()).then(None)
                            .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("fillPrice") - 1)
                            .otherwise(-1.0)))
    print(f"entries: burst-level {base.height}, order-level {orders.height} ({time.time() - t0:.0f}s)")

    flt = lambda df: df.filter((pl.col("usd") >= RULE_MIN_USD) & (pl.col("price") <= 0.50))
    rng = random.Random(7)
    print("\n-- shipped cell, both definitions --")
    rows = []
    rows.append(report("burst >=5k <=0.50 (shipped def)", flt(base), rng))
    rows.append(report("order >=5k <=0.50 (order_hash def)", flt(orders), rng))
    rows.append(report("burst >=1k <=0.50 (lower thr ref)", base.filter(
        (pl.col("usd") >= 1000) & (pl.col("price") <= 0.50)), rng))
    rows.append(report("order >=1k <=0.50 (lower thr ref)", orders.filter(
        (pl.col("usd") >= 1000) & (pl.col("price") <= 0.50)), rng))

    # overlap analysis: what each definition sees that the other misses
    print("\n-- definition overlap --")
    fresh = (pl.col("ageDays") <= 3) & (pl.col("marketsSoFar") <= 3)
    bKeys = set(map(tuple, flt(base.filter(fresh)).select("account", "marketId", "outcome").iter_rows()))
    oKeys = set(map(tuple, flt(orders.filter(fresh)).select("account", "marketId", "outcome").iter_rows()))
    print(f"fresh >=5k <=0.50: burst-level {len(bKeys)} (account,market,outcome) picks, "
          f"order-level {len(oKeys)}, shared {len(bKeys & oKeys)}, "
          f"order-only {len(oKeys - bKeys)}, burst-only {len(bKeys - oKeys)}")
    # how many order-level entries were invisible to any 10-minute burst:
    # their fills span more than one burst window.
    windows = (fills.sort("ts")
               .with_columns(newWindow=(pl.col("ts").diff()
                                        .over(["account", "marketId", "outcome", "orderHash"])
                                        .dt.total_seconds() > BURST_WINDOW_SEC)
                             .fill_null(True))
               .group_by(["account", "marketId", "outcome", "orderHash"])
               .agg(nWindows=pl.col("newWindow").sum())
               .join(orders.filter(pl.col("usd") >= RULE_MIN_USD)
                     .select("account", "marketId", "outcome", "orderHash"),
                     on=["account", "marketId", "outcome", "orderHash"], how="semi"))
    print(f"orders >=$5k whose fills span more than one 10-minute window (invisible to bursts): "
          f"{windows.filter(pl.col('nWindows') > 1).height} of {windows.height}")
    print(f"\ndone {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
