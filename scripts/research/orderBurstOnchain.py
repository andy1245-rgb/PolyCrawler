"""On-chain order_hash burst rebuild — replaces the Dune pull (which needs
DUNE_API_KEY and is currently unusable from this network) with direct
OrderFilled-log pulls from Polygon, joined to the existing data-api fills.

Contract reality (Etherscan getsourcecode / getcontractcreation):
  ctfExchangeV1     0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e  deployed 2022-09-26
  negRiskExchangeV1 0xc5d563a36ae78145c45a50134d48a1215220f80a  deployed 2023-11-28
  ctfExchangeV2     0xe111180000d2663c0091e4f400237545b87b996b  deployed 2026-03-31
  negRiskExchangeV2 0xe2222d279d744050d28e00520010520000310f59  deployed 2026-04-03
  exchangeV3        0xe3333700ca9d93003f00f0f71f8515005f6c00aa  deployed 2026-05-26

Event ABIs (verified against Etherscan getabi + raw on-chain logs):
  V1: OrderFilled(bytes32 indexed orderHash, address indexed maker,
      address indexed taker, uint256 makerAssetId, uint256 takerAssetId,
      uint256 makerAmountFilled, uint256 takerAmountFilled, uint256 fee)
      topic0 = keccak("OrderFilled(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)")
      BUY leg: makerAssetId == 0 (wallet gave collateral), takerAssetId != 0;
      usd = makerAmountFilled (1e6), shares = takerAmountFilled (1e6)
      (ground-truth match in data/fills.parquet: $33.2965 for 416.20625
      shares at price 0.08).
  V2/V3: OrderFilled(bytes32 indexed orderHash, address indexed maker,
      address indexed taker, Side side, uint256 tokenId,
      uint256 makerAmountFilled, uint256 takerAmountFilled, uint256 fee,
      bytes32 builder, bytes32 metadata)
      topic0 = keccak("OrderFilled(bytes32,address,address,uint8,uint256,uint256,uint256,uint256,bytes32,bytes32)")
      BUY leg: side == 0; usd = makerAmountFilled, shares = takerAmountFilled
      (verified in-tx: 68.09 USDC for 340.45 shares at price 0.20).

Provider reality: Etherscan V2 indexes the V1 exchanges (topic0 filter works,
1000 logs/page, ~5/s, raw rows carry blockNumber+timeStamp) but has a
permanent gap for the 2026 V2/V3 addresses; Alchemy free tier answers for
everything but caps eth_getLogs at 10 blocks.  So: V1-era days -> Etherscan;
V2-era days -> Alchemy (still-live V1 addresses included in the same filter).

Join architecture: on-chain logs cannot be filtered by token, so a sampled
day's logs map to only ~1% via position-id lookup — and most of the platform
is outside the tracked universe anyway.  Instead each sampled day's BUY legs
are joined to the fills.parquet (data-api ground truth) rows for the same
day by (txHash, maker wallet, shares, usd): fills.parquet supplies
marketId/outcome/price, the log supplies orderHash.  Unmatched legs are
fills of markets outside the tracked universe; skipped.

Why sampling: full history is millions of events — sample --per-month
deterministic days per month and rebuild the shipped burst-level rule and
the order-level rule on the SAME sampled fills. The comparison is
apples-to-apples within the sample; overlap deltas (what the order
definition sees that the burst definition misses) are the answer.
firstSeen (wallet age) comes from the FULL fills.parquet universe, so
ageDays/marketsSoFar stay honest.

Data per day under data/raw/dune/:
  orderFilledRaw_<YYYY-MM-DD>.csv  all parsed BUY legs (ts, account, tokenId,
                                   usd, shares, price, orderHash, exchange)
  onchainBuy_<YYYY-MM-DD>.csv      just the legs joined to fills.parquet
Run:  uv run python scripts/research/orderBurstOnchain.py [--per-month 2]
"""

import calendar
import csv
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[2]

DUNE_DIR = ROOT / "data" / "raw" / "dune"

EXCHANGES_V1 = {
    "ctfExchangeV1": "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",
    "negRiskExchangeV1": "0xc5d563a36ae78145c45a50134d48a1215220f80a",
}
EXCHANGES_V2 = {
    "ctfExchangeV2": "0xe111180000d2663c0091e4f400237545b87b996b",
    "negRiskExchangeV2": "0xe2222d279d744050d28e00520010520000310f59",
    "exchangeV3": "0xe3333700ca9d93003f00f0f71f8515005f6c00aa",
}
V1_TOPIC = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
V2_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
V2_DEPLOY = datetime(2026, 3, 31, tzinfo=timezone.utc)  # ctfExchangeV2 goes live
SAMPLE_START = datetime(2023, 10, 1, tzinfo=timezone.utc)

ETHERSCAN = "https://api.etherscan.io/v2/api"
ALCHEMY_HOST = "polygon-mainnet.g.alchemy.com"
PAGE = 1000
MAX_PAGES = 400

RAW_FIELDS = ["ts", "account", "tokenId", "usd", "shares", "price", "orderHash", "txHash", "exchange"]
ENRICHED_FIELDS = ["ts", "account", "marketId", "outcome", "shares", "price", "usd", "orderHash", "exchange"]


# ---------------------------------------------------------------- parse ---

def parseV1Log(log: dict, ts: int) -> dict | None:
    """BUY fill row from a V1 OrderFilled log; None if SELL or malformed."""
    topics = log.get("topics") or []
    if len(topics) < 3 or not log.get("data"):
        return None
    words = _words(log["data"])
    if len(words) < 4:
        return None
    makerAssetId, takerAssetId = int(words[0], 16), int(words[1], 16)
    if makerAssetId != 0 or takerAssetId == 0:
        return None  # SELL / mixed leg
    return _row(topics, words, ts, log)


def parseV2Log(log: dict, ts: int) -> dict | None:
    """BUY fill row from a V2/V3 OrderFilled log; None if SELL or malformed."""
    topics = log.get("topics") or []
    if len(topics) < 3 or not log.get("data"):
        return None
    words = _words(log["data"])
    if len(words) < 4 or int(words[0], 16) != 0:
        return None  # side != BUY or malformed
    return _row(topics, words, ts, log)


def _row(topics: list[str], words: list[str], ts: int, log: dict) -> dict:
    usd = int(words[2], 16) / 1e6
    shares = int(words[3], 16) / 1e6
    if usd <= 0 or shares <= 0:
        return None
    # indexed: topic1 = orderHash, topic2 = maker, topic3 = taker
    return {
        "ts": ts,
        "account": "0x" + topics[2][-40:] if len(topics) > 2 else "",
        "tokenId": canonicalTokenId(words[1]),
        "usd": usd,
        "shares": shares,
        "price": usd / shares,
        "orderHash": topics[1],
        "txHash": str(log.get("transactionHash") or "").lower(),
        "exchange": str(log.get("address") or "").lower(),
    }


def canonicalTokenId(word: str) -> str:
    return "0x%x" % int(word, 16)


def _words(data: str) -> list[str]:
    body = data[2:] if data.startswith("0x") else data
    return [body[i * 64:(i + 1) * 64] for i in range(len(body) // 64)]


# ------------------------------------------------------ block boundaries ---

def dayBlockSpan(client: httpx.Client, url: str, tip: int, day: date) -> tuple[int, int]:
    """First block with ts >= day 00:00 UTC and last block with ts < +24h."""
    t0 = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    t1 = t0 + 86400

    def tsOf(n: int) -> int:
        r = _rpc(client, url, "eth_getBlockByNumber", [hex(n), False])
        if not r:
            raise RuntimeError(f"block {n} unreachable")
        return int(r["timestamp"], 16)

    def firstAt(cond: int) -> int:
        lo, hi = 1, tip
        while lo < hi:
            mid = (lo + hi) // 2
            if tsOf(mid) < cond:
                lo = mid + 1
            else:
                hi = mid
        return lo

    start = firstAt(t0)
    end = firstAt(t1)
    if tsOf(end) < t1:
        end += 1  # Polygon tip lag; be safe
    return start, end - 1


def _rpc(client: httpx.Client, url: str, method: str, params: list) -> object | None:
    for attempt in range(3):
        try:
            body = client.post(url, json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params}).json()
            if body.get("result") is not None:
                return body["result"]
        except Exception:
            pass
        time.sleep(0.5 + attempt)
    return None


# ----------------------------------------------------------------- pulls ---

def pullEtherscanDay(client: httpx.Client, day: date, fromB: int, toB: int) -> list[dict]:
    """V1-era OrderFilled logs for both V1 exchanges. Etherscan raw rows carry
    blockNumber + timeStamp, so no extra block scan is needed. Dense ranges
    blow past the 10k (page x offset) window, so big ranges bisect into
    smaller block spans."""
    key = _envKey("ETHERSCAN_API_KEY")
    if not key:
        raise RuntimeError("ETHERSCAN_API_KEY missing; cannot pull V1 era")

    def fetchRange(addr: str, lo: int, hi: int) -> list[dict]:
        if lo > hi:
            return []
        logs = []
        page = 1
        attempt = 0
        while page <= MAX_PAGES:
            try:
                r = client.get(ETHERSCAN, params={
                    "chainid": 137, "module": "logs", "action": "getLogs",
                    "fromBlock": lo, "toBlock": hi,
                    "address": addr, "topic0": V1_TOPIC,
                    "page": page, "offset": PAGE, "apikey": key})
                body = r.json()
            except Exception:
                if attempt >= 5:
                    raise
                attempt += 1
                time.sleep(1.5 * attempt)
                continue
            attempt = 0
            if body.get("status") != "1":
                message = str(body.get("message") or "") + str(body.get("result") or "")
                if "No records" in message:
                    break
                if "rate limit" in message.lower() or "max calls" in message.lower():
                    if attempt >= 5:
                        raise RuntimeError(f"etherscan rate limit stuck: {message[:160]}")
                    attempt += 1
                    time.sleep(1.5 * attempt)
                    continue
                if "window is too large" in message or "PageNo" in message:
                    if hi - lo <= 10:
                        raise RuntimeError(f"etherscan range {lo}-{hi}: {message[:160]}")
                    mid = (lo + hi) // 2
                    return fetchRange(addr, lo, mid) + fetchRange(addr, mid + 1, hi)
                raise RuntimeError(f"etherscan getLogs: {str(body)[:200]}")
            batch = body.get("result") or []
            logs.extend(batch)
            if len(batch) < PAGE:
                break
            page += 1
            time.sleep(0.4)
        return logs

    logs = []
    for addr in EXCHANGES_V1.values():
        logs.extend(fetchRange(addr, fromB, toB))
        print(f"etherscan {day} {addr[:10]}..: cumulative {len(logs)} OrderFilled logs", flush=True)
    return logs


def pullAlchemyDay(client: httpx.Client, url: str, fromB: int, toB: int) -> list[dict]:
    """V2-era day pull: V2/V3 exchanges plus the still-live V1 addresses,
    both topics in one filter per 10-block window. Windows go out in batched
    JSON-RPC arrays (8 per HTTP POST) to cut request overhead."""
    addresses = list(EXCHANGES_V2.values()) + list(EXCHANGES_V1.values())
    topics = [[V2_TOPIC, V1_TOPIC]]

    windows = [(b, min(b + 9, toB)) for b in range(fromB, toB + 1, 10)]
    batches = [windows[i:i + 8] for i in range(0, len(windows), 8)]
    logs = []
    startT = time.time()

    def fetchBatch(batch: list[tuple[int, int]]) -> list[dict]:
        payload = [
            {"jsonrpc": "2.0", "id": i, "method": "eth_getLogs", "params": [{
                "address": addresses, "fromBlock": hex(b), "toBlock": hex(e),
                "topics": topics}]}
            for i, (b, e) in enumerate(batch)
        ]
        for attempt in range(4):
            try:
                rows = client.post(url, json=payload).json()
                results = {item.get("id"): item.get("result") for item in rows}
                if any(v is None for v in results.values()):
                    # a missing result inside the batch -> re-tag missing windows one by one
                    logs = []
                    for i, (b, e) in enumerate(batch):
                        result = results.get(i)
                        if result is None:
                            single = fetchWindow((b, e))
                            logs.extend(single)
                        else:
                            logs.extend(result)
                    return logs
                return [log for result in results.values() for log in (result or [])]
            except Exception:
                time.sleep(1.0 + attempt)
        small: list[dict] = []
        for window in batch:
            small.extend(fetchWindow(window))
        return small

    def fetchWindow(window: tuple[int, int]) -> list[dict]:
        return _rpc(client, url, "eth_getLogs", [{
            "address": addresses, "fromBlock": hex(window[0]),
            "toBlock": hex(window[1]), "topics": topics}]) or []

    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, chunk in enumerate(ex.map(fetchBatch, batches)):
            logs.extend(chunk)
            if (i + 1) % 25 == 0:
                rate = (i + 1) / (time.time() - startT)
                done = min((i + 1) * 8, len(windows))
                print(f"  {done}/{len(windows)} windows, {len(logs)} logs, {rate:.1f} batch/s", flush=True)
    print(f"alchemy: {len(windows)} windows -> {len(logs)} OrderFilled logs", flush=True)
    return logs


def blockTimestamps(client: httpx.Client, url: str, blocks: list[int]) -> dict[int, int]:
    uniq = sorted(set(blocks))
    out: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for n, result in zip(uniq, ex.map(
                lambda b: _rpc(client, url, "eth_getBlockByNumber", [hex(b), False]), uniq)):
            if result:
                out[n] = int(result["timestamp"], 16)
    return out


# ----------------------------------------------------------- day caching ---

def pullDay(client: httpx.Client, url: str, day: date, tip: int) -> tuple[int, list[dict]]:
    """Pull one sampled day: parse BUY legs, cache raw, join to
    fills.parquet, cache the enriched universe rows."""
    t0dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    fromB, toB = dayBlockSpan(client, url, tip, day)
    print(f"{day}: blocks {fromB} -> {toB}", flush=True)
    if t0dt >= V2_DEPLOY:
        rawLogs = pullAlchemyDay(client, url, fromB, toB)
        tss = blockTimestamps(client, url, [int(str(l.get("blockNumber") or "0"), 16) for l in rawLogs])
    else:
        rawLogs = pullEtherscanDay(client, day, fromB, toB)
        tss = {}
    legs, skipped = [], 0
    for log in rawLogs:
        blockHex = log.get("blockNumber")
        if blockHex is None:
            skipped += 1
            continue
        topic0 = (log.get("topics") or [None])[0]
        # Etherscan gives timeStamp directly; Alchemy rows need block ts lookup
        if log.get("timeStamp"):
            ts = int(str(log["timeStamp"]), 16)
        else:
            ts = tss.get(int(str(blockHex), 16), 0)
            if not ts:
                skipped += 1
                continue
        if topic0 == V1_TOPIC:
            leg = parseV1Log(log, ts)
        elif topic0 == V2_TOPIC:
            leg = parseV2Log(log, ts)
        else:
            leg = None
        if leg is None:
            skipped += 1
            continue
        legs.append(leg)
    rawPath = DUNE_DIR / f"orderFilledRaw_{day.isoformat()}.csv"
    writeCsv(rawPath, RAW_FIELDS, legs)
    print(f"  raw {len(legs)} BUY legs ({skipped} logs skipped) -> {rawPath.name}", flush=True)

    enriched = enrichLegs(day, legs)
    outPath = DUNE_DIR / f"onchainBuy_{day.isoformat()}.csv"
    writeCsv(outPath, ENRICHED_FIELDS, enriched)
    print(f"  joined {len(enriched)} universe fills -> {outPath.name}", flush=True)
    return len(legs), enriched


def writeCsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- enrich ---

def universeDayFills(day: date) -> pl.DataFrame | None:
    """data-api fills for one sampled day, from data/ + data/universe."""
    t0 = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=1)
    frames = []
    for d in [ROOT / "data", ROOT / "data" / "universe"]:
        p = d / "fills.parquet"
        if not p.exists():
            continue
        frame = (pl.scan_parquet(p)
                 .filter((pl.col("ts") >= t0) & (pl.col("ts") < t1) & (pl.col("side") == "BUY"))
                 .select("ts", "txHash", "account", "marketId", "outcome", "size", "price")
                 .collect())
        frames.append(frame)
    if not frames:
        return None
    return pl.concat(frames, how="diagonal_relaxed")


def enrichLegs(day: date, legs: list[dict]) -> list[dict]:
    """Join sampled BUY legs to data-api ground truth by (txHash, wallet,
    shares, usd). fills.parquet supplies marketId/outcome/price; the log
    supplies orderHash. Unmatched legs are mostly fills of markets outside
    the tracked universe (the data-api only covers the fetched events)."""
    dayFills = universeDayFills(day)
    if not legs or dayFills is None or dayFills.height == 0:
        return []
    legsFrame = (
        pl.DataFrame([l for l in legs if l.get("txHash")], schema_overrides={
            "ts": pl.Int64, "usd": pl.Float64, "shares": pl.Float64})
        .with_columns(
            pl.from_epoch(pl.col("ts"), time_unit="s").dt.replace_time_zone("UTC").alias("legTs"))
        .select("legTs", "account", "usd", "shares", "orderHash", "tokenId", "exchange", "txHash")
    )
    bus = dayFills.select(
        pl.col("ts").alias("fillTs"), "txHash",
        pl.col("account").alias("wallet"),
        "marketId", "outcome", "size", "price",
        (pl.col("size") * pl.col("price")).alias("usdData"),
    )
    joined = legsFrame.join(bus, on="txHash", how="inner")
    tol = pl.max_horizontal((pl.col("size") * 5e-4).abs(), pl.lit(0.05))
    pairs = joined.filter(
        (pl.col("account") == pl.col("wallet"))
        & ((pl.col("shares") - pl.col("size")).abs() <= 0.02)
        & ((pl.col("usd") - pl.col("usdData")).abs() <= tol)
        & ((pl.col("legTs") - pl.col("fillTs")).abs() <= pl.duration(seconds=2)))
    if pairs.height == 0:
        return []
    # greedy min-total-diff pairing per (tx, wallet, moment): a tx can hold
    # several same-wallet legs; keep the closest amount pair.
    pairs = pairs.with_columns(
        ((pl.col("shares") - pl.col("size")).abs()
         + (pl.col("usd") - pl.col("usdData")).abs()).alias("pairDiff"))
    pairs = pairs.sort("pairDiff").unique(subset=["txHash", "wallet", "legTs"], keep="first")
    return [{
        "ts": str(row["legTs"]),
        "account": row["account"],
        "marketId": row["marketId"],
        "outcome": row["outcome"],
        "shares": row["size"],
        "price": row["price"],
        "usd": row["usdData"],
        "orderHash": row["orderHash"],
        "exchange": row["exchange"],
    } for row in pairs.iter_rows(named=True)]



def fileSummary() -> str:
    caches = sorted(DUNE_DIR.glob("onchainBuy_*.csv"))
    if not caches:
        return "pull done, no cached days yet"
    total = sum(pl.read_csv(p, infer_schema_length=0).height for p in caches)
    raw = sum(pl.read_csv(p, infer_schema_length=0).height for p in DUNE_DIR.glob("orderFilledRaw_*.csv"))
    return f"pull done: {total} joined universe fills, {raw} raw legs, {len(caches)} days"


# -------------------------------------------------------------- sampling ---

def sampleDays(monthsFrom: tuple[int, int], perMonth: int, seed: int = 7) -> list[date]:
    today = datetime.now(timezone.utc).date()
    out: list[date] = []
    rng = random.Random(seed)
    y, m = monthsFrom
    while (y, m) <= (today.year, today.month):
        last = calendar.monthrange(y, m)[1]
        chosen: set[int] = set()
        while len(chosen) < min(perMonth, last):
            chosen.add(rng.randrange(1, last + 1))
        out.extend(sorted(date(y, m, d) for d in chosen))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _envKey(name: str) -> str:
    import os
    found = os.environ.get(name, "").strip()
    if found:
        return found
    for path in [Path.cwd() / ".env", ROOT / ".env"]:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return ""


def main() -> None:
    args = sys.argv[1:]
    perMonth = int(args[args.index("--per-month") + 1]) if "--per-month" in args else 2
    monthsFrom = (SAMPLE_START.year, SAMPLE_START.month)
    if "--months-from" in args:
        y, m = args[args.index("--months-from") + 1].split("-")
        monthsFrom = (int(y), int(m))
    skip = "--skip-pull" in args

    apiKey = _envKey("ALCHEMY_API_KEY")
    if not apiKey:
        sys.exit("ALCHEMY_API_KEY missing")
    url = f"https://{ALCHEMY_HOST}/v2/{apiKey}"
    client = httpx.Client(timeout=60.0)
    head = _rpc(client, url, "eth_blockNumber", [])
    if not head:
        sys.exit("could not read eth_blockNumber")
    tip = int(str(head), 16)

    days = sampleDays(monthsFrom, perMonth)
    print(f"sample plan: {len(days)} days ({perMonth}/month)", flush=True)
    if not skip:
        for d in days:
            if (DUNE_DIR / f"onchainBuy_{d.isoformat()}.csv").exists():
                continue
            try:
                pullDay(client, url, d, tip)
            except Exception as exc:
                print(f"{d} FAILED: {str(exc)[:200]}", flush=True)

    print(fileSummary(), flush=True)


if __name__ == "__main__":
    main()
