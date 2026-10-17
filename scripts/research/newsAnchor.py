"""News-anchor test on the shipped military fresh-big-bet rule (#3 in
research/ideasResearch.md): are the profitable signals "genuinely informed"
(trades BEFORE first public news on the topic) or "news chasers" (after)?

Method:
  1. Reproduce the shipped cell exactly via the militarySweep.py code path
     (fresh <=5d, <=3 markets, burst >= $5k, tape price <= 0.35, military
     slug keywords; retReal = next taker price within 5 min).
  2. For each event in the signal set, query GDELT DOC 2.0 (free, no key)
     for the FIRST article matching the event's topic phrases inside a
     window [firstSignal-30d, resolution+1d], sorted ascending. The first
     article's GDELT `seendate` (15-min resolution) is the per-event
     firstNewsTs anchor. Responses are cached to data/raw/gdelt/ (read-only
     GETs only, ~1 request per event, rate-limited via polycrawler.http).
     Anchor quality is logged per event: "truncated" means the first match
     sits within 12h of the window start, i.e. the topic was already being
     covered before the window opened (anchor is a lower bound on true
     first-news time) — this biases the split AGAINST the pre-news
     hypothesis, which is the safe direction for a promotion decision.
  3. Split signals: pre-news = ts < firstNewsTs + 2h grace; post-news =
     otherwise. Events with no anchor are reported but excluded from the
     split. Per subset: n, win rate, mean ret (insider price), mean retReal
     (realistic fill), and the same event-level bootstrap as
     militaryCategory.py/militarySweep.py (2000 resamples over events,
     seed 7) for P(>0).

Decision rule (research/ideasResearch.md #3): promote "no breaking news in
last N hours" as a live gate candidate only if pre-news n >= ~150 AND
P(>0) >= 95%.

Run:  uv run python scripts/research/newsAnchor.py
      uv run python scripts/research/newsAnchor.py --skip-network   (cache only)
"""

import argparse
import hashlib
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import polars as pl
from polycrawler.http import HttpSession

t0 = time.time()
MILITARY = ("iran", "israel", "hezbollah", "houthi", "lebanon", "hamas", "gaza",
            "ukraine", "russia", "taiwan", "pakistan-military", "maduro", "venezuela", "nato")
FILL_WINDOW_SEC = 300

GRACE = timedelta(hours=2)          # signal counts as pre-news if ts < firstNews + grace
LOOKBACK = timedelta(days=30)       # news search starts this long before the first signal
TAIL = timedelta(days=1)            # ... and ends this long after resolution
MAXWIN = timedelta(days=89)         # GDELT artlist sanity cap (~3 months)
TRUNCATED = timedelta(hours=12)     # anchor this close to window start => pre-existing coverage
GDELT_HOST = "api.gdeltproject.org"
GDELT_RATE = 1 / 15                 # requests/sec — GDELT docs say one per 5s, but its 429
                                    # penalty escalates when paced at the limit (observed);
                                    # 15s spacing + one retry pass stays well clear.
BOOT_N = 2000
MID = datetime(2025, 6, 1, tzinfo=timezone.utc)

# Event topic -> GDELT query terms (space-joined = AND, per probe: "Kupiansk
# Zzzzqqq" returns 0 articles; OR blocks are the only explicit OR). Exact
# phrases in quotes are used where a verbatim headline phrase exists ("US
# strikes Iran") because loose ANDs match multi-country digest articles;
# GDELT rejects quoted phrases shorter than ~6 chars, so short single words
# stay bare. Keyed by slug substring, first match wins (specific keys first);
# unmapped events fall back to generic slug-token derivation.
GDELT_QUERIES: list[tuple[str, list[str]]] = [
    ("israel-invade-lebanon", ["Israel", "invasion", "Lebanon"]),
    ("israel-strike-on-iranian-nuclear", ["Israel", '"Iranian nuclear"']),
    ("israel-invade-syria", ["Israel", "invasion", "Syria"]),
    ("russia-x-ukraine-ceasefire", ["Russia", "Ukraine", "ceasefire"]),
    ("israel-x-hezbollah-ceasefire", ['"Hezbollah ceasefire"']),
    ("israel-x-hamas-ceasefire", ['"Hamas ceasefire"']),
    ("zelenskyy-out", ["Zelensky", "Ukraine", "president"]),
    ("kupiansk", ["Kupiansk"]),
    ("kostyantynivka", ["Kostyantynivka"]),
    ("pokrovsk", ["Pokrovsk"]),
    ("maduro-out", ["Maduro", "Venezuela"]),
    ("invade-venezuela", ["Venezuela", "invade"]),
    ("us-strikes-iran", ['"US strikes Iran"']),
    ("usisrael-strikes-iran", ['"US strikes Iran"']),
    ("israel-strikes-iran", ['"Israel strikes Iran"']),
    ("khamenei-out", ["Khamenei"]),
    ("iranian-regime-fall", ['"Iranian regime"']),
    ("china-invade-taiwan", ["China", "Taiwan", "invasion"]),
    ("us-x-iran-permanent-peace", ['"peace deal"', '"United States"', "Iran"]),
    ("us-x-iran-ceasefire-extended", ['"Iran ceasefire"', "extended"]),
    ("us-x-iran-ceasefire", ['"Iran ceasefire"', '"United States"']),
]
STOPWORDS = {"in", "by", "the", "of", "on", "will", "x", "as", "before",
             "january", "february", "march", "april", "may", "june", "july",
             "august", "september", "october", "november", "december"}


def phrasesFor(slug: str) -> list[str]:
    for key, phrases in GDELT_QUERIES:
        if key in slug:
            return phrases
    tokens = [t for t in slug.replace("-", " ").split()
              if t not in STOPWORDS and not t.isdigit()]
    return tokens or [slug]


def queryFor(slug: str) -> str:
    return " ".join(phrasesFor(slug))


def parseSeen(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- 1. signals
def buildSignals() -> pl.DataFrame:
    dirs = ["data", "data/universe"]
    markets = (pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
               .unique("marketId", keep="last")
               .select("marketId", "eventSlug", "winner",
                       pl.coalesce("resolvedAt", "endDate").alias("resolvedAt")))
    milSlugs = {s for s in markets["eventSlug"].unique().to_list()
                if any(k in (s or "").lower() for k in MILITARY)}
    markets = markets.with_columns(isMilitary=pl.col("eventSlug").is_in(list(milSlugs)))

    cols = ["ts", "account", "marketId", "outcome", "side", "size", "price"]
    lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet").select(cols) for d in dirs])
    firstSeen = lazy.group_by("account").agg(firstTs=pl.col("ts").min()).collect()
    entries = (lazy.filter(pl.col("side") == "BUY").drop("side")
               .sort("account", "marketId", "outcome", "ts")
               .with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome")
                                    .fill_null(pl.duration(days=1)) > pl.duration(minutes=10))
                             .cum_sum().over("account", "marketId", "outcome"))
               .group_by("account", "marketId", "outcome", "burst")
               .agg(ts=pl.col("ts").min(), usd=(pl.col("size") * pl.col("price")).sum(),
                    shares=pl.col("size").sum())
               .with_columns(price=pl.col("usd") / pl.col("shares"))
               .drop("burst", "shares")
               .collect())
    entries = (entries.join(markets, on="marketId").join(firstSeen, on="account").sort("account", "ts")
               .with_columns(marketsSoFar=pl.col("marketId").is_first_distinct().cast(pl.Int32)
                             .cum_sum().over("account"),
                             ageDays=(pl.col("ts") - pl.col("firstTs")).dt.total_seconds() / 86400,
                             won=pl.col("outcome") == pl.col("winner"),
                             ret=pl.when(pl.col("winner").is_null()).then(None)
                             .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("price") - 1)
                             .otherwise(-1.0))
               .filter(pl.col("ret").is_not_null()))
    # realistic fill: next taker price in the same (market,outcome) within 5 min
    tape = (lazy.filter(pl.col("side") == "BUY")
            .select("ts", "marketId", "outcome", "price").sort("marketId", "outcome", "ts").collect())
    tape = (tape.with_columns(
        nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"),
        nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"),
    ).with_columns(
        fillPrice=pl.when((pl.col("nextTs") - pl.col("ts")).dt.total_seconds() <= FILL_WINDOW_SEC)
        .then(pl.col("nextPrice")).otherwise(pl.col("price")),
    )
        .unique(subset=["ts", "marketId", "outcome"], keep="last"))
    entries = (entries.drop("price")
               .join(tape.select("ts", "marketId", "outcome", "price", "fillPrice"),
                     on=["ts", "marketId", "outcome"], how="left")
               .with_columns(
                   retReal=pl.when(pl.col("winner").is_null()).then(None)
                   .when(pl.col("outcome") == pl.col("winner")).then(1 / pl.col("fillPrice") - 1)
                   .otherwise(-1.0)))
    print(f"entries {entries.height} ({time.time()-t0:.0f}s)", flush=True)
    # shipped cell (militarySweep.py: minUsd 5k x maxPx 0.35 x age 5), price here
    # is the tape price at the entry ts (post-join), exactly as in the sweep.
    sig = (entries.filter(pl.col("isMilitary") & (pl.col("marketsSoFar") <= 3)
                          & (pl.col("usd") >= 5000) & (pl.col("price") <= 0.35)
                          & (pl.col("ageDays") <= 5)))
    print(f"shipped-cell signals {sig.height}")
    return sig


# ---------------------------------------------------------------- 2. anchors
def gdeltWindow(slug: str, firstSig: datetime, resolved: datetime) -> tuple[datetime, datetime]:
    end = resolved + TAIL
    start = max(firstSig - LOOKBACK, end - MAXWIN)  # 89d cap: GDELT artlist window sanity
    return start, end


def anchorEvents(sig: pl.DataFrame, skipNetwork: bool) -> pl.DataFrame:
    evs = (sig.group_by("eventSlug")
           .agg(firstSig=pl.col("ts").min(), resolved=pl.col("resolvedAt").max(), n=pl.len())
           .sort("firstSig"))

    def cacheKeyFor(slug: str, start: datetime, end: datetime, q: str) -> str:
        # query hash included so a changed query never reads a stale cache entry
        qh = hashlib.md5(q.encode()).hexdigest()[:10]
        return f"artlist_{slug}_{start:%Y%m%d%H%M%S}_{end:%Y%m%d%H%M%S}_{qh}"

    session = None
    if not skipNetwork:
        client = httpx.Client(timeout=60.0, headers={"User-Agent": "polycrawler2-research/0.2 (news anchor backtest; read-only)"})
        # GDELT 429 penalties decay slowly — a bounded retry budget per event
        session = HttpSession(client, hostRates={GDELT_HOST: GDELT_RATE}, dataDir="data",
                              maxAttempts=6, connectCap=30.0)

    def anchorOne(ev: dict) -> dict:
        slug = ev["eventSlug"]
        start, end = gdeltWindow(slug, ev["firstSig"], ev["resolved"])
        q = queryFor(slug)
        key = cacheKeyFor(slug, start, end, q)
        row = {"eventSlug": slug, "n": ev["n"], "query": q,
               "winStart": start, "winEnd": end, "firstNews": None,
               "firstTitle": None, "firstDomain": None, "quality": "error", "note": ""}
        try:
            if session is None and skipNetwork:
                # cache-only mode: read the cached file directly, no request path
                from polycrawler.http import cachePath
                p = cachePath("data", "gdelt", key)
                if not p.exists():
                    row["quality"] = "no-cache"
                    return row
                import json
                payload = json.loads(p.read_text())
            else:
                payload = session.getJson(
                    "https://api.gdeltproject.org/api/v2/doc/doc",
                    params={"query": q, "mode": "artlist", "format": "json",
                            "sort": "dateasc", "maxrecords": 5,
                            "startdatetime": f"{start:%Y%m%d%H%M%S}",
                            "enddatetime": f"{end:%Y%m%d%H%M%S}"},
                    cacheKind="gdelt", cacheKey=key)
            arts = (payload or {}).get("articles") or []
            if not arts:
                row["quality"] = "miss"
            else:
                first = arts[0]
                ts = parseSeen(first.get("seendate"))
                if ts is None:
                    row["quality"] = "bad-date"
                else:
                    row["firstNews"] = ts
                    row["firstTitle"] = (first.get("title") or "")[:120]
                    row["firstDomain"] = first.get("domain")
                    row["quality"] = "truncated" if ts - start < TRUNCATED else "ok"
                    if row["quality"] == "truncated":
                        row["note"] = "topic already covered at window start (anchor = lower bound)"
        except Exception as exc:  # per-event isolation: one bad query must not kill the run
            row["quality"] = "error"
            row["note"] = str(exc)[:200]
        return row

    rows = [anchorOne(ev) for ev in evs.iter_rows(named=True)]
    for r in rows:
        print(f"  anchor {r['quality']:>9} n={r['n']:>3} {r['eventSlug'][:52]:52s} q={r['query'][:60]}", flush=True)
    # one bounded retry pass for transient (429/timeout) failures — the cache
    # makes every successful event free on this pass
    retryable = [ev for ev, r in zip(evs.iter_rows(named=True), rows) if r["quality"] == "error"]
    for ev in retryable:
        r = anchorOne(ev)
        if r["quality"] != "error":
            rows[rows.index(next(x for x in rows if x["eventSlug"] == ev["eventSlug"]))] = r
        print(f"  retry   {r['quality']:>9} n={r['n']:>3} {ev['eventSlug'][:52]}", flush=True)
    if session is not None:
        print(f"gdelt requests={session.stats.calls.get(GDELT_HOST, 0)} "
              f"cacheHits={session.stats.cacheHits.get(GDELT_HOST, 0)}")
        client.close()
    else:
        print("gdelt requests=0 (cache-only)")
    return pl.DataFrame(rows).with_columns(
        pl.col("winStart", "winEnd", "firstNews").cast(pl.Datetime("us", "UTC")))


# ---------------------------------------------------------------- 3. split + stats
def bootP(df: pl.DataFrame, rng: random.Random, col: str = "retReal") -> tuple[float, float, float]:
    """Event-level bootstrap, same method as militaryCategory.report()."""
    ev = (df.group_by("eventSlug").agg(pnl=(pl.col(col) * 100).sum(), cap=pl.len() * 100.0)
          .with_columns(r=pl.col("pnl") / pl.col("cap")))
    events = list(ev.iter_rows(named=True))
    boots = []
    for _ in range(BOOT_N):
        samp = [events[rng.randrange(len(events))] for _ in range(len(events))]
        boots.append(sum(e["pnl"] for e in samp) / sum(e["cap"] for e in samp))
    boots.sort()
    return boots[100], boots[1899], sum(1 for b in boots if b > 0) / len(boots)


def _r(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(v, nd)


def subsetRow(name: str, df: pl.DataFrame, rng: random.Random) -> dict:
    if df.height == 0:
        return {"subset": name, "n": 0, "events": 0, "winRate": None, "ret": None,
                "retReal": None, "boot p5": None, "boot p95": None, "P(>0)": None,
                "H1": None, "H2": None}
    p5, p95, ppos = bootP(df, rng)
    retReal = df["retReal"].mean()
    return {"subset": name, "n": df.height, "events": df["eventSlug"].n_unique(),
            "winRate": _r(df["won"].mean()), "ret": _r(df["ret"].mean()),
            "retReal": _r(retReal),
            "boot p5": _r(p5), "boot p95": _r(p95),
            "P(>0)": f"{ppos:.0%}",
            "H1": _r(df.filter(pl.col("ts") < MID)["retReal"].mean()),
            "H2": _r(df.filter(pl.col("ts") >= MID)["retReal"].mean())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-network", action="store_true",
                    help="use only cached GDELT responses under data/raw/gdelt/")
    ap.add_argument("--csv", default="data/research/newsAnchorSignals.csv")
    ap.add_argument("--md", default="research/newsAnchor.md")
    args = ap.parse_args()

    sig = buildSignals()
    rng = random.Random(7)
    anchors = anchorEvents(sig, args.skip_network)

    sig = (sig.join(anchors.select("eventSlug", "firstNews", "quality"), on="eventSlug", how="left")
           .with_columns(isPreNews=pl.when(pl.col("firstNews").is_null()).then(None)
                         .when(pl.col("ts") < pl.col("firstNews") + GRACE).then(True)
                         .otherwise(False)))

    # CSV of signals with isPreNews
    out = sig.select(
        "ts", "account", "marketId", "eventSlug", "outcome", "usd", "price",
        "fillPrice", "ret", "retReal", "won", "resolvedAt", "firstNews", "quality",
        pl.col("isPreNews").cast(pl.Utf8).alias("isPreNews")).sort("ts")
    out.write_csv(args.csv)
    print(f"wrote {args.csv} ({out.height} signals)")

    # splits (grace sensitivity at 0h / 2h / 12h)
    anchored = sig.filter(pl.col("firstNews").is_not_null())
    print(f"\nanchor coverage: {anchors.filter(pl.col('quality').is_in(['ok', 'truncated'])).height}"
          f"/{anchors.height} events, "
          f"{anchored.height}/{sig.height} signals")
    rows = []
    for grace, label in ((timedelta(0), "grace 0h"), (GRACE, "grace 2h (shipped)"),
                         (timedelta(hours=12), "grace 12h")):
        pre = anchored.filter(pl.col("ts") < pl.col("firstNews") + grace)
        post = anchored.filter(pl.col("ts") >= pl.col("firstNews") + grace)
        rows.append(subsetRow(f"pre-news  {label}", pre, rng))
        rows.append(subsetRow(f"post-news {label}", post, rng))
    rows.append(subsetRow("unanchored events", sig.filter(pl.col("firstNews").is_null()), rng))
    rows.append(subsetRow("all shipped-cell signals", sig, rng))
    rpt = pl.DataFrame(rows)
    with pl.Config(tbl_rows=-1, fmt_str_lengths=40):
        print(rpt)

    # per-event anchor table for the md
    evTable = (anchors.join(sig.group_by("eventSlug").agg(
        preN=pl.col("isPreNews").sum(), firstSig=pl.col("ts").min()), on="eventSlug", how="left")
        .with_columns(pl.col("preN").fill_null(0).cast(pl.Int32))
        .sort("firstSig"))

    # mechanical decision rule (research/ideasResearch.md #3)
    pre2h = anchored.filter(pl.col("ts") < pl.col("firstNews") + GRACE)
    post2h = anchored.filter(pl.col("ts") >= pl.col("firstNews") + GRACE)
    pPre = subsetRow("pre", pre2h, rng)
    pPost = subsetRow("post", post2h, rng)
    preN, preP = pPre["n"], pPre["P(>0)"]
    okN = preN is not None and preN >= 150
    okP = preP is not None and int(preP.rstrip("%")) >= 95
    if okN and okP:
        verdict = "PROMOTE as live gate candidate (pre-news n>=150 and P(>0)>=95%)"
    elif preN is None or preN < 150:
        verdict = (f"DO NOT PROMOTE yet — pre-news n={preN} < 150 "
                   f"(anchor coverage is the binding constraint; report honestly)")
    else:
        verdict = f"DO NOT PROMOTE — pre-news P(>0)={preP} < 95%"

    nOk = anchors.filter(pl.col("quality").is_in(["ok", "truncated"])).height
    nTrunc = anchors.filter(pl.col("quality") == "truncated").height
    lines = [
        "# News-anchor test on the shipped military rule (pre-news vs news-chasers)",
        "",
        f"Script: `scripts/research/newsAnchor.py` (run {datetime.now(timezone.utc):%Y-%m-%d %H:%M}Z).",
        "Companion to `research/ideasResearch.md` #3 and `research/militaryCategory.md`.",
        "",
        "## Method",
        "",
        "1. Reproduces the shipped cell via the `militarySweep.py` code path (fresh <=5d,",
        "   <=3 markets, burst >= $5k, tape price <= 0.35, military slug keywords;",
        f"   realistic fill = next taker price within 5 min). Rebuilt n={sig.height} signals "
        f"across {anchors.height} events (shipped docs report 425-428; runs vary by +-1-3 on "
        "   a float-tie at the exact $5k burst boundary — parallel float summation order).",
        "2. Per event, GDELT DOC 2.0 artlist (free, no key), space-joined keywords = AND",
        "   (verified by probe: real+nonsense word pair returns 0 articles), sorted",
        "   ascending within a window [firstSignal-30d, resolution+1d, capped 89d].",
        "   The FIRST matching article's `seendate` (15-min resolution) is the",
        "   per-event firstNewsTs anchor. Responses cached to `data/raw/gdelt/`",
        "   (read-only GETs, one request per event, 15s spacing + one bounded",
        "   retry pass for transient 429/timeout failures).",
        "3. Split: pre-news = signal ts < firstNewsTs + 2h grace; post-news otherwise.",
        "   Event-level bootstrap (2000 resamples, seed 7) on retReal, same method as",
        "   `militaryCategory.py`.",
        "",
        "**Bias note:** anchors are built to fail conservative. A `truncated` quality flag",
        "means the topic was already covered when the search window opens, so the anchor",
        "is a LOWER bound on true first-news time and some genuinely pre-news signals are",
        "misfiled as post-news. This biases AGAINST the pre-news hypothesis — the safe",
        "direction for a promotion decision.",
        "",
        f"## Anchor coverage: {nOk}/{anchors.height} events, {anchored.height}/{sig.height} signals",
        "",
        f"({nTrunc} events truncated: pre-existing topic coverage at window start; "
        f"{anchors.height - nOk} without an anchor)",
        "",
        "| event | n | pre(2h) | anchor quality | firstNews (UTC) | first article | query |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for r in evTable.iter_rows(named=True):
        fn = f"{r['firstNews']:%Y-%m-%d %H:%M}" if r["firstNews"] is not None else "-"
        title = (r["firstTitle"] or "-").replace("|", "/")[:60]
        lines.append(f"| {r['eventSlug']} | {r['n']} | {r['preN']} | {r['quality']} "
                     f"| {fn} | {title} | `{r['query']}` |")
    lines += [
        "",
        "## Pre-news vs post-news (grace sensitivity)",
        "",
        "| subset | n | events | win% | ret | retReal | boot p5 | boot p95 | P(>0) | H1 | H2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        f = lambda v: "-" if v is None else (f"{v}" if isinstance(v, str) else f"{v:+.3f}")
        wr = "-" if r["winRate"] is None else f"{r['winRate']:.0%}"
        lines.append(f"| {r['subset']} | {r['n']} | {r['events']} | {wr} "
                     f"| {f(r['ret'])} | {f(r['retReal'])} | {f(r['boot p5'])} | {f(r['boot p95'])} "
                     f"| {f(r['P(>0)'])} | {f(r['H1'])} | {f(r['H2'])} |")
    lines += [
        "",
        "ret = insider's own price (upper bound); retReal = next-taker-price within 5 min",
        "(realistic fill, the shipped-cell convention). H1/H2 = mean retReal before/after",
        "2025-06-01.",
        "",
        f"## Decision rule: {verdict}",
        "",
        "Signals CSV: `data/research/newsAnchorSignals.csv` (one row per shipped-cell signal,",
        "with isPreNews / firstNewsTs / anchor quality).",
        "",
    ]
    Path(args.md).write_text("\n".join(lines))
    print(f"wrote {args.md}")


if __name__ == "__main__":
    main()
