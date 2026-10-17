"""Third-universe scan: burst-population census of the non-military
insider-evidence category tags (ideasResearch §4).

Gamma API notes (verified live 2026-10):
- offset pagination on /events walls at ~5000 rows with a validation error
  ("offset too large, use /events/keyset");
- /events/keyset paginates ONLY through the `after_cursor` param — passing
  the opaque next_cursor as `cursor` is silently ignored and the same head
  page comes back forever (caught live by the id-regression guard below);
- limit is clamped to 100;
- `include_markets=false` strips markets so the census pass carries event
  rows only (weights drop from ~7.5KB to ~0.3KB per event) — resolution and
  per-market fee data then live in the second, volume-floor slice (`volume_min`
  works server-side on keyset, so the >= $20k slice is complete, not sampled).

Two cached passes per tag under data/raw/thirdUniverse/<tag>/:

1. census: every closed event, slim row cache (id/closed/closedTime/volume/
   dates), 100/keyset page. Yields total closed counts.
2. floor slice: closed=true, volume_min=20000, full markets (one keyset page
   each). Filtered afterwards to resolved events (all markets closed with a
   0/1 outcome); yields resolved share over the closed corpus, volume
   distribution, feesEnabled share, date range, markets >= $500k/$100k/$20k,
   and the top-60-by-volume sample pool. Cached to <tag>/markets.json.

3. burst estimate WITHOUT full-universe fills pulls: for the top-60-by-volume
   resolved markets per category, pull data-api /trades BUY fills
   (takerOnly=false — both CLOB legs, the shipped fetch pipeline's behaviour;
   backward-walking through the 10k-offset wall via fetch.collectTrades).
   Burst semantics COPIED from scripts/research/entrySweep.py:107-108
   (entrySweep exposes no burst-length constant; see
   research/thirdUniverseScan.md): BUY fills per (account, marketId,
   outcome), a gap > 10 minutes (burstSec = 600) starts a new burst, burst
   USD = sum(size * price). Counted per market and per tier (>= $5k/$10k/
   $50k), plus single-fill >= $5k wallets and fill-tape density.

Run from the repo root:
  uv run python scripts/research/thirdUniverseScan.py            # all phases
  uv run python scripts/research/thirdUniverseScan.py --refresh-crawl earnings
  uv run python scripts/research/thirdUniverseScan.py --refresh-trades

Cache is append-only and keyed (one file per keyset page / per market's
trade walk), so re-runs cost nothing network-side.
"""

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from polycrawler.fetch import collectTrades, fillDedupeKeys, winnerFrom
from polycrawler.http import HttpSession

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "thirdUniverse"

gammaApi = "https://gamma-api.polymarket.com"
gammaHost = "gamma-api.polymarket.com"
GAMMA_RATE = 4.0  # req/s, same pacing as the oosExpansion roster crawl

# ideasResearch §4 candidates + the cheap third probe requested in the task
# brief. sp-500 is the slug gamma resolves for stock-index questions
# (s-p-500 / stock-indexes keyset empty); reported however small it is.
CATS = ["earnings", "merger", "acquisition", "fda", "sp-500"]

VOLUME_FLOOR = 20_000.0
TOP_N = 60
BURST_SEC = 600.0  # copied from entrySweep.py:107-108 ("minutes=10"), see module docstring
TIERS = [(5_000.0, "bursts5k"), (10_000.0, "bursts10k"), (50_000.0, "bursts50k")]
BIG_MARKS = [500_000.0, 100_000.0, 20_000.0]

CENSUS_SLIM = {"id", "slug", "closed", "closedTime", "volume",
               "startDate", "endDate", "active", "automaticallyResolved"}
PAGE = 100


def log(msg: str) -> None:
    print(f"{LOG_MARK}[{time.time() - t0:7.1f}s] {msg}", flush=True)


LOG_MARK = "[3US] "

# ------------------------------------------------------------- crawl ---


def keysetChain(session: HttpSession, tag: str, extra: dict[str, str],
                pagePath: Any, slim: bool, force: bool) -> list[dict[str, Any]]:
    """Walk /events/keyset across a tag, one slim cache file per page.

    Guards: the cursor chain must advance (first event id strictly greater
    than the previous page's last id) — the API silently ignores a misnamed
    cursor param and would loop on the head page forever. An error-shaped
    payload retries through the HttpSession adapter, and a repeated page
    stops the walk instead of caching an unbounded duplicate pile.
    """
    outDir = RAW_DIR / tag
    outDir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    afterCursor: str | None = None
    page = 0
    lastId = -1
    while True:
        path = RAW_DIR / tag / f"{pagePath}_{page:04d}.json"
        if path.exists() and path.stat().st_size > 2 and not force:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                rows = data["rows"]
                afterCursor = data["nextCursor"]
            else:  # legacy bare-row cache: chain state unknown, stop after replay
                rows = data
                afterCursor = None
            cached = True
        else:
            cached = False
            params: dict[str, Any] = {"closed": "true", "tag_slug": tag, "limit": PAGE, **extra}
            if afterCursor is not None:
                params["after_cursor"] = afterCursor
            payload = session.getJson(f"{gammaApi}/events/keyset", params)
            rows = payload.get("events") or []
            if slim:
                rows = [{k: r.get(k) for k in CENSUS_SLIM} for r in rows]
            path.write_text(json.dumps({"rows": rows, "nextCursor": payload.get("next_cursor")}))
        if not rows:
            break
        firstId = int(rows[0]["id"])
        if lastId >= 0 and firstId <= lastId:
            log(f"{tag}: keyset cursor did not advance at page {page} "
                f"(first id {firstId} <= {lastId}) — stopping")
            break
        lastId = int(rows[-1]["id"])
        events.extend(rows)
        page += 1
        if page % 50 == 0:
            log(f"{tag}/{pagePath}: page {page}, {len(events)} events")
        afterCursor = payload.get("next_cursor") if not cached else afterCursor
        if not afterCursor:
            break
    log(f"{tag}/{pagePath}: done — {page} pages, {len(events)} events ({'cached' if cached else 'fresh'})")
    return events


def censusTag(session: HttpSession, tag: str, force: bool) -> dict[str, Any]:
    events = keysetChain(session, tag, {}, "census", slim=True, force=force)
    closedTime = [str(e["closedTime"]) for e in events if e.get("closedTime")]
    volumes = sorted(float(e.get("volume") or 0) for e in events)
    return {
        "closedEvents": len(events),
        "closedOver20k": sum(1 for v in volumes if v >= VOLUME_FLOOR),
        "closedVolumeP50": percentile(volumes, 50),
        "closedVolumeP90": percentile(volumes, 90),
        "closedVolumeMax": percentile(volumes, 100),
        "dateRange": [min(closedTime)[:10] if closedTime else None,
                      max(closedTime)[:10] if closedTime else None],
    }


# ------------------------------------------------------------- census ---

def marketResolved(market: dict[str, Any]) -> bool:
    if not market.get("closed"):
        return False
    return winnerFrom(market.get("outcomes") or [], market.get("outcomePrices") or "") is not None


def eventResolved(event: dict[str, Any]) -> bool:
    markets = event.get("markets") or []
    return bool(markets) and all(marketResolved(m) for m in markets)


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def eventVolume(event: dict[str, Any]) -> float:
    vol = num(event.get("volume"))
    if vol > 0:
        return vol
    return sum(num(m.get("volumeNum") or m.get("volume")) for m in event.get("markets") or [])


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p / 100 * len(ordered)))]


def summarizeTag(tag: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolved slice census for one tag (phase-2 corpus, markets.json)."""
    resolved = [ev for ev in events if eventResolved(ev)]
    volumes = [eventVolume(ev) for ev in resolved]
    feeAll = feeMarkets = 0
    bigCounts = defaultdict(int)
    endDates: list[str] = []
    marketRows: list[dict[str, Any]] = []
    for ev in resolved:
        if ev.get("endDate"):
            endDates.append(str(ev["endDate"]))
        for m in ev.get("markets") or []:
            feeAll += 1
            isFee = bool(m.get("feesEnabled"))
            feeMarkets += int(isFee)
            vol = num(m.get("volumeNum") or m.get("volume"))
            for mark in BIG_MARKS:
                bigCounts[mark] += int(vol >= mark)
            marketRows.append({
                "conditionId": str(m.get("conditionId") or "").lower(),
                "eventSlug": ev.get("slug"),
                "question": m.get("question"),
                "volume": vol,
                "feesEnabled": isFee,
            })
    marketRows.sort(key=lambda r: -r["volume"])
    (RAW_DIR / tag / "markets.json").write_text(json.dumps(marketRows))
    return {
        "floorEvents": len(events),
        "resolvedEvents": len(resolved),
        "unresolvedFloorEvents": len(events) - len(resolved),
        "resolvedVolumeP50": round(percentile(volumes, 50)),
        "resolvedVolumeP90": round(percentile(volumes, 90)),
        "resolvedVolumeMax": round(percentile(volumes, 100)),
        "marketsInResolvedSlice": len(marketRows),
        "marketsOver500k": bigCounts[500_000.0],
        "marketsOver100k": bigCounts[100_000.0],
        "marketsOver20k": bigCounts[20_000.0],
        "marketsWithFees": feeMarkets,
        "feeShare": round(feeMarkets / feeAll * 100, 1) if feeAll else 0.0,
        "dateRange": [min(endDates)[:10] if endDates else None,
                      max(endDates)[:10] if endDates else None],
    }


# ------------------------------------------------------------- bursts ---


def dedupeFills(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out = []
    for row in rows:
        key = tuple(row.get(name) for name in fillDedupeKeys)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def burstsFor(marketId: str, fills: list[dict[str, Any]]) -> dict[str, Any]:
    """entrySweep burst semantics on one market's BUY fills (BURST_SEC above).

    Fills grouped per (account, outcome) — the market bucket is implicit since
    the caller segments by market; a gap > 10 min starts a new burst; burst
    USD = sum(size * price).
    """
    usd = lambda g: sum(float(r["size"]) * float(r["price"]) for r in g)
    byWallet: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(fills, key=lambda r: int(r["timestamp"])):
        byWallet[(str(row["proxyWallet"]).lower(), str(row.get("outcome") or ""))].append(row)

    burstOwners: list[tuple[str, list[dict[str, Any]]]] = []
    for (acc, _outcome), group in byWallet.items():
        start = 0
        for i in range(1, len(group) + 1):
            if i == len(group) or int(group[i]["timestamp"]) - int(group[i - 1]["timestamp"]) > BURST_SEC:
                burstOwners.append((acc, group[start:i]))
                start = i

    counts = {}
    for threshold, name in TIERS:
        counts[name] = sum(1 for _a, g in burstOwners if usd(g) >= threshold)
    bigPrints = sorted(len(g) for _a, g in burstOwners if usd(g) >= 5_000.0)
    singleFillWallets = {acc for acc, group in byWallet.items()
                         if max(float(r["size"]) * float(r["price"]) for r in group) >= 5_000.0}
    burstWallets = {acc for acc, g in burstOwners if usd(g) >= 5_000.0}

    times = [int(r["timestamp"]) for r in fills]
    spanHours = (max(times) - min(times)) / 3600.0 if len(times) >= 2 else 0.0
    return {
        "marketId": marketId,
        "fillCount": len(fills),
        "spanHours": round(spanHours, 1),
        "printsPerHour": round(len(fills) / spanHours, 1) if spanHours > 0 else 0.0,
        "walletsSingleFill5k": len(singleFillWallets),
        "walletsAnyBurst5k": len(burstWallets),
        "bursts5k": counts["bursts5k"],
        "bursts10k": counts["bursts10k"],
        "bursts50k": counts["bursts50k"],
        "bigBurstPrintsMedian": bigPrints[len(bigPrints) // 2] if bigPrints else 0,
    }


def tradesCachePath(tag: str, marketId: str) -> Path:
    return RAW_DIR / tag / f"trades_{marketId.split('0x')[1][:64]}.json"


def pullTrades(session: HttpSession, tag: str, marketId: str, refresh: bool) -> list[dict[str, Any]]:
    """BUY fills for one market (fetch.collectTrades walks the 10k-offset
    wall backward by timestamp, exactly the shipped pipeline)."""
    path = tradesCachePath(tag, marketId)
    if path.exists() and path.stat().st_size > 2 and not refresh:
        return json.loads(path.read_text())
    try:
        rows = collectTrades(session.client, marketId, side="BUY")
    except RuntimeError as exc:
        log(f"{tag}: trades pull failed for {marketId[:16]}: {str(exc)[:160]}")
        rows = []
    path.write_text(json.dumps(dedupeFills(rows)))
    return rows


# ------------------------------------------------------------- output ---

DASH = "—"


def renderReport(summaries: list[dict[str, Any]], burstRows: list[dict[str, Any]]) -> str:
    lines = [
        "# Third-universe scan machine report (human readout: research/thirdUniverseScan.md)",
        "",
        "## Corpus per category (keyset census + >= $20k resolved slice)",
        "",
        "| tag | closed ev | closed ev >=20k | floor-slice ev | resolved ev | resolved p50/p90/max vol | mkts | >=500k | >=100k | >=20k | fee % | date range (ev endDate) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['tag']} | {s['closedEvents']} | {s['closedOver20k']} "
            f"| {s['floorEvents']} | {s['resolvedEvents']} "
            f"| {s['resolvedVolumeP50']}/{s['resolvedVolumeP90']}/{s['resolvedVolumeMax']} "
            f"| {s['marketsInResolvedSlice']} | {s['marketsOver500k']} | {s['marketsOver100k']} "
            f"| {s['marketsOver20k']} | {s['feeShare']} | {s['dateRange'][0] or DASH} → {s['dateRange'][1] or DASH} |")
    lines += [
        "",
        "## Burst estimate (top-60-by-volume resolved markets per category)",
        "",
        "| tag | mkts | fills | bursts >=5k | >=10k | >=50k | 1-fill >=5k wallets | wallets w/ >=5k burst | mkts w/ >=5k burst | prints/mkt-hr | med prints in 5k burst |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    byTag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in burstRows:
        byTag[row["tag"]].append(row)
    for tag in CATS:
        rows = byTag.get(tag) or []
        if not rows:
            lines.append(f"| {tag} | 0 | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} | {DASH} |")
            continue
        marketsWithBurst = sum(1 for r in rows if r["bursts5k"] > 0)
        lines.append(
            f"| {tag} | {len(rows)} | {sum(r['fillCount'] for r in rows)} "
            f"| {sum(r['bursts5k'] for r in rows)} | {sum(r['bursts10k'] for r in rows)} "
            f"| {sum(r['bursts50k'] for r in rows)} | {sum(r['walletsSingleFill5k'] for r in rows)} "
            f"| {sum(r['walletsAnyBurst5k'] for r in rows)} | {marketsWithBurst} "
            f"| {sum(r['printsPerHour'] for r in rows) / len(rows):.1f} "
            f"| {sorted(r['bigBurstPrintsMedian'] for r in rows)[len(rows) // 2]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["all", "crawl", "report"], default="all")
    ap.add_argument("--refresh-crawl", nargs="*", default=[], metavar="TAG")
    ap.add_argument("--refresh-trades", action="store_true")
    ap.add_argument("--top-n", type=int, default=TOP_N)
    ap.add_argument("--cats", nargs="*", default=CATS)
    ap.add_argument("--skip-census", action="store_true",
                    help="reuse cached census counts, skip the keyset census walk")
    args = ap.parse_args()
    force = set(args.refresh_crawl)

    summariesPath = RAW_DIR / "summaries.json"
    burstPath = RAW_DIR / "burstRows.json"
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0,
                      headers={"User-Agent": "polycrawler2-third-universe-scan"}) as client:
        session = HttpSession(client, hostRates={gammaHost: GAMMA_RATE})
        stored = {s["tag"]: s for s in (json.loads(summariesPath.read_text())
                                        if summariesPath.exists() else [])}

        # ---- census keyset walk + floor slice
        if args.phase in ("all", "crawl"):
            for tag in args.cats:
                if args.skip_census and tag in stored and "closedEvents" in stored[tag]:
                    log(f"{tag}: census cached")
                else:
                    c = censusTag(session, tag, force=tag in force)
                    stored[tag] = {**stored.get(tag, {}), **c, "tag": tag}
                    log(f"{tag}: census {c['closedEvents']} closed events "
                        f"({c['closedOver20k']} >= $20k), "
                        f"range {c['dateRange'][0]} → {c['dateRange'][1]}")
                floorPath = RAW_DIR / tag / "floor.json"
                if floorPath.exists() and tag not in force:
                    events = json.loads(floorPath.read_text())
                else:
                    events = keysetChain(session, tag,
                                         {"volume_min": str(int(VOLUME_FLOOR))},
                                         "floor", slim=False, force=tag in force)
                    floorPath.write_text(json.dumps(events))
                stored[tag] = {**stored[tag], **summarizeTag(tag, events)}
                s = stored[tag]
                log(f"{tag}: {s['resolvedEvents']}/{s['floorEvents']} floor-slice events resolved, {s['marketsInResolvedSlice']} markets, "
                    f"fee share {s['feeShare']}%")
            summaries = [stored[t] for t in args.cats if t in stored]
            summariesPath.write_text(json.dumps(summaries, indent=1))

        burstRows: list[dict[str, Any]] = []
        if burstPath.exists():
            burstRows = json.loads(burstPath.read_text())
        cachedByTag: dict[str, set[str]] = defaultdict(set)
        for row in burstRows:
            cachedByTag[row["tag"]].add(row["marketId"])

        # ---- burst estimate on the top-N by volume
        if args.phase in ("all", "report"):
            for tag in args.cats:
                marketRowsPath = RAW_DIR / tag / "markets.json"
                if not marketRowsPath.exists():
                    log(f"{tag}: no floor slice cached, skipping burst phase")
                    continue
                picks = json.loads(marketRowsPath.read_text())[:args.top_n]
                done = cachedByTag[tag]
                todo = [m for m in picks if m["conditionId"] not in done]
                log(f"{tag}: burst phase — {len(done)}/{len(picks)} cached, {len(todo)} to pull")
                for i, m in enumerate(todo):
                    rows = pullTrades(session, tag, m["conditionId"], refresh=args.refresh_trades)
                    burstRows.append({"tag": tag, **burstsFor(m["conditionId"], rows)})
                    if (i + 1) % 20 == 0:
                        log(f"{tag}: {i + 1}/{len(todo)} markets burst-profiled")
                        burstPath.write_text(json.dumps(burstRows))
            burstPath.write_text(json.dumps(burstRows))

    if args.phase == "all" or args.phase == "report":
        summaries = [stored[t] for t in args.cats if t in stored]
        report = renderReport(summaries, burstRows)
        print(report)
        logPath = ROOT / "logs" / "thirdUniverseScan.log"
        logPath.parent.mkdir(exist_ok=True)
        with logPath.open("a") as fh:
            fh.write(f"\n=== run {datetime.now(timezone.utc).isoformat()} ===\n{report}\n")
        log(f"report rendered and appended to {logPath.relative_to(ROOT)}")
    log(f"total runtime {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
