"""Price-move check: what is left if we copy an insider buy after a delay.

Our entry price is the last trade at or before entryTs + delay (missing when that
print is more than 6 hours old), plus slippage. Horizon marks use the same rule.
Resolution pays $1 when the bought outcome won and $0 when it lost.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import polars as pl

entryWindow = timedelta(minutes=10)
staleWindow = timedelta(hours=6)
defaultDelaysSec: tuple[int, ...] = (0, 30, 60, 5 * 60, 15 * 60, 60 * 60)
defaultHorizons: tuple[tuple[str, int | None], ...] = (
    ("1h", 60 * 60),
    ("6h", 6 * 60 * 60),
    ("1d", 24 * 60 * 60),
    ("resolution", None),
)
bootstrapDraws = 1000
bootstrapSeed = 0
defaultSlippageBps = 50.0

entrySchema = {
    "entryId": pl.Int64,
    "account": pl.String,
    "marketId": pl.String,
    "outcome": pl.String,
    "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
    "price": pl.Float64,
    "size": pl.Float64,
    "usd": pl.Float64,
}

returnSchema = {
    "entryId": pl.Int64,
    "account": pl.String,
    "marketId": pl.String,
    "question": pl.String,
    "outcome": pl.String,
    "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
    "usd": pl.Float64,
    "delaySec": pl.Int64,
    "horizon": pl.String,
    "ourEntryPrice": pl.Float64,
    "exitPrice": pl.Float64,
    "ret": pl.Float64,
}

summarySchema = {
    "delaySec": pl.Int64,
    "horizon": pl.String,
    "n": pl.Int64,
    "meanRet": pl.Float64,
    "medianRet": pl.Float64,
    "winRate": pl.Float64,
    "ciLow": pl.Float64,
    "ciHigh": pl.Float64,
    "usdWeightedMean": pl.Float64,
}


@dataclass
class DriftStats:
    n60: int
    newer60: int
    changed60: int
    meanRel60: float | None
    medianRel60: float | None
    meanAbs60: float | None
    n5m: int
    newer5m: int
    changed5m: int
    meanRel5m: float | None
    medianRel5m: float | None
    meanAbs5m: float | None


@dataclass
class MarketDrop:
    marketId: str
    question: str
    horizon: str
    pnl: float
    totalPnl: float
    entryCount: int
    otherQuestion: str | None


@dataclass
class MoveStudy:
    name: str
    blurb: str
    accountCount: int
    accountsWithEntries: int
    entryCount: int
    usd: float
    summary: pl.DataFrame
    heldOut: pl.DataFrame
    dropped: MarketDrop | None
    drift: DriftStats


def aggregateEntries(
    fills: pl.DataFrame,
    accounts: Sequence[str],
    window: timedelta = entryWindow,
) -> pl.DataFrame:
    """Cluster one account's BUY fills on a single outcome.

    Fills more than `window` after the cluster's first fill start a new entry.
    Timestamp is the first fill. Price is size-weighted. Usd is size × price.
    """
    wanted = {account.lower() for account in accounts}
    empty = pl.DataFrame(schema=entrySchema)
    if not wanted or fills.height == 0:
        return empty
    buys = (
        fills.filter(
            (pl.col("side") == "BUY")
            & pl.col("account").str.to_lowercase().is_in(list(wanted))
            & (pl.col("size") > 0)
            & pl.col("price").is_not_null()
        )
        .with_columns(pl.col("account").str.to_lowercase())
        .sort(["account", "marketId", "outcome", "ts"])
    )
    if buys.height == 0:
        return empty

    records: list[dict] = []
    bucket: list[dict] = []

    def flush() -> None:
        if not bucket:
            return
        size = 0.0
        usd = 0.0
        for row in bucket:
            size += float(row["size"])
            usd += float(row["size"]) * float(row["price"])
        first = bucket[0]
        records.append(
            {
                "entryId": len(records),
                "account": first["account"],
                "marketId": first["marketId"],
                "outcome": first["outcome"],
                "ts": first["ts"],
                "price": usd / size,
                "size": size,
                "usd": usd,
            }
        )

    columns = ["account", "marketId", "outcome", "ts", "size", "price"]
    for row in buys.select(columns).iter_rows(named=True):
        if bucket:
            sameKey = (
                row["account"] == bucket[0]["account"]
                and row["marketId"] == bucket[0]["marketId"]
                and row["outcome"] == bucket[0]["outcome"]
            )
            if not sameKey or row["ts"] > bucket[0]["ts"] + window:
                flush()
                bucket = []
        bucket.append(row)
    flush()
    return pl.DataFrame(records, schema=entrySchema)


def buildPriceTape(fills: pl.DataFrame, markets: pl.DataFrame) -> pl.DataFrame:
    """Last trade price per (market, outcome, timestamp), plus the complement.

    A fill at price p on one outcome of a two-outcome market is also a print at
    1 − p on the other outcome. When both exist at the same timestamp, the
    direct print wins.
    """
    pairs = markets.filter(pl.col("outcomes").list.len() == 2).select(
        "marketId",
        pl.col("outcomes").list.get(0).alias("outcomeA"),
        pl.col("outcomes").list.get(1).alias("outcomeB"),
    )
    base = fills.select("ts", "marketId", "outcome", "price").join(pairs, on="marketId", how="inner")
    base = base.filter(
        pl.col("price").is_not_null()
        & (pl.col("price") >= 0)
        & (pl.col("price") <= 1)
        & ((pl.col("outcome") == pl.col("outcomeA")) | (pl.col("outcome") == pl.col("outcomeB")))
    )
    if base.height == 0:
        return pl.DataFrame(
            schema={
                "marketId": pl.String,
                "outcome": pl.String,
                "ts": pl.Datetime(time_unit="us", time_zone="UTC"),
                "price": pl.Float64,
            }
        )
    base = base.with_row_index("rowId")
    direct = base.select(
        "rowId",
        "ts",
        "marketId",
        "outcome",
        "price",
        pl.lit(1, dtype=pl.Int8).alias("prefer"),
    )
    complementOutcome = (
        pl.when(pl.col("outcome") == pl.col("outcomeA"))
        .then(pl.col("outcomeB"))
        .otherwise(pl.col("outcomeA"))
    )
    complement = base.select(
        "rowId",
        "ts",
        "marketId",
        complementOutcome.alias("outcome"),
        (1.0 - pl.col("price")).alias("price"),
        pl.lit(0, dtype=pl.Int8).alias("prefer"),
    )
    both = pl.concat([complement, direct], how="vertical")
    return (
        both.group_by(["marketId", "outcome", "ts"])
        .agg(pl.col("price").sort_by(["prefer", "rowId"]).last())
        .sort(["marketId", "outcome", "ts"])
    )


def priceAt(
    tape: pl.DataFrame,
    queries: pl.DataFrame,
    stale: timedelta = staleWindow,
) -> pl.DataFrame:
    """Attach the last trade at or before each query timestamp.

    `queries` needs marketId, outcome, and ts. Price is null when no print falls
    inside the previous `stale` window.
    """
    if queries.height == 0 or tape.height == 0:
        return queries.with_columns(pl.lit(None, dtype=pl.Float64).alias("price"))
    tagged = queries.with_row_index("__qid")
    left = tagged.sort(["marketId", "outcome", "ts"])
    right = tape.select("marketId", "outcome", "ts", "price").sort(["marketId", "outcome", "ts"])
    joined = left.join_asof(
        right,
        on="ts",
        by=["marketId", "outcome"],
        strategy="backward",
        tolerance=stale,
        check_sortedness=False,
    )
    return joined.sort("__qid").drop("__qid")


def _marksAt(entries: pl.DataFrame, tape: pl.DataFrame, offsets: Sequence[int]) -> pl.DataFrame:
    parts: list[pl.DataFrame] = []
    for offset in offsets:
        parts.append(
            entries.select(
                "entryId",
                "marketId",
                "outcome",
                (pl.col("ts") + pl.duration(seconds=int(offset))).alias("ts"),
                pl.lit(int(offset)).alias("offset"),
            )
        )
    priced = priceAt(tape, pl.concat(parts, how="vertical"))
    wide = entries.select("entryId")
    for offset in offsets:
        column = f"p{int(offset)}"
        part = priced.filter(pl.col("offset") == int(offset)).select(
            "entryId",
            pl.col("price").alias(column),
        )
        wide = wide.join(part, on="entryId", how="left")
    return wide


def tradeReturns(
    entries: pl.DataFrame,
    tape: pl.DataFrame,
    markets: pl.DataFrame,
    delays: Sequence[int] = defaultDelaysSec,
    horizons: Sequence[tuple[str, int | None]] = defaultHorizons,
    slippageBps: float = defaultSlippageBps,
) -> pl.DataFrame:
    """Long frame of copy returns. One row per entry, delay, and horizon."""
    if entries.height == 0:
        return pl.DataFrame(schema=returnSchema)
    timed = [int(seconds) for _, seconds in horizons if seconds is not None]
    offsets = sorted(set(int(delay) for delay in delays) | set(timed))
    marks = _marksAt(entries, tape, offsets)
    marketCols = markets.select("marketId", "question", "winner", "resolvedAt").unique(
        subset=["marketId"],
        keep="first",
    )
    base = entries.join(marketCols, on="marketId", how="left").join(marks, on="entryId", how="left")
    slipFactor = 1.0 + slippageBps / 10_000.0
    pieces: list[pl.DataFrame] = []
    for delay in delays:
        mark = pl.col(f"p{int(delay)}")
        ourExpr = pl.when(mark.is_not_null() & (mark > 0)).then(mark * slipFactor).otherwise(None)
        decision = pl.col("ts") + pl.duration(seconds=int(delay))
        tooLate = (
            pl.when(pl.col("resolvedAt").is_null())
            .then(False)
            .otherwise(pl.col("resolvedAt") <= decision)
        )
        for name, seconds in horizons:
            if seconds is None:
                exitExpr = (
                    pl.when(pl.col("winner").is_null() | tooLate)
                    .then(None)
                    .when(pl.col("outcome") == pl.col("winner"))
                    .then(1.0)
                    .otherwise(0.0)
                )
            else:
                exitExpr = pl.col(f"p{int(seconds)}")
            retExpr = (
                pl.when(ourExpr.is_not_null() & exitExpr.is_not_null())
                .then((exitExpr - ourExpr) / ourExpr)
                .otherwise(None)
            )
            pieces.append(
                base.select(
                    "entryId",
                    "account",
                    "marketId",
                    "question",
                    "outcome",
                    "ts",
                    "usd",
                    pl.lit(int(delay)).alias("delaySec"),
                    pl.lit(name).alias("horizon"),
                    ourExpr.alias("ourEntryPrice"),
                    exitExpr.alias("exitPrice"),
                    retExpr.alias("ret"),
                )
            )
    return pl.concat(pieces, how="vertical")


def _percentile(sortedVals: list[float], prob: float) -> float:
    if len(sortedVals) == 1:
        return sortedVals[0]
    rank = prob * (len(sortedVals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sortedVals) - 1)
    weight = rank - lo
    return sortedVals[lo] * (1.0 - weight) + sortedVals[hi] * weight


def _bootstrapMeanCi(values: list[float], draws: int, rng: random.Random) -> tuple[float, float]:
    n = len(values)
    if n == 1:
        return values[0], values[0]
    means = [sum(rng.choices(values, k=n)) / n for _ in range(draws)]
    means.sort()
    return _percentile(means, 0.025), _percentile(means, 0.975)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def summarizeReturns(
    returns: pl.DataFrame,
    delays: Sequence[int] = defaultDelaysSec,
    horizons: Sequence[tuple[str, int | None]] = defaultHorizons,
    draws: int = bootstrapDraws,
    seed: int = bootstrapSeed,
) -> pl.DataFrame:
    """Equal-weight mean with a bootstrap 95% CI, plus a usd-weighted mean."""
    rng = random.Random(seed)
    rows: list[dict] = []
    for delay in delays:
        for name, _seconds in horizons:
            part = returns.filter(
                (pl.col("delaySec") == int(delay))
                & (pl.col("horizon") == name)
                & pl.col("ret").is_not_null()
            )
            n = part.height
            if n == 0:
                rows.append(
                    {
                        "delaySec": int(delay),
                        "horizon": name,
                        "n": 0,
                        "meanRet": None,
                        "medianRet": None,
                        "winRate": None,
                        "ciLow": None,
                        "ciHigh": None,
                        "usdWeightedMean": None,
                    }
                )
                continue
            values = [float(value) for value in part["ret"].to_list()]
            weights = [float(value) for value in part["usd"].to_list()]
            meanRet = sum(values) / n
            weightSum = sum(weights)
            weighted = sum(ret * usd for ret, usd in zip(values, weights)) / weightSum if weightSum else None
            ciLow, ciHigh = _bootstrapMeanCi(values, draws, rng)
            rows.append(
                {
                    "delaySec": int(delay),
                    "horizon": name,
                    "n": n,
                    "meanRet": meanRet,
                    "medianRet": _median(values),
                    "winRate": sum(1 for value in values if value > 0) / n,
                    "ciLow": ciLow,
                    "ciHigh": ciHigh,
                    "usdWeightedMean": weighted,
                }
            )
    return pl.DataFrame(rows, schema=summarySchema)


def _scoreMarkets(returns: pl.DataFrame, horizon: str) -> pl.DataFrame:
    part = returns.filter(
        (pl.col("delaySec") == 0) & (pl.col("horizon") == horizon) & pl.col("ret").is_not_null()
    )
    if part.height == 0:
        return part
    return part.group_by("marketId").agg(
        (pl.col("usd") * pl.col("ret")).sum().alias("pnl"),
        pl.col("ret").sum().alias("retSum"),
        pl.len().alias("entryCount"),
        pl.col("question").drop_nulls().first().alias("question"),
    )


def pickDroppedMarket(returns: pl.DataFrame) -> MarketDrop | None:
    """Market with the largest dollar PnL at delay 0, preferring resolution."""
    chosenHorizon = "resolution"
    scores = _scoreMarkets(returns, "resolution")
    if scores.height == 0:
        chosenHorizon = "1d"
        scores = _scoreMarkets(returns, "1d")
    if scores.height == 0:
        return None
    byPnl = scores.sort(["pnl", "marketId"], descending=[True, False]).row(0, named=True)
    byRet = scores.sort(["retSum", "marketId"], descending=[True, False]).row(0, named=True)
    other = None if byRet["marketId"] == byPnl["marketId"] else byRet["question"] or byRet["marketId"]
    return MarketDrop(
        marketId=byPnl["marketId"],
        question=byPnl["question"] or byPnl["marketId"],
        horizon=chosenHorizon,
        pnl=float(byPnl["pnl"]),
        totalPnl=float(scores["pnl"].sum()),
        entryCount=int(byPnl["entryCount"]),
        otherQuestion=other,
    )


def _pairDrift(frame: pl.DataFrame, later: str) -> tuple[int, int, int, float | None, float | None, float | None]:
    paired = frame.filter(pl.col("p0").is_not_null() & (pl.col("p0") > 0) & pl.col(later).is_not_null())
    if paired.height == 0:
        return 0, 0, 0, None, None, None
    newer = paired.filter(pl.col(f"{later}ts") > pl.col("p0ts")).height
    changed = paired.filter(pl.col(later) != pl.col("p0")).height
    rel = (pl.col(later) - pl.col("p0")) / pl.col("p0")
    absolute = pl.col(later) - pl.col("p0")
    stats = paired.select(
        rel.mean().alias("meanRel"),
        rel.median().alias("medianRel"),
        absolute.mean().alias("meanAbs"),
    ).row(0, named=True)
    return (
        paired.height,
        newer,
        changed,
        float(stats["meanRel"]),
        float(stats["medianRel"]),
        float(stats["meanAbs"]),
    )


def priceDrift(entries: pl.DataFrame, tape: pl.DataFrame) -> DriftStats:
    """How far the outcome price moves in the first 60s and 5m after entry."""
    empty = DriftStats(0, 0, 0, None, None, None, 0, 0, 0, None, None, None)
    if entries.height == 0 or tape.height == 0:
        return empty
    parts = [
        entries.select(
            "entryId",
            "marketId",
            "outcome",
            (pl.col("ts") + pl.duration(seconds=seconds)).alias("ts"),
            pl.lit(label).alias("which"),
        )
        for label, seconds in (("p0", 0), ("p60", 60), ("p300", 300))
    ]
    queries = pl.concat(parts, how="vertical").sort(["marketId", "outcome", "ts"])
    right = tape.select("marketId", "outcome", pl.col("ts").alias("matchTs"), "price").sort(
        ["marketId", "outcome", "matchTs"]
    )
    joined = queries.join_asof(
        right,
        left_on="ts",
        right_on="matchTs",
        by=["marketId", "outcome"],
        strategy="backward",
        tolerance=staleWindow,
        check_sortedness=False,
    )
    wide = entries.select("entryId")
    for label in ("p0", "p60", "p300"):
        part = joined.filter(pl.col("which") == label).select(
            "entryId",
            pl.col("price").alias(label),
            pl.col("matchTs").alias(f"{label}ts"),
        )
        wide = wide.join(part, on="entryId", how="left")
    n60, newer60, changed60, meanRel60, medianRel60, meanAbs60 = _pairDrift(wide, "p60")
    n5m, newer5m, changed5m, meanRel5m, medianRel5m, meanAbs5m = _pairDrift(wide, "p300")
    return DriftStats(
        n60,
        newer60,
        changed60,
        meanRel60,
        medianRel60,
        meanAbs60,
        n5m,
        newer5m,
        changed5m,
        meanRel5m,
        medianRel5m,
        meanAbs5m,
    )


def runStudy(
    name: str,
    blurb: str,
    entries: pl.DataFrame,
    tape: pl.DataFrame,
    markets: pl.DataFrame,
    accountCount: int,
    slippageBps: float = defaultSlippageBps,
    delays: Sequence[int] = defaultDelaysSec,
    horizons: Sequence[tuple[str, int | None]] = defaultHorizons,
) -> MoveStudy:
    returns = tradeReturns(entries, tape, markets, delays, horizons, slippageBps)
    summary = summarizeReturns(returns, delays, horizons)
    dropped = pickDroppedMarket(returns)
    if dropped is None:
        heldOut = pl.DataFrame(schema=summarySchema)
    else:
        held = returns.filter(pl.col("marketId") != dropped.marketId)
        heldOut = summarizeReturns(held, delays, horizons)
    usd = float(entries["usd"].sum()) if entries.height else 0.0
    accountsWithEntries = int(entries["account"].n_unique()) if entries.height else 0
    return MoveStudy(
        name=name,
        blurb=blurb,
        accountCount=accountCount,
        accountsWithEntries=accountsWithEntries,
        entryCount=entries.height,
        usd=usd,
        summary=summary,
        heldOut=heldOut,
        dropped=dropped,
        drift=priceDrift(entries, tape),
    )


def delayLabel(delaySec: int) -> str:
    if delaySec < 60:
        return f"{delaySec}s"
    if delaySec % 3600 == 0:
        return f"{delaySec // 3600}h"
    if delaySec % 60 == 0:
        return f"{delaySec // 60}m"
    return f"{delaySec}s"


def _fmtPct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * value:.2f}%"


def _fmtPrice(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.4f}"


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _clean(text: str) -> str:
    return " ".join(text.replace("|", "/").split())


def renderTable(summary: pl.DataFrame) -> str:
    header = "| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |"
    rule = "|---|---|---:|---:|---:|---:|---|---:|"
    lines = [header, rule]
    for row in summary.iter_rows(named=True):
        if row["n"] == 0:
            ci = "n/a"
        else:
            ci = f"[{_fmtPct(row['ciLow'])}, {_fmtPct(row['ciHigh'])}]"
        lines.append(
            "| "
            + " | ".join(
                [
                    delayLabel(int(row["delaySec"])),
                    str(row["horizon"]),
                    str(int(row["n"])),
                    _fmtPct(row["meanRet"]),
                    _fmtPct(row["medianRet"]),
                    _fmtPct(row["winRate"]),
                    ci,
                    _fmtPct(row["usdWeightedMean"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _resolutionBits(summary: pl.DataFrame, delays: Sequence[int]) -> str:
    bits = []
    for delay in delays:
        rows = summary.filter((pl.col("delaySec") == int(delay)) & (pl.col("horizon") == "resolution"))
        if rows.height == 0:
            continue
        row = rows.row(0, named=True)
        bits.append(
            f"{delayLabel(int(delay))} mean {_fmtPct(row['meanRet'])} "
            f"(usd-weighted {_fmtPct(row['usdWeightedMean'])}, n={int(row['n'])})"
        )
    return "; ".join(bits)


def _dropSentence(dropped: MarketDrop) -> str:
    share = ""
    if dropped.totalPnl > 0 and dropped.pnl > 0:
        share = f", {100.0 * dropped.pnl / dropped.totalPnl:.0f}% of dollar PnL"
    sentence = (
        f"Leave-one-market-out drops the largest delay-0 {dropped.horizon} dollar PnL "
        f"({_clean(dropped.question)}, {dropped.entryCount} entries, "
        f"{_money(dropped.pnl)} of {_money(dropped.totalPnl)}{share})."
    )
    if dropped.otherQuestion:
        sentence += (
            " The largest equal-weight sum of returns at that cell is "
            f"{_clean(dropped.otherQuestion)}."
        )
    return sentence


def _driftSentence(drift: DriftStats) -> str:
    def bit(
        label: str,
        n: int,
        newer: int,
        changed: int,
        medianRel: float | None,
        meanRel: float | None,
        meanAbs: float | None,
    ) -> str:
        if n == 0 or medianRel is None:
            return f"no paired price at {label}"
        return (
            f"{label} median {_fmtPct(medianRel)}, mean {_fmtPct(meanRel)}, "
            f"mean price change {_fmtPrice(meanAbs)} "
            f"({newer}/{n} newer prints, {changed}/{n} changed price)"
        )

    early = bit("60s", drift.n60, drift.newer60, drift.changed60, drift.medianRel60, drift.meanRel60, drift.meanAbs60)
    later = bit("5m", drift.n5m, drift.newer5m, drift.changed5m, drift.medianRel5m, drift.meanRel5m, drift.meanAbs5m)
    return f"Price move from the entry print: {early}; {later}."


def renderStudy(study: MoveStudy) -> str:
    lines = [
        f"## {study.name}",
        "",
        study.blurb,
        "",
        (
            f"{study.accountCount} accounts, {study.accountsWithEntries} with an entry, "
            f"{study.entryCount} entries, {_money(study.usd)} insider usd."
        ),
        "",
        renderTable(study.summary),
        "",
        "Resolution: " + _resolutionBits(study.summary, (0, 60, 300, 3600)) + ".",
        "",
        _driftSentence(study.drift),
        "",
    ]
    if study.dropped is None:
        lines.append("No delay-0 resolution or 1d return, so there is no market to drop.")
    else:
        lines.append(_dropSentence(study.dropped))
        lines.append("")
        lines.append(renderTable(study.heldOut))
        lines.append("")
        lines.append(
            "Without that market, resolution: " + _resolutionBits(study.heldOut, (0, 60, 300, 3600)) + "."
        )
    lines.append("")
    return "\n".join(lines)


def buildReport(
    fills: pl.DataFrame,
    markets: pl.DataFrame,
    suspicious: pl.DataFrame,
    labels: pl.DataFrame,
    slippageBps: float = defaultSlippageBps,
    splitDate: date = date(2026, 3, 1),
) -> str:
    cutoff = datetime(splitDate.year, splitDate.month, splitDate.day, tzinfo=timezone.utc)
    tape = buildPriceTape(fills, markets)
    labelAccounts = labels.get_column("wallet").to_list()
    susFrame = suspicious.filter(pl.col("suspicious"))
    susAccounts = susFrame.get_column("account").to_list()
    labeledEntries = aggregateEntries(fills, labelAccounts)
    susEntries = aggregateEntries(fills, susAccounts)
    forwardEntries = susEntries.filter(pl.col("ts") >= cutoff)
    labeled = runStudy(
        "Labeled wallets",
        "Nine news-linked wallets. This copies every clustered buy on the tape, including the trades that made them known.",
        labeledEntries,
        tape,
        markets,
        accountCount=len(labelAccounts),
        slippageBps=slippageBps,
    )
    suspiciousStudy = runStudy(
        "Suspicious accounts",
        (
            f"Accounts with `suspicious == true` in `data/suspicious.parquet`, flagged using fills "
            f"before {splitDate.isoformat()}. The full sample includes the winning bets that earned the flag."
        ),
        susEntries,
        tape,
        markets,
        accountCount=len(susAccounts),
        slippageBps=slippageBps,
    )
    forward = runStudy(
        "Forward subset",
        (
            f"Buys whose entry time is on or after {splitDate.isoformat()} by those same flagged accounts. "
            "The flag did not use these fills. A cluster that started before the split stays in the hindsight sample."
        ),
        forwardEntries,
        tape,
        markets,
        accountCount=len(susAccounts),
        slippageBps=slippageBps,
    )
    intro = "\n".join(
        [
            "# Price-move check",
            "",
            "If we buy the same outcome as a suspected insider after a delay, is there still a profit at 1h, 1d, and resolution?",
            "",
            (
                f"Our entry price is the last trade at or before `entryTs + delay`, plus {slippageBps:.0f} bps "
                "slippage (`price × bps / 10000`). A print older than 6 hours is missing. "
                "An account's buys of one outcome are one entry while they fall within 10 minutes of the first fill; "
                "the entry time is that first fill and its weight is size × price. "
                "Return per $1 is `(exitPrice − ourEntryPrice) / ourEntryPrice`. "
                "Timed exits use the same 6-hour mark. Resolution pays $1 when that outcome won and $0 when it lost, "
                "and only when `resolvedAt` is after the delayed entry time. "
                f"The 95% interval is a {bootstrapDraws}-draw bootstrap of the equal-weight mean (seed {bootstrapSeed}), "
                "drawn in delay-then-horizon order. Dollar-weighted means use the insider's entry usd. "
                "Win rate is the share of priced entries with return > 0. "
                "`n` is entries with both an entry price and an exit price."
            ),
            "",
            (
                f"Tape: {fills.height:,} fills, {markets.height} markets, {tape.height:,} price points "
                f"(direct prints plus complements)."
            ),
            "",
            (
                "A trade at price p on one outcome is also a print at 1 − p on the other outcome of that same market. "
                "Each market is its own Yes/No pair. The direct print wins when both exist at one timestamp."
            ),
            "",
        ]
    )
    caveats = "\n".join(
        [
            "## Caveats",
            "",
            (
                "The suspicious-account table is hindsight-biased: those accounts were flagged because a pre-split bet won. "
                "The forward subset is the copy a discovery rule could have placed after the split."
            ),
            "",
            (
                "Bootstrap draws treat entries as independent. Entries in the same market move together, so the interval "
                "is tight relative to market-level uncertainty. The leave-one-market-out table is the check for one market carrying the mean."
            ),
            "",
            (
                "Slippage is charged on the entry only. Resolution pays exactly 0 or 1. "
                "Prints whose outcome is outside that market's two listed outcomes are omitted from the tape."
            ),
            "",
        ]
    )
    sections = [
        intro.rstrip("\n"),
        renderStudy(labeled).strip("\n"),
        renderStudy(suspiciousStudy).strip("\n"),
        renderStudy(forward).strip("\n"),
        caveats.rstrip("\n"),
    ]
    return "\n\n".join(sections) + "\n"
