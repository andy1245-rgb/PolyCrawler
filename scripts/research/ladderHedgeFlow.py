"""If-jump evaluation #3 (ideaGenAlpha.md family (d) / candidate #3):
negRisk date-ladder hedge-flow second wave.

Pre-registered in research/ladderHedgeFlow.md BEFORE any data access; this
script implements the locked spec:

  group rule      stems = eventSlug shared by >=3 markets; the military
                  slug-keyword subset is the trigger universe; negRisk identity
                  from cached + fresh CLOB pulls (feeMarkRegrade shooter
                  pattern), annotation only
  trigger burst   per (account, marketId, outcome) 10-minute-gapped burst
                  windows of BUY fills (entrySweep segmentation verbatim),
                  cumulative USD crossing $10k primary / $5k secondary prior;
                  t0 = the fill where cumulative first crosses X; n capped at
                  200 per lane (seed 7, uniform sample of the full census
                  sorted by t0)
  event           a >=$X burst (qualified by total burst USD) whose burst
                  starts in (t0, t0+W], on a DIFFERENT rung of the same stem,
                  account != trigger account; W in 10m/1h/6h/24h
  controls        C1: 5 other-stem military ladder rungs per trigger, same
                  timestamps (cross-stem concurrency baseline);
                  C2: 5 non-ladder military markets per trigger (same and a
                  volume-matched sensitivity pool)
  hedge lanes     H1 same-rung opposite-side prints >=$1k, H2 cross-rung
                  prints >=$1k, all account != trigger, within (t0, t0+6h];
                  witness = H1 or H2 (gate >= 30%)
  drift           reacting rung Yes-equivalent price p0 -> T+1h / T+1d
                  (fills tape, no book snapshots), reported in the direction
                  the reacting burst bought
  gates           G1 reaction rate > both controls, two-proportion z, raw
                  p < 0.0025 (0.01 Bonferroni x4 across W per X), n >= 100;
                  G2 hedge witness >= 30%; G3 median drift >= +1%
                  -> REAL / PRE-EXISTING / ABSENT / INCONCLUSIVE(n<100)

Run: uv run python scripts/research/ladderHedgeFlow.py 2>&1 \
        | tee logs/ladderHedgeFlow.log
"""

import importlib.util
import json
import math
import random
import sys
import time
from bisect import bisect_right
from collections import Counter
from pathlib import Path

import polars as pl

t0wall = time.time()
ROOT = Path(__file__).resolve().parents[2]
DIRS = ["data", "data/universe", "data/oos", "data/oosExpansion"]
OUT = ROOT / "data" / "research" / "ladderHedgeFlow"

SEED = 7
N_CAP = 200
LANES = {"10k": 10_000.0, "5k": 5_000.0}  # primary first per pre-registration
WINDOWS = {"10m": 600, "1h": 3_600, "6h": 21_600, "24h": 86_400}
HEDGE_W = 21_600  # 6h primary per pre-registration
HEDGE_USD = 1_000.0
CTRL_N = 5
BONF_RAW_P = 0.0025  # doc: 0.01 Bonferroni x4 across W per X


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "research" / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


researchData = _load("researchData", "researchData.py")
feeMark = _load("feeMarkRegrade", "feeMarkRegrade.py")


def log(msg: str) -> None:
    print(msg, flush=True)


def ztest(k1: int, n1: int, k0: int, n0: int) -> float:
    """Two-sided p of the two-proportion z test."""
    if n1 == 0 or n0 == 0:
        return 1.0
    p1, p0 = k1 / n1, k0 / n0
    p = (k1 + k0) / (n1 + n0)
    se = math.sqrt(max(p * (1 - p) * (1 / n1 + 1 / n0), 1e-18))
    z = (p1 - p0) / se
    return max(min(1.0, math.erfc(abs(z) / math.sqrt(2))), 0.0)


# ------------------------------------------------------------------ frames --
markets = pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in DIRS],
                    how="diagonal_relaxed").unique(subset=["marketId"], keep="last")
ladderSlugs = set(markets.group_by("eventSlug").agg(rungs=pl.len())
                  .filter(pl.col("rungs") >= 3)["eventSlug"])
markets = markets.with_columns(
    isMil=pl.col("eventSlug").map_elements(researchData.isMilitarySlug, return_dtype=bool),
    isLadder=pl.col("eventSlug").is_in(pl.lit(sorted(ladderSlugs))))
milLadder = markets.filter(pl.col("isMil") & pl.col("isLadder"))
milOther = markets.filter(pl.col("isMil") & ~pl.col("isLadder"))
log(f"[setup] markets: {markets.height:,} unique | ladder stems: {len(ladderSlugs):,} | "
    f"military ladder rungs: {milLadder.height:,} | military non-ladder: {milOther.height:,}")
log("[setup] top military ladder stems by rung count:")
for r in (milLadder.group_by("eventSlug").agg(rungs=pl.len())
          .sort("rungs", descending=True).head(8).to_dicts()):
    log(f"         {r['eventSlug']:46s} rungs={r['rungs']}")

# negRisk annotation: cached + fresh CLOB pulls, feeMarkRegrade shooter pattern
milLadderIds = sorted(milLadder["marketId"])
cached = {p.stem.replace("clob__", "") for p in
          (ROOT / "data" / "raw" / "feeMarkRegrade").glob("clob__*.json")}
missing = [m for m in milLadderIds if m not in cached]
log(f"[negRisk] cached CLOB pulls cover {len(milLadderIds) - len(missing)}/"
    f"{len(milLadderIds)} military ladder rungs; crawling {len(missing)}")
if missing:
    try:
        feeMark.crawlFeeMarks(missing)
        log(f"[negRisk] crawl ok -> all {len(milLadderIds)} military ladder rungs annotated")
    except (OSError, ValueError, RuntimeError) as exc:
        log(f"[negRisk] crawl FAILED ({exc!r}) - proceeding on cached coverage "
            f"(pre-registered: annotation, not grouping)")
negRiskMap: dict[str, bool] = {}
for mid in milLadderIds:
    p = ROOT / "data" / "raw" / "feeMarkRegrade" / f"clob__{mid}.json"
    if p.exists():
        d = json.loads(p.read_text())
        if "neg_risk" in d:
            negRiskMap[mid] = bool(d["neg_risk"])
nn = [negRiskMap.get(m) for m in milLadderIds]
known = [v for v in nn if v is not None]
log(f"[negRisk] neg_risk=true on {sum(known)}/{len(known)} "
    f"({100 * sum(known) / max(len(known), 1):.1f}%) of annotated military ladder "
    f"rungs; {len(nn) - len(known)} unknown")

# ------------------------------------------------------------------- bursts --
buy = (pl.concat([pl.scan_parquet(f"{d}/fills.parquet") for d in DIRS],
                 how="diagonal_relaxed")
       .filter(pl.col("side") == "BUY")
       .select("ts", "account", "marketId", "outcome",
               usd=(pl.col("size") * pl.col("price")))
       .sort("account", "marketId", "outcome", "ts")
       .with_columns(
           burstIdx=(pl.col("ts").diff().over("account", "marketId", "outcome")
                     .fill_null(pl.duration(days=1)) > pl.duration(minutes=10))
           .cum_sum().over("account", "marketId", "outcome"))
       .with_columns(cum=pl.col("usd").cum_sum()
                     .over("account", "marketId", "outcome", "burstIdx")))
burst = (buy.group_by("account", "marketId", "outcome", "burstIdx")
         .agg(tMin=pl.col("ts").min(),
              t5=pl.when(pl.col("cum") >= 5_000).then(pl.col("ts")).min(),
              t10=pl.when(pl.col("cum") >= 10_000).then(pl.col("ts")).min(),
              usd=pl.col("cum").max())
         .collect())
log(f"[bursts] {burst.height:,} 10-min burst windows scanned "
    f"(t={time.time() - t0wall:.0f}s)")

slugOf = dict(zip(markets["marketId"].to_list(), markets["eventSlug"].to_list()))
stems = sorted(set(milLadder["eventSlug"].to_list()))
sidOf = {s: i for i, s in enumerate(stems)}
midToSid = {m: sidOf[s] for m, s in zip(milLadder["marketId"].to_list(),
                                        milLadder["eventSlug"].to_list())}


def qualified(x: float) -> pl.DataFrame:
    """Bursts on military markets whose cumulative crossed >= x, carrying the
    burst start (tMin) and the x-crossing instant (tX)."""
    tx = "t5" if x == 5_000.0 else "t10"
    return (burst.filter(pl.col("usd") >= x)
            .join(markets.filter(pl.col("isMil")).select("marketId"), on="marketId")
            .with_columns(sid=pl.col("marketId")
                          .map_elements(lambda m: sidOf.get(slugOf.get(m, ""), -1),
                                        return_dtype=pl.Int32))
            .select("account", "marketId", "outcome", "sid", "usd",
                    tMinUs=pl.col("tMin").cast(pl.Datetime("us")).cast(pl.Int64),
                    tX=pl.col(tx).cast(pl.Datetime("us")).cast(pl.Int64)))


# --------------------------------------------- cross-stem concurrency census --
# pre-specified sanity bound vs C1: military ladder >=$10k bursts, how often
# another stem's burst starts within W (no account/state filters at all)
lb = (qualified(10_000.0).filter(pl.col("sid") >= 0).sort("tMinUs"))
lbT: list[int] = [t // 1_000_000 for t in lb["tMinUs"].to_list()]
lbS: list[int] = lb["sid"].to_list()
census = {}
for wName, w in WINDOWS.items():
    c = 0
    for i, t in enumerate(lbT):
        if any(s != lbS[i] for s in lbS[i + 1:bisect_right(lbT, t + w)]):
            c += 1
    census[wName] = c
log("[census] cross-stem concurrency, military ladder >=$10k bursts "
    f"(n={lb.height:,}): " + ", ".join(f"{w}: {100 * c / max(lb.height, 1):.1f}%"
                                       for w, c in census.items()))

# ----------------------------------------------------------- price/big-print --
# Yes-equivalent price tape and >=$1k print tape, military ladder rungs only
tapes = (pl.concat([pl.scan_parquet(f"{d}/fills.parquet") for d in DIRS],
                   how="diagonal_relaxed")
         .select("ts", "marketId", "account", "outcome", "side", "price",
                 usd=(pl.col("size") * pl.col("price")))
         .join(pl.LazyFrame({"marketId": milLadderIds}), on="marketId", how="semi")
         .with_columns(yesP=pl.when(pl.col("outcome") == "Yes")
                       .then(pl.col("price")).otherwise(1.0 - pl.col("price")))
         .collect())
log(f"[tapes] {tapes.height:,} fills on military ladder rungs "
    f"(t={time.time() - t0wall:.0f}s)")

printTape = tapes.filter(pl.col("usd") >= HEDGE_USD).select(
    "ts", "marketId", "account", "outcome", "side", "usd")
log(f"[tapes] {printTape.height:,} prints >=${HEDGE_USD:.0f} on military ladder rungs")

# per-market sorted print lists for the hedge lanes
printIdx: dict[str, dict[str, list]] = {}
for key, sub in printTape.partition_by("marketId", as_dict=True).items():
    mid = key[0] if isinstance(key, tuple) else key
    s = sub.sort("ts")
    printIdx[mid] = {
        "t": [t // 1_000_000 for t in s["ts"].cast(pl.Datetime("us")).cast(pl.Int64).to_list()],
        "acc": s["account"].to_list(),
        "out": s["outcome"].to_list(),
        "side": s["side"].to_list(),
        "usd": s["usd"].to_list()}

# per-market sorted Yes-equivalent price series for the drift lane
priceIdx: dict[str, tuple[list[int], list[float]]] = {}
for key, sub in tapes.partition_by("marketId", as_dict=True).items():
    mid = key[0] if isinstance(key, tuple) else key
    s = sub.sort("ts")
    priceIdx[mid] = ([t // 1_000_000
                      for t in s["ts"].cast(pl.Datetime("us")).cast(pl.Int64).to_list()],
                     s["yesP"].to_list())
log(f"[tapes] per-market series built: {len(priceIdx):,} price tapes, "
    f"{len(printIdx):,} print tapes (t={time.time() - t0wall:.0f}s)")


def lastAt(mid: str, t: int) -> float | None:
    """Last Yes-equivalent traded price on mid at or before t."""
    p = priceIdx.get(mid)
    if p is None:
        return None
    idx = bisect_right(p[0], t) - 1
    return float(p[1][idx]) if idx >= 0 else None


# --------------------------------------------------------------- lane loops --
triggerDetail: dict[str, pl.DataFrame] = {}
h2ByLane: dict[str, Counter] = {}
summary = {"params": {"dirs": DIRS, "seed": SEED, "nCap": N_CAP,
                      "windows_h": WINDOWS, "hedgeW": HEDGE_W, "hedgeUsd": HEDGE_USD,
                      "ctrlN": CTRL_N, "bonfRawP": BONF_RAW_P},
           "censusCrossStem": census, "negRiskTrueShare": 100 * sum(known) / max(len(known), 1)}

for lane, x in LANES.items():
    q = qualified(x).sort("tMinUs")
    qt: list[int] = [t // 1_000_000 for t in q["tMinUs"].to_list()]
    qMid: list[str] = q["marketId"].to_list()
    qSid: list[int] = q["sid"].to_list()
    qA: list[str] = q["account"].to_list()
    qO: list[str] = q["outcome"].to_list()

    lm = q.filter(pl.col("sid") >= 0).join(milLadder.select("marketId", "eventSlug"),
                                           on="marketId")
    log(f"[lane:{lane}] >=$X bursts on military ladder rungs (full census): {lm.height:,}")
    cand = lm.sort("tX", "account", "marketId", "outcome")
    nAll = cand.height
    if nAll > N_CAP:
        idx = sorted(random.Random(SEED).sample(range(nAll), N_CAP))
        cand = (cand.with_row_index("ri")
                .filter(pl.col("ri").is_in(pl.Series(idx).implode()))
                .drop("ri"))
    ng = cand.group_by("eventSlug").agg(n=pl.len()).sort("n", descending=True)
    log(f"[lane:{lane}] sampled triggers: {cand.height} of {nAll:,} (seed {SEED}); "
        f"per-stem: " + ", ".join(f"{r['eventSlug']}:{r['n']}"
                                  for r in ng.head(10).to_dicts()))

    milOtherIds = milOther["marketId"].to_list()
    ladVol = milLadder["volumeUsd"].median()
    c2Liquid = milOther.filter(pl.col("volumeUsd") >= ladVol)["marketId"].to_list()
    endDateOf = dict(zip(milLadder["marketId"].to_list(), milLadder["endDate"].to_list()))

    rows = []
    h2Counter: Counter = Counter()
    h2ByLane[lane] = h2Counter
    for i, r in enumerate(cand.to_dicts()):
        t0 = int(r["tX"] // 1_000_000)
        acc = r["account"]
        sid = int(r["sid"])
        t0n = r["tX"]
        sibs = [m for m, s in midToSid.items() if s == sid and m != r["marketId"]]
        rng = random.Random(SEED * 1_000_003 + i)
        c1s = rng.sample([m for m, s in midToSid.items() if s != sid], CTRL_N)
        c2s = rng.sample(milOtherIds, CTRL_N)
        c2ls = rng.sample(c2Liquid, min(CTRL_N, len(c2Liquid)))
        rr = {"lane": lane, "tri": i, "t0": t0n, "stem": r["eventSlug"],
              "marketId": r["marketId"], "outcome": r["outcome"], "account": acc,
              "usd": r["usd"]}
        # reactions + controls per window
        for wName, w in WINDOWS.items():
            lo = bisect_right(qt, t0)
            hi = bisect_right(qt, t0 + w)
            firstHit = next((j for j in range(lo, hi)
                             if qSid[j] == sid and qMid[j] != r["marketId"]
                             and qA[j] != acc), None)
            rr[f"react_{wName}"] = firstHit is not None
            if firstHit is not None:
                rr[f"react1_{wName}"] = {"t": qt[firstHit], "mid": qMid[firstHit],
                                         "out": qO[firstHit]}
            seg = set(qMid[lo:hi])
            rr[f"c1_{wName}"] = int(any(c in seg for c in c1s))
            rr[f"c2_{wName}"] = int(any(c in seg for c in c2s))
            rr[f"c2liq_{wName}"] = int(any(c in seg for c in c2ls))
        # hedge lanes H1/H2 at HEDGE_W (per-lane decomposition accumulators)
        win0, win1 = t0, t0 + HEDGE_W
        h1 = False
        cnt = printIdx.get(r["marketId"])
        if cnt is not None:
            a = bisect_right(cnt["t"], win0)
            b = bisect_right(cnt["t"], win1)
            h1 = any(ca != acc and cu >= HEDGE_USD
                     and ((cs == "SELL" and co == r["outcome"])
                          or (cs == "BUY" and co != r["outcome"]))
                     for ca, cs, co, cu in zip(cnt["acc"][a:b], cnt["side"][a:b],
                                               cnt["out"][a:b], cnt["usd"][a:b]))
        h2 = False
        for sib in sibs:
            sp = printIdx.get(sib)
            if sp is None:
                continue
            a = bisect_right(sp["t"], win0)
            b = bisect_right(sp["t"], win1)
            zipped = [(sp["acc"][j], sp["side"][j], sp["out"][j], sp["usd"][j])
                      for j in range(a, b)]
            sel = [(ca, cs, co) for ca, cs, co, cu in zipped
                   if ca != acc and cu >= HEDGE_USD]
            if sel:
                h2 = True
                d0, dS = endDateOf[r["marketId"]], endDateOf[sib]
                posK = "unknown" if d0 is None or dS is None else (
                    "later" if dS > d0 else "earlier")
                for ca, cs, co in sel:
                    h2Counter[f"{cs} {co} {posK}"] += 1
        rr["h1"], rr["h2"], rr["hedgeWitness"] = h1, h2, h1 or h2
        # first-print drift from the earliest reaction (earliest window wins)
        first = next((rr[f"react1_{w}"] for w in
                      ["10m", "1h", "6h", "24h"] if rr.get(f"react1_{w}")), None)
        if first:
            reactMid, reactOut = first["mid"], first["out"]
            p0 = lastAt(reactMid, t0)
            p1h = lastAt(reactMid, t0 + 3_600)
            p1d = lastAt(reactMid, t0 + 86_400)
            if p0 and p1h:
                base = (1.0 - p0) if reactOut == "No" else p0
                tgt = (1.0 - p1h) if reactOut == "No" else p1h
                rr["reactRung"], rr["reactOut"] = reactMid, reactOut
                rr["p0"], rr["p1h"] = base, tgt
                rr["drift1h"] = tgt / base - 1.0
            if p0 and p1d:
                base = (1.0 - p0) if reactOut == "No" else p0
                tgt = (1.0 - p1d) if reactOut == "No" else p1d
                rr["p1d"] = tgt
                rr["drift1d"] = tgt / base - 1.0
            rr["reactDelayMin"] = (first["t"] - t0) / 60.0
        rows.append(rr)

    det = pl.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    det.write_parquet(OUT / f"triggers_{lane}.parquet")
    triggerDetail[lane] = det
    log(f"[lane:{lane}] triggers detailed & saved ({cand.height} rows, "
        f"t={time.time() - t0wall:.0f}s)")

# ------------------------------------------------------- gate tables/results --
RESULTS = {}
for lane in LANES:
    det = triggerDetail[lane]
    h2Counter = h2ByLane[lane]
    n = det.height
    rates = {}
    for wName in WINDOWS:
        k = int(det[f"react_{wName}"].sum())
        k1, n1 = int(det[f"c1_{wName}"].sum()), n * CTRL_N
        k2, n2 = int(det[f"c2_{wName}"].sum()), n * CTRL_N
        k2l = int(det[f"c2liq_{wName}"].sum())
        p1, p2 = ztest(k, n, k1, n1), ztest(k, n, k2, n2)
        gate = (k / n > k1 / n1 if n1 else False) and (k / n > k2 / n2 if n2 else False) \
            and p1 < BONF_RAW_P and p2 < BONF_RAW_P and n >= 100
        rates[wName] = {"triggerRate": k / n, "c1Rate": k1 / max(n1, 1), "c2Rate": k2 / n2,
                        "c2LiqRate": k2l / max(n2, 1), "pVsC1": p1, "pVsC2": p2,
                        "g1": bool(gate)}
        log(f"[gate:{lane}/{wName}] react {100 * k / n:.1f}% vs C1 "
            f"{100 * k1 / max(n1, 1):.1f}% / C2 {100 * k2 / n2:.1f}% "
            f"(p={p1:.3g}/{p2:.3g}) G1={'PASS' if gate else 'fail'}")
    wit = float(det["hedgeWitness"].mean())
    g2 = wit >= 0.30
    log(f"[gate:{lane}/hedge] witness {100 * wit:.1f}% (H1 {100 * det['h1'].mean():.1f}% | "
        f"H2 {100 * det['h2'].mean():.1f}%) G2={'PASS' if g2 else 'fail'}")
    dr = det.filter(pl.col("drift1h").is_not_null())
    med1h = float(dr["drift1h"].median()) if dr.height else None
    med1d = (float(det["drift1d"].median())
             if "drift1d" in det.columns and det["drift1d"].is_not_null().any() else None)
    g3 = bool(dr.height > 0 and med1h is not None and med1h >= 0.01)
    d1dTxt = f"{100 * med1d:+.2f}%" if med1d is not None else "n/a"
    log(f"[gate:{lane}/drift] n={dr.height} median drift1h {100 * med1h:+.2f}% "
        f"(T+1d median {d1dTxt}) G3={'PASS' if g3 else 'fail'}") if dr.height \
        else log(f"[gate:{lane}/drift] n=0 (no reacting triggers with price) "
                 f"G3=fail")
    anyG1 = any(r["g1"] for r in rates.values())
    verdict = ("INCONCLUSIVE(n<100)" if n < 100 else
               "REAL" if anyG1 and g2 and g3 else
               "PRE-EXISTING" if anyG1 and g2 else "ABSENT")
    log(f"[verdict:{lane}] {verdict} (n={n})")
    RESULTS[lane] = {"n": int(n), "rates": rates, "witness": wit,
                     "g1": anyG1, "g2": bool(g2), "g3": g3,
                     "medianDrift1h": med1h, "verdict": verdict,
                     "h2Decompose": dict(h2Counter.most_common())}
    for key, val in sorted(h2Counter.items(), key=lambda kv: -kv[1]):
        log(f"[h2:{lane}] {key}: {val}")

overall = RESULTS["10k"]["verdict"] if "10k" in RESULTS else "ABSENT"
log(f"[verdict:OVERALL] {overall}")
log(f"[done] total t={time.time() - t0wall:.0f}s")
(OUT / "summary.json").write_text(json.dumps(summary | RESULTS, indent=2, default=str))
