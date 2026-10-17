"""Falsification/verification of the sports-favorites T-7d edge on our own
tape (research/ideaGenAlpha.md §2(h), pre-registered in
research/sportsT7d.md BEFORE any fetch).

Source claim (sturzael/polymarket-edge-research, re-fetched 2026-10-17):
resolved MLB/NBA/NFL/NHL game-outcome favorites priced 0.55-0.60 at T-7d
resolve YES ~+25-30pp above the implied read (e16 yes_rate 0.875 @ 0.575,
z=5.1, n=32; e23 +25.8pp, z=7.6, n=120 on vol >= $5k, lifespan <= 14d,
window vol >= $5k). Cross-venue control: Betfair <= +/-6pp, Azuro <= +3pp
at their own close-anchored windows.

We do NOT accept their z. Their exact extraction rule (e16
05_fixed_time_calibration.py, registered §1.1): anchor = end_date - 7d,
+/-12h window, >= 3 prints, size-weighted VWAP of the favorite's price,
5pp buckets, stat = yes_rate - bucket_mid. Our tape: trailing last print in
[T-7d-12h, T-7d] (favorite token, counter-token print => 1-p when the
favorite side itself is untraded); their window-VWAP recomputed beside it
as the comparability/robustness column. Scope is stricter on volume ($50k
market floor vs their $5k) so a positive cell is conservative.

Phases (append-only caches under data/raw/sportsT7d/):
1. crawl: Gamma /events/keyset per tag (mlb/nba/nfl/nhl), closed=true,
   volume_min=50000 server-side (after_cursor rail per
   scripts/research/thirdUniverseScan.py); select one game-outcome market
   per event (volume >= $50k, end-start >= 8d, binary non-Yes/No, slug
   contains "-vs-"); pull data-api BUY fills via fetch.collectTrades
   (backward-walk over the 10k-offset wall); extract per-horizon snapshots
   (T-14d/T-7d/T-5d/T-3d: trailing print + +/-12h VWAP + window stats).
2. grade: per 5pp band 0.50-0.95 - n, realized winRate, implied band mid,
   calibration excess, z (their formula), break-even winRate (50bps exec),
   mean ret / $100 copy, per-event bootstrap p5/P(>0) (BOOTS=1000, seed 42,
   entrySweep.evaluate idiom), top-event share (oosTransport idiom),
   time-half split (HALF_SPLIT = entrySweep's), fee-net regrade with the
   feeMarkRegrade machinery (winner pays 10% of redemption on fee-marked
   conditions). Verdict strictly follows the registered ladder + kill rule.

Run (from repo root):
  uv run python scripts/research/sportsT7d.py 2>&1 | tee logs/sportsT7d.log
  uv run python scripts/research/sportsT7d.py --refresh-crawl
  uv run python scripts/research/sportsT7d.py --grade-only (after phase 1)
"""

import argparse
import importlib.util
import json
import random
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from polycrawler.fetch import collectTrades, fillDedupeKeys, winnerFrom
from polycrawler.http import HttpSession

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "sportsT7d"

gammaApi = "https://gamma-api.polymarket.com"
gammaHost = "gamma-api.polymarket.com"
dataApiHost = "data-api.polymarket.com"
RATE = 4.0  # req/s cap per the study spec (Gamma host; HttpSession rails it)

TAGS = ["mlb", "nba", "nfl", "nhl"]
PAGE = 100
HORIZONS = [14, 7, 5, 3]  # days before end_date; T-7d decides, rest = sensitivity
WINDOW_SEC = 12 * 3600  # +/-12h, their e16 convention
MIN_VWAP_PRINTS = 3  # their e16 inclusion rule for the VWAP column
MIN_MARKET_VOLUME = 50_000.0  # task brief: ~8.5x their $5k floor
MIN_DUR_DAYS = 8.0  # their rule: market duration >= offset + 1
EVENT_CAP = 3200
PER_SPORT_CAP = 800
SEED = 42
BOOTS = 1000
MIN_CELL = 20
EXEC_COST = 0.005  # 50bps of notional, ideaGenAlpha §2(h) spec
WIN_FEE = 0.10  # fee-marked conditions: winner pays 10% of redemption (R13 model)
HALF_SPLIT = datetime(2025, 6, 1, tzinfo=UTC)  # entrySweep idiom

BANDS = [(lo / 100.0, (lo + 5) / 100.0) for lo in range(50, 95, 5)]
HEADLINE_BAND = (0.55, 0.60)
EXCESS_DECAY = 0.08  # < 8pp => citation-confirmed decay (ideaGenAlpha §2(h))
EXCESS_GRADUATE = 0.15  # >= 15pp => graduate (>= half the cited 25.8pp)
EXCESS_PRICED = 0.03  # kill rule: everything graded <= +3pp and no PASS

SLUG_GAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
SLUG_SUFFIX = re.compile(
    r"-(spread|totals?|nrfi|over|under|points?|inning|1h|2h|half|moneyline|draw"
    r"|outright|handicap|parlay|totd|goals)", re.IGNORECASE)
SLUG_BANNED = re.compile(
    r"(series|advance|outright|futures|champio|finals|matchup)", re.IGNORECASE)
LEGACY_GAME_ML = re.compile(r"(who-will-win-game-\d+-of|-game-\d+$)", re.IGNORECASE)

logMark = "[S7D] "


def log(msg: str) -> None:
    print(f"{logMark}[{time.time() - t0:7.1f}s] {msg}", flush=True)


def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def parseIsoTs(value: Any) -> int | None:
    """Gamma prints ISO timestamps with arbitrary-precision fractional seconds
    (e.g. .99774); pad/trim the fraction for fromisoformat."""
    if not value:
        return None
    text = str(value).replace("Z", "")
    dot = text.find(".")
    if dot >= 0:
        plus = text.find("+", dot)
        frac = text[dot + 1:plus] if plus >= 0 else text[dot + 1:]
        tail = text[plus:] if plus >= 0 else ""
        text = text[:dot + 1] + frac.ljust(max(len(frac), 1), "0")[:6] + tail
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return None


def bandLabel(band: tuple[float, float]) -> str:
    return f"{band[0]:.2f}-{band[1]:.2f}"


def loadSibling(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "research" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fm = loadSibling("sportsT7dFee", "feeMarkRegrade.py")

# ------------------------------------------------------------- events ---


def keysetEvents(session: HttpSession, tag: str, force: bool) -> list[dict[str, Any]]:
    """Gamma /events/keyset walk for one tag: /events/keyset paginates ONLY
    through the after_cursor param (passing it as `cursor` is silently
    ignored — the R6 guard), limit clamps to 100, volume_min filters
    server-side. One cache file per page under data/raw/sportsT7d/<tag>/."""
    outDir = RAW_DIR / tag
    outDir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    afterCursor: str | None = None
    lastId = -1
    page = 0
    while True:
        path = outDir / f"events_{page:04d}.json"
        if path.exists() and path.stat().st_size > 2 and not force:
            data = json.loads(path.read_text())
            rows, afterCursor = data["rows"], data.get("nextCursor")
        else:
            params: dict[str, Any] = {"closed": "true", "tag_slug": tag,
                                      "volume_min": str(int(MIN_MARKET_VOLUME)),
                                      "limit": PAGE}
            if afterCursor is not None:
                params["after_cursor"] = afterCursor
            payload = session.getJson(f"{gammaApi}/events/keyset", params)
            rows = payload.get("events") or []
            afterCursor = payload.get("next_cursor")
            path.write_text(json.dumps({"rows": rows, "nextCursor": afterCursor}))
        if not rows:
            break
        firstId = int(rows[0]["id"])
        if lastId >= 0 and firstId <= lastId:
            log(f"{tag}: keyset cursor did not advance at page {page} - stopping")
            break
        lastId = int(rows[-1]["id"])
        events.extend(rows)
        page += 1
        if page % 10 == 0:
            log(f"{tag}: page {page}, {len(events)} events (vol >= ${MIN_MARKET_VOLUME:.0f})")
        if not afterCursor:
            break
    log(f"{tag}: done - {page} pages, {len(events)} events")
    return events


def outcomePair(market: dict[str, Any]) -> tuple[list[str], list[str]] | None:
    try:
        outcomes = json.loads(market["outcomes"]) if isinstance(
            market.get("outcomes"), str) else market.get("outcomes")
        prices = json.loads(market["outcomePrices"]) if isinstance(
            market.get("outcomePrices"), str) else market.get("outcomePrices")
    except (json.JSONDecodeError, TypeError):
        return None
    if (not isinstance(outcomes, list) or not isinstance(prices, list)
            or len(outcomes) != 2 or len(prices) != 2):
        return None
    return ([str(o) for o in outcomes], [str(p) for p in prices])


def gameTsFrom(slug: str, endTs: int | None) -> int | None:
    """Game calendar date embedded in the event slug (modern books), anchored
    at 12:00Z; legacy dateless slugs fall back to endDate−7d (their endDate
    is the game-day noon for those eras)."""
    m = SLUG_GAME_DATE.search(slug or "")
    if m:
        return int(datetime.strptime(m.group(1), "%Y-%m-%d")
                   .replace(tzinfo=UTC, hour=12).timestamp())
    return endTs


def selectMarkets(tag: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One game-outcome moneyline per event (registered §2 scope: dated
    head-to-head, the e23 game_outcome filter): binary team-name outcomes,
    question contains 'vs.', volume >= $50k, listing lead (createdAt chain)
    >= 8d. Market identity: modern-era moneyline has slug == event slug;
    2024-era legacy singles match who-will-win-game-N / trailing -game-N.
    Spread/total/nrfi/1h/inning suffix markets and series/futures events
    are excluded."""
    vsq = re.compile(r"\bvs\.?\b", re.IGNORECASE)
    rows: list[dict[str, Any]] = []
    for ev in events:
        evSlug = str(ev.get("slug") or "")
        cands: list[tuple[tuple, dict[str, Any], list[str]]] = []
        for m in ev.get("markets") or []:
            if not m.get("closed"):
                continue
            pair = outcomePair(m)
            if pair is None:
                continue
            outcomes, prices = pair
            slug = str(m.get("slug") or "")
            question = str(m.get("question") or "")
            if not vsq.search(question):
                continue
            if any(o.lower() in ("yes", "no") for o in outcomes):
                continue
            if SLUG_BANNED.search(slug) or SLUG_SUFFIX.search(slug):
                continue
            if slug != evSlug and not LEGACY_GAME_ML.search(slug):
                continue
            if winnerFrom(outcomes, prices) is None:
                continue
            vol = num(m.get("volumeNum") or m.get("volume"))
            if vol < MIN_MARKET_VOLUME:
                continue
            endTs = parseIsoTs(m.get("endDate"))
            if endTs is None:
                continue
            leadTs = (parseIsoTs(m.get("createdAt")) or parseIsoTs(ev.get("createdAt"))
                      or parseIsoTs(m.get("startDate")))
            gameTs = gameTsFrom(evSlug, endTs)
            if leadTs is None or (gameTs - leadTs) < MIN_DUR_DAYS * 86400:
                continue
            cands.append(((-vol), m, outcomes))
        if not cands:
            continue
        _key, m, outcomes = min(cands, key=lambda c: c[0])
        endTs = parseIsoTs(m.get("endDate"))
        leadTs = (parseIsoTs(m.get("createdAt")) or parseIsoTs(ev.get("createdAt"))
                  or parseIsoTs(m.get("startDate")))
        gameTs = gameTsFrom(str(ev.get("slug") or ""), endTs)
        rows.append({
            "tag": tag,
            "eventSlug": evSlug,
            "marketId": str(m.get("conditionId") or "").lower(),
            "question": m.get("question"),
            "marketSlug": m.get("slug"),
            "outcomes": outcomes,
            "winner": winnerFrom(outcomes, outcomePair(m)[1]),
            "volume": num(m.get("volumeNum") or m.get("volume")),
            "endTs": endTs,
            "gameTs": gameTs,
            "startTs": leadTs,
            "createdAt": leadTs,
        })
    log(f"{tag}: {len(rows)} qualifying game-outcome markets (vol >= "
        f"${MIN_MARKET_VOLUME:.0f}, dur >= {MIN_DUR_DAYS:.0f}d)")
    return rows


def sampleSelection(allRows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic stratified cap toward EVENT_CAP (registered: sort per
    sport, seeded sample PER_SPORT_CAP)."""
    rng = random.Random(SEED)
    out: list[dict[str, Any]] = []
    for tag in TAGS:
        rows = sorted((r for r in allRows if r["tag"] == tag),
                      key=lambda r: (r["eventSlug"], r["marketId"]))
        total = len(rows)
        if total > PER_SPORT_CAP:
            keep = set(rng.sample(range(total), PER_SPORT_CAP))
            rows = [r for i, r in enumerate(rows) if i in keep]
        log(f"{tag}: sampled {len(rows)}/{total}")
        out.extend(rows)
    if len(out) > EVENT_CAP:
        keep = set(rng.sample(range(len(out)), EVENT_CAP))
        out = [r for i, r in enumerate(out) if i in keep]
    log(f"selection: {len(out)} events total")
    return sorted(out, key=lambda r: (r["tag"], r["eventSlug"]))

# -------------------------------------------------------------- fills ---


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


def tradesCachePath(tag: str, marketId: str) -> Path:
    return RAW_DIR / tag / f"trades_{marketId.split('0x')[1][:64]}.json"


def pullTrades(session: HttpSession, tag: str, marketId: str, refresh: bool) -> list[dict[str, Any]]:
    """BUY fills for one market (collectTrades walks the 10k-offset wall
    backward by timestamp, exactly the shipped pipeline's behaviour)."""
    path = tradesCachePath(tag, marketId)
    if path.exists() and path.stat().st_size > 2 and not refresh:
        return json.loads(path.read_text())
    try:
        rows = collectTrades(session.client, marketId, side="BUY")
    except RuntimeError as exc:
        log(f"{tag}: trades pull failed for {marketId[:16]}: {str(exc)[:160]}")
        rows = []
    rows = dedupeFills(rows)
    path.write_text(json.dumps(rows))
    return rows


def tapeSeries(fills: list[dict[str, Any]], outcomes: list[str]) -> list[tuple]:
    """(ts, tokenName, price, size) prints; names normalized to the market's
    outcome vocabulary, off-vocabulary prints dropped."""
    vocab = {str(o).lower(): str(o) for o in outcomes}
    out: list[tuple] = []
    for row in fills:
        token = vocab.get(str(row.get("outcome") or "").lower())
        price = num(row.get("price"))
        size = num(row.get("size"))
        ts = row.get("timestamp")
        if token is None or not (0.0 < price <= 1.0) or size <= 0 or ts is None:
            continue
        out.append((int(ts), token, price, size))
    out.sort()
    return out


def snapshotHorizon(tape: list[tuple], outcomes: list[str], endTs: int, h: int) -> dict[str, Any] | None:
    """Registered extraction: favorite = better pre-T token read (own last
    print in the trailing window, else counter-token's 1-p); primary price =
    that trailing print; their +/-12h size-weighted VWAP beside it."""
    tStar = endTs - h * 86400
    win = [t for t in tape if tStar - WINDOW_SEC <= t[0] <= tStar + WINDOW_SEC]
    if not win:
        return None
    trail = [t for t in tape if tStar - WINDOW_SEC <= t[0] <= tStar]
    lastBy: dict[str, float] = {}
    for _ts, token, price, _size in trail:
        lastBy[token] = price
    reads: dict[str, float] = {}
    for token in {t for _ts, t, _p, _s in tape} | set(outcomes):
        if token in lastBy:
            reads[token] = lastBy[token]
        elif lastBy:
            reads[token] = 1.0 - next(iter(lastBy.values()))
    if not reads or max(reads.values()) <= 0.5:
        return None
    fav = max(reads, key=reads.get)
    favSpace = [price if token == fav else 1.0 - price for _ts, token, price, *_ in win]
    sizes = [t[3] for t in win]
    vwap = (sum(p * s for p, s in zip(favSpace, sizes)) / sum(sizes)) if sum(sizes) else None
    return {
        "horizon": h,
        "tStar": tStar,
        "fav": fav,
        "price": round(reads[fav], 5),
        "ownPrint": fav in lastBy,
        "trailPrints": len(trail),
        "windowPrints": len(win),
        "windowUsd": round(sum(t[3] * (t[2] if t[1] == fav else 1.0 - t[2]) for t in win), 2),
        "maxTradeUsd": round(max(t[3] * t[2] for t in win), 2),
        "vwap": round(vwap, 5) if vwap is not None and len(win) >= MIN_VWAP_PRINTS else None,
    }

# -------------------------------------------------------------- grade ---


def breakEvenWinRate(price: float, feeFlagged: bool) -> float:
    """win rate needed to break even on a $100 copy (50bps exec; fee-marked
    winners redeem at 0.9x)."""
    winProceeds = 100.0 * ((1.0 - WIN_FEE if feeFlagged else 1.0) / price)
    pnlWin = winProceeds - 100 - 100 * EXEC_COST
    pnlLose = -100 - 100 * EXEC_COST
    return -pnlLose / (pnlWin - pnlLose)


def feeAdjustedRet(price: float, won: bool, feeOn: bool) -> float:
    """$100 copy at entry `price`, 50bps exec; fee-marked winners redeem 0.9x."""
    if not won:
        return -100 - 100 * EXEC_COST
    mult = (1.0 - WIN_FEE) if feeOn else 1.0
    return 100.0 * (mult / price) - 100 - 100 * EXEC_COST


def bootstrap(rows: list[dict[str, Any]], retKey: str) -> tuple[float, float, float]:
    """Event-level resample (entrySweep.evaluate idiom: stable-sorted keys
    feed the rng; pnl-mean metric; BOOTS draws; p5 = sorted draws[B/20])."""
    events = sorted(rows, key=lambda r: r["key"])
    rng = random.Random(SEED)
    draws = []
    for _ in range(BOOTS):
        samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
        draws.append(sum(r[retKey] for r in samp) / len(samp))
    draws.sort()
    topTotal = max(events, key=lambda r: r[retKey])[retKey]
    tot = sum(r[retKey] for r in events)
    topShare = topTotal / tot if tot > 0 else 1.0
    return round(draws[BOOTS // 20], 4), round(sum(1 for d in draws
                                                   if d > 0) / len(draws), 4), round(topShare, 4)


def bandTable(rows: list[dict[str, Any]], priceKey: str, retKey: str) -> list[dict[str, Any]]:
    out = []
    for lo, hi in BANDS:
        cell = [r for r in rows if r.get(priceKey) is not None and lo <= r[priceKey] < hi]
        n = len(cell)
        implied = bucketMidLo(lo, hi)
        if n < MIN_CELL:
            out.append({"band": bandLabel((lo, hi)), "n": n, "verdict": "INCON"})
            continue
        winRate = sum(1 for r in cell if r["won"]) / n
        z = (winRate - implied) / (implied * (1 - implied) / n) ** 0.5
        p5, pgt0, topShare = bootstrap(cell, retKey)
        half1 = [r for r in cell if r["endTs"] < int(HALF_SPLIT.timestamp())]
        half2 = [r for r in cell if r["endTs"] >= int(HALF_SPLIT.timestamp())]
        row = {
            "band": bandLabel((lo, hi)), "n": n, "implied": round(implied, 3),
            "winRate": round(winRate, 4), "excess": round(winRate - implied, 4),
            "z": round(z, 2),
            "breakEvenWR": round(breakEvenWinRate(implied, False), 4),
            "meanRet": round(sum(r[retKey] for r in cell) / n, 2),
            "p5": p5, "pGt0": pgt0, "topEventShare": topShare,
            "h1": wrOf(half1, len(half1)), "h2": wrOf(half2, len(half2)),
            "feeShare": round(100 * sum(1 for r in cell if r["feeFlagged"]) / n, 1),
        }
        row["verdict"] = ("PASS" if (n >= MIN_CELL and row["p5"] > 0
                                      and row["pGt0"] >= 0.85 and row["topEventShare"] < 0.60)
                          else "FAIL")
        out.append(row)
    return out


def bucketMidLo(lo: float, hi: float) -> float:
    return lo + (hi - lo) / 2


def wrOf(half: list[dict[str, Any]], n: int) -> float | None:
    return round(sum(1 for r in half if r["won"]) / n, 4) if n else None


def bandRow(table: list[dict[str, Any]], band: tuple[float, float]) -> dict[str, Any] | None:
    return next((r for r in table if r["band"] == bandLabel(band)), None)


def feeNetTable(rows: list[dict[str, Any]], priceKey: str, retKey: str):
    net = [{**r, retKey: feeAdjustedRet(r[priceKey], r["won"], bool(r["feeFlagged"]))}
           for r in rows]
    return bandTable(net, priceKey, retKey)


def computeVerdict(rows: list[dict[str, Any]], prim: list[dict[str, Any]],
                   sec: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    head = bandRow(prim, HEADLINE_BAND) or {}
    headSec = bandRow(sec, HEADLINE_BAND) or {}
    graded = [r for r in prim if r.get("n", 0) >= MIN_CELL]
    headlineExcess = head.get("excess")
    headlineGate = head.get("verdict") == "PASS"
    secExcess = headSec.get("excess")
    secGate = headSec.get("verdict") == "PASS"
    extra = any(r["verdict"] == "PASS" and (r.get("excess") or 0) >= EXCESS_DECAY
                for r in prim if r is not head)
    allPriced = bool(graded) and all(
        (r.get("excess") or 0) <= EXCESS_PRICED for r in graded) and not extra
    if headlineGate and headlineExcess >= EXCESS_GRADUATE and secGate and secExcess >= EXCESS_GRADUATE:
        verdict = "STRONG-PASS"
    elif headlineGate and headlineExcess >= EXCESS_DECAY:
        verdict = "EDGE-EXISTS" if extra else "HEADLINE-PASS"
    elif allPriced:
        verdict = "NO-GO-KILL"
    else:
        verdict = "DECAY-MIXED"
    return verdict, {
        "headlineExcess": headlineExcess, "headlineGate": headlineGate,
        "secondaryExcess": secExcess, "secondaryGate": secGate,
        "gateRow": head, "gradedExcesses": {r["band"]: r.get("excess") for r in graded},
    }

# ------------------------------------------------------------ reporting ---


def rowLine(r: dict[str, Any], fee: bool = False) -> str:
    tagTxt = "[fee-net] " if fee else ""
    extra = f"  fee%={r['feeShare']}" if fee else f"  h1={r['h1']}  h2={r['h2']}"
    shareTxt = "" if fee else f"  topShare={r['topEventShare']:.0%}"
    return (f"  {r['band']}  n={r['n']:>3}  winRate={r['winRate']:.3f}  implied="
            f"{r['implied']:.3f}  excess={r['excess']:+.3f}  z={r['z']:+.2f}  "
            f"beWR={r['breakEvenWR']:.3f}  {tagTxt}ret=${r['meanRet']:+.2f}/100  "
            f"p5={r['p5']:+.2f}  P>0={r['pGt0']:.2f}"
            f"{shareTxt}{extra}  {r['verdict']}")


def sensitivityHorizon(sel: list[dict[str, Any]], feeFlag: dict[str, int], h: int) -> list[dict[str, Any]]:
    rows = []
    for r in sel:
        snap = next((s for s in r.get("snapshots") or [] if s and s["horizon"] == h), None)
        if snap is None:
            continue
        feeOn = int(feeFlag.get(r["marketId"], 0))
        span = r["endTs"] - (r["createdAt"] or r["startTs"] or r["endTs"])
        won = snap["fav"] == r["winner"]
        rows.append({
            "key": f"{r['tag']}:{r['eventSlug']}:{r['marketId'][:10]}",
            "tag": r["tag"], "endTs": r["endTs"], "winner": r["winner"],
            "fav": snap["fav"], "won": won,
            "price": snap["price"], "vwap": snap["vwap"],
            "windowUsd": snap["windowUsd"], "maxTradeUsd": snap["maxTradeUsd"],
            "windowPrints": snap["windowPrints"], "trailPrints": snap["trailPrints"],
            "lifespanDays": span / 86400.0 if span > 0 else None,
            "feeFlagged": feeOn,
            "retTrail": feeAdjustedRet(snap["price"], won, False),
            "retVwap": None if snap["vwap"] is None else feeAdjustedRet(snap["vwap"], won, False),
        })
    return rows


def printTable(title: str, table: list[dict[str, Any]], fee: bool = False) -> None:
    print(f"\n{title}")
    for r in table:
        if r["n"] < MIN_CELL:
            print(f"  {r['band']}  n={r['n']}  INCON")
        else:
            print(rowLine(r, fee=fee))


def main() -> None:
    args = parseArgs()
    client = httpx.Client(timeout=60.0, headers={"User-Agent": "polycrawler2-sportsT7d"})
    session = HttpSession(client, hostRates={gammaHost: RATE, dataApiHost: RATE})

    if not args.grade_only:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        allRows: list[dict[str, Any]] = []
        for tag in TAGS:
            allRows.extend(selectMarkets(tag, keysetEvents(session, tag, args.refresh_crawl)))
        selection = sampleSelection(allRows)
        (RAW_DIR / "selection.json").write_text(json.dumps(selection, indent=1))
        log(f"pulling BUY fills for {len(selection)} markets")
        for i, r in enumerate(selection, 1):
            fills = pullTrades(session, r["tag"], r["marketId"], args.refresh_trades)
            tape = tapeSeries(fills, r["outcomes"])
            r["firstFillTs"] = tape[0][0] if tape else None
            r["fillCount"] = len(fills)
            r["snapshots"] = [snapshotHorizon(tape, r["outcomes"], r.get("gameTs") or r["endTs"], h)
                              for h in HORIZONS]
            if i % 25 == 0:
                log(f"  trades {i}/{len(selection)} ({time.time() - t0:.0f}s)")
        (RAW_DIR / "snapshots.json").write_text(json.dumps(selection, indent=1))
        feeMap = fm.crawlFeeMarks(sorted({r["marketId"] for r in selection}))
        fees = {mid: fm.feeFlag(v) for mid, v in feeMap.items()}
        (RAW_DIR / "fees.json").write_text(json.dumps(fees))
        log(f"fee flags: {sum(fees.values())}/{len(fees)} fee-marked")

    sel = json.loads((RAW_DIR / "snapshots.json").read_text())
    feeFlag = json.loads((RAW_DIR / "fees.json").read_text())
    rows7 = sensitivityHorizon(sel, feeFlag, 7)
    log(f"T-7d rows: {len(rows7)}")
    if len(rows7) < MIN_CELL:
        log("underpowered: T-7d sample < MIN_CELL - INCON, no verdict either way")
        return

    vwapRows = [r for r in rows7 if r["vwap"] is not None]
    prim = bandTable(vwapRows, "vwap", "retVwap")
    trailRows = [r for r in rows7 if r["price"] is not None]
    sec = bandTable(trailRows, "price", "retTrail")
    feeNet = feeNetTable(vwapRows, "vwap", "retVwap")
    verdict, diag = computeVerdict(rows7, prim, sec)

    printTable("\n=== T-7d PRIMARY tape (their +/-12h VWAP, >=3 prints, exec 50bps) ===", prim)
    printTable("\n=== T-7d robustness column (trailing last print in [T-12h, T]) ===", sec)
    printTable("\n=== T-7d fee-net regrade (fee-marked winners redeem*0.9) ===", feeNet,
               fee=True)

    secExcessTxt = (f"{diag['secondaryExcess']:+.3f}"
                    if diag["secondaryExcess"] is not None else "n/a")
    headEx = diag["headlineExcess"]
    headTxt = f"{headEx:+.3f}" if headEx is not None else "INCON"
    print("\n=== VERDICT (mechanical, registered ladder) ===")
    print(f"  headline {bandLabel(HEADLINE_BAND)} excess = "
          f"{headTxt} | gate = {diag['headlineGate']} | "
          f"trailing-print excess = {secExcessTxt} | "
          f"trailing gate = {diag['secondaryGate']}")
    if verdict == "STRONG-PASS":
        print(f"  => STRONG-PASS: excess >= +{EXCESS_GRADUATE:.0%} both tapes; graduate.")
    elif verdict in ("HEADLINE-PASS", "EDGE-EXISTS"):
        print(f"  => {verdict}: edge replicates on our tape.")
    elif verdict == "NO-GO-KILL":
        print("  => NO-GO-KILL: favorites correctly priced on our tape.")
    else:
        print("  => DECAY-MIXED: residual excess present but gate/decay criteria unmet.")

    if verdict != "NO-GO-KILL":
        headRows = [r for r in vwapRows
                    if HEADLINE_BAND[0] <= r["vwap"] < HEADLINE_BAND[1]]
        print("\n  headline-band rows per sport (diagnostic):")
        for tag in TAGS:
            sliceRows = [r for r in headRows if r["tag"] == tag]
            if sliceRows:
                wr = sum(1 for r in sliceRows if r["won"]) / len(sliceRows)
                print(f"    {tag}: n={len(sliceRows)} winRate={wr:.3f} excess={wr - 0.575:+.3f}")
        for h in (14, 5, 3):
            rowsH = sensitivityHorizon(sel, feeFlag, h)
            if len(rowsH) < MIN_CELL:
                print(f"  T-{h}d: n={len(rowsH)} INCON")
                continue
            tab = bandTable(rowsH, "vwap", "retVwap")
            headH = bandRow(tab, HEADLINE_BAND)
            if headH and headH.get("n", 0) >= MIN_CELL:
                print(f"  T-{h}d {bandLabel(HEADLINE_BAND)}: n={headH['n']} "
                      f"excess={headH['excess']:+.3f} z={headH['z']:+.2f} "
                      f"p5={headH['p5']:+.2f} {headH['verdict']}")
            else:
                print(f"  T-{h}d: headline band n<20 INCON")

    grade = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "primaryVwap": prim, "trailingSecondary": sec, "feeNet": feeNet,
        "verdict": verdict, **{k: v for k, v in diag.items() if k != "gateRow"},
    }
    (RAW_DIR / "grade.json").write_text(json.dumps(grade, indent=1))
    log(f"grade written to {RAW_DIR / 'grade.json'}")


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-crawl", action="store_true")
    parser.add_argument("--refresh-trades", action="store_true")
    parser.add_argument("--grade-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
