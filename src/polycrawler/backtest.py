"""Replay copied buys and write a run."""

from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Mapping, Sequence

import polars as pl
import yaml
from pydantic import BaseModel, ConfigDict

from polycrawler.fetch import fillDedupeKeys
from polycrawler.priceMove import buildPriceTape, priceAt
from polycrawler.strategy import BookMemory, netPath, observeBuy, orderShares, planBuy, recordCopy

tsType = pl.Datetime(time_unit="us", time_zone="UTC")
markHorizon = timedelta(days=3650)


class BacktestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minNetUsd: float = 500
    maxEntryPrice: float = 0.5
    minEntryPrice: float | None = None
    maxEntriesPerEvent: int | None = None
    copyRule: Literal["all", "largestPerEvent"] = "all"
    sizing: Literal["fixed", "mirrorPct"] = "mirrorPct"
    fixedUsd: float = 100
    mirrorPct: float = 1.0
    maxPositionUsd: float | None = 1000
    maxTotalExposureUsd: float | None = None
    exitMode: Literal["followCluster", "holdToResolution"] = "followCluster"
    delaySec: int = 30
    slippageBps: float = 50


tradeSchema = {
    "tradeId": pl.Int64,
    "accountGroup": pl.String,
    "account": pl.String,
    "marketId": pl.String,
    "eventSlug": pl.String,
    "question": pl.String,
    "outcome": pl.String,
    "entryTs": tsType,
    "exitTs": tsType,
    "theirPrice": pl.Float64,
    "theirUsd": pl.Float64,
    "entryPrice": pl.Float64,
    "exitPrice": pl.Float64,
    "shares": pl.Float64,
    "usd": pl.Float64,
    "pnl": pl.Float64,
    "exitReason": pl.String,
    "marked": pl.Boolean,
}


@dataclass
class Lot:
    tradeId: int
    accountGroup: str
    account: str
    marketId: str
    eventSlug: str
    question: str
    outcome: str
    entryTs: datetime
    decisionTs: datetime
    theirPrice: float
    theirUsd: float
    entryPrice: float
    shares: float
    usd: float
    exitTs: datetime | None = None
    exitPrice: float | None = None
    exitReason: str | None = None
    marked: bool = False

    @property
    def pnl(self) -> float | None:
        if self.exitPrice is None:
            return None
        return self.shares * (self.exitPrice - self.entryPrice)


@dataclass
class Book:
    memory: BookMemory = field(default_factory=BookMemory)
    openLots: dict[tuple[str, str, str], list[Lot]] = field(default_factory=dict)
    armed: set[tuple[str, str, str]] = field(default_factory=set)
    net: dict[tuple[str, str, str], float] = field(default_factory=dict)
    lastPrice: dict[tuple[str, str, str], float] = field(default_factory=dict)
    exposure: float = 0.0
    closed: list[Lot] = field(default_factory=list)
    nextId: int = 0
    bursts: dict = field(default_factory=dict)


@dataclass
class Prepared:
    path: pl.DataFrame
    tape: pl.DataFrame
    startTs: datetime
    endTs: datetime


@dataclass
class BacktestResult:
    params: BacktestParams
    paramsHash: str
    trades: pl.DataFrame
    summary: dict


def paramsHash(params: BacktestParams) -> str:
    payload = params.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _lazy(fills: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
    if isinstance(fills, pl.LazyFrame):
        return fills
    return fills.lazy()


def _utc(frame: pl.DataFrame, column: str) -> pl.DataFrame:
    if frame.height == 0:
        return frame
    return frame.with_columns(pl.col(column).cast(tsType))


def prepareBacktest(
    fills: pl.DataFrame | pl.LazyFrame,
    markets: pl.DataFrame,
    accountsToCopy: Sequence[str],
    startTs: datetime,
    endTs: datetime,
    clusterMap: dict[str, str] | None = None,
) -> Prepared:
    lazy = _lazy(fills)
    wanted = sorted({account.lower() for account in accountsToCopy})
    emptyFills = pl.DataFrame(
        schema={
            "ts": tsType,
            "account": pl.String,
            "marketId": pl.String,
            "outcome": pl.String,
            "side": pl.String,
            "size": pl.Float64,
            "price": pl.Float64,
        }
    )
    if not wanted:
        copied = emptyFills
    else:
        copied = (
            lazy.filter(pl.col("account").str.to_lowercase().is_in(wanted))
            .filter((pl.col("ts") >= startTs) & (pl.col("ts") <= endTs))
            .select("ts", "account", "marketId", "outcome", "side", "size", "price")
            .collect()
        )
    marketIds = copied["marketId"].unique().to_list() if copied.height else []
    if marketIds:
        tapeFills = (
            lazy.filter(pl.col("marketId").is_in(marketIds))
            .select("ts", "marketId", "outcome", "price")
            .collect()
        )
    else:
        tapeFills = pl.DataFrame(
            schema={
                "ts": tsType,
                "marketId": pl.String,
                "outcome": pl.String,
                "price": pl.Float64,
            }
        )
    tape = buildPriceTape(tapeFills, markets)
    path = _attachMarkets(netPath(copied, wanted, clusterMap), markets)
    return Prepared(path=path, tape=tape, startTs=startTs, endTs=endTs)


def _attachMarkets(path: pl.DataFrame, markets: pl.DataFrame) -> pl.DataFrame:
    meta = markets
    if "eventSlug" not in meta.columns:
        meta = meta.with_columns(pl.lit(None, dtype=pl.String).alias("eventSlug"))
    if "question" not in meta.columns:
        meta = meta.with_columns(pl.lit(None, dtype=pl.String).alias("question"))
    meta = meta.select("marketId", "eventSlug", "question", "winner", "resolvedAt").unique(
        subset=["marketId"],
        keep="first",
    )
    if path.height == 0:
        return path.join(meta, on="marketId", how="left")
    return path.join(meta, on="marketId", how="left").sort("rowId")


def _slip(price: float | None, slippageBps: float, buying: bool) -> float | None:
    if price is None or price <= 0:
        return None
    factor = 1.0 + slippageBps / 10_000.0 if buying else 1.0 - slippageBps / 10_000.0
    return max(0.0, float(price) * factor)


def _prices(
    frame: pl.DataFrame,
    tape: pl.DataFrame,
    delaySec: int,
    slippageBps: float,
    buying: bool,
    idColumn: str,
) -> dict[int, float | None]:
    if frame.height == 0 or tape.height == 0:
        return {}
    queries = _utc(
        frame.select(
            idColumn,
            "marketId",
            "outcome",
            (pl.col("ts") + pl.duration(seconds=int(delaySec))).alias("ts"),
        ),
        "ts",
    )
    priced = priceAt(tape, queries)
    out: dict[int, float | None] = {}
    for row in priced.iter_rows(named=True):
        out[int(row[idColumn])] = _slip(row["price"], slippageBps, buying)
    return out


def _blankSummary(startTs: datetime, endTs: datetime, digest: str) -> dict:
    return {
        "totalPnl": 0.0,
        "capitalDeployed": 0.0,
        "returnOnDeployed": None,
        "tradeCount": 0,
        "winRate": None,
        "maxDrawdown": 0.0,
        "pnlByEvent": {},
        "topEvent": None,
        "topEventPnl": 0.0,
        "topEventPnlShare": None,
        "pnlWithoutTopEvent": 0.0,
        "capitalByEvent": {},
        "capitalWithoutTopEvent": 0.0,
        "returnWithoutTopEvent": None,
        "medianEventReturn": None,
        "eventCount": 0,
        "markedCount": 0,
        "startTs": startTs.isoformat(),
        "endTs": endTs.isoformat(),
        "paramsHash": digest,
    }


def _emptyTrades() -> pl.DataFrame:
    return pl.DataFrame(schema=tradeSchema)


def _closeKey(
    book: Book,
    key: tuple[str, str, str],
    exitTs: datetime,
    exitPrice: float,
    reason: str,
    marked: bool,
) -> None:
    lots = book.openLots.pop(key, [])
    book.armed.discard(key)
    for lot in lots:
        lot.exitTs = exitTs
        lot.exitPrice = exitPrice
        lot.exitReason = reason
        lot.marked = marked
        book.exposure -= lot.usd
        book.closed.append(lot)
    if book.exposure < 1e-9:
        book.exposure = 0.0


def _maybeExit(
    book: Book,
    key: tuple[str, str, str],
    fillTs: datetime,
    exitPrice: float | None,
    params,
) -> None:
    if params.exitMode != "followCluster" or key not in book.openLots:
        return
    net = book.net.get(key, 0.0)
    price = book.lastPrice.get(key, 0.0)
    worth = net * price if net > 0 else 0.0
    if worth >= params.minNetUsd:
        book.armed.add(key)
        return
    if key not in book.armed or exitPrice is None:
        return
    exitTs = fillTs + timedelta(seconds=int(params.delaySec))
    _closeKey(book, key, exitTs, exitPrice, "followCluster", False)


def _openLot(
    book: Book,
    row: dict,
    ourPrice: float,
    shares: float,
    params,
    theirPrice: float | None = None,
    theirUsd: float | None = None,
) -> None:
    usd = shares * ourPrice
    group = row["accountGroup"]
    key = (group, row["marketId"], row["outcome"])
    decisionTs = row["ts"] + timedelta(seconds=int(params.delaySec))
    lot = Lot(
        tradeId=book.nextId,
        accountGroup=group,
        account=row["account"],
        marketId=row["marketId"],
        eventSlug=row.get("eventSlug") or row["marketId"],
        question=row.get("question") or "",
        outcome=row["outcome"],
        entryTs=row["ts"],
        decisionTs=decisionTs,
        theirPrice=float(row["price"] if theirPrice is None else theirPrice),
        theirUsd=float(row["usd"] if theirUsd is None else theirUsd),
        entryPrice=ourPrice,
        shares=shares,
        usd=usd,
    )
    book.nextId += 1
    book.openLots.setdefault(key, []).append(lot)
    book.exposure += usd
    recordCopy(row, book.memory)
    if params.exitMode == "followCluster":
        net = book.net.get(key, 0.0)
        mark = book.lastPrice.get(key, float(row["price"]))
        if net > 0 and net * mark >= params.minNetUsd:
            book.armed.add(key)


def _onBuy(book: Book, row: dict, ourPrice: float | None, params, endTs: datetime) -> None:
    key = (row["accountGroup"], row["marketId"], row["outcome"])
    burst, fillSize = observeBuy(
        book.bursts.get(key), row["ts"], float(row["size"]), float(row["price"])
    )
    book.bursts[key] = burst
    action, theirShares = planBuy(
        burst,
        fillSize,
        row["accountGroup"],
        row["marketId"],
        row.get("eventSlug"),
        book.memory,
        params,
    )
    if action == "skip":
        return
    decisionTs = row["ts"] + timedelta(seconds=int(params.delaySec))
    resolvedAt = row.get("resolvedAt")
    if resolvedAt is not None and resolvedAt <= decisionTs:
        return
    if decisionTs > endTs:
        return
    held = sum(lot.usd for lot in book.openLots.get(key, ()))
    shares = orderShares(theirShares, ourPrice, params, book.exposure, positionUsd=held)
    if shares <= 0 or ourPrice is None:
        return
    if action == "trigger":
        theirPrice = burst.usd / burst.shares
        theirUsd = burst.usd
    else:
        theirPrice = float(row["price"])
        theirUsd = float(row["size"]) * theirPrice
    _openLot(book, row, ourPrice, shares, params, theirPrice, theirUsd)
    burst.copying = True


def _resolveMarket(book: Book, marketId: str, winner: str, when: datetime) -> None:
    for key in list(book.openLots):
        if key[1] != marketId:
            continue
        staying: list[Lot] = []
        leaving: list[Lot] = []
        for lot in book.openLots[key]:
            if lot.decisionTs < when:
                leaving.append(lot)
            else:
                staying.append(lot)
        if not leaving:
            continue
        if staying:
            book.openLots[key] = staying
        else:
            book.openLots.pop(key, None)
            book.armed.discard(key)
        for lot in leaving:
            price = 1.0 if lot.outcome == winner else 0.0
            lot.exitTs = when
            lot.exitPrice = price
            lot.exitReason = "resolution"
            lot.marked = False
            book.exposure -= lot.usd
            book.closed.append(lot)
        if book.exposure < 1e-9:
            book.exposure = 0.0


def _markOpen(book: Book, tape: pl.DataFrame, endTs: datetime) -> None:
    stillOpen = [lot for lots in book.openLots.values() for lot in lots]
    book.openLots.clear()
    book.armed.clear()
    if not stillOpen:
        return
    prices: dict[int, float | None] = {}
    if tape.height:
        queries = _utc(
            pl.DataFrame(
                {
                    "tradeId": [lot.tradeId for lot in stillOpen],
                    "marketId": [lot.marketId for lot in stillOpen],
                    "outcome": [lot.outcome for lot in stillOpen],
                    "ts": [endTs for _ in stillOpen],
                }
            ),
            "ts",
        )
        priced = priceAt(tape, queries, stale=markHorizon)
        for row in priced.iter_rows(named=True):
            price = row["price"]
            prices[int(row["tradeId"])] = None if price is None else float(price)
    for lot in stillOpen:
        lot.exitTs = endTs
        lot.exitPrice = prices.get(lot.tradeId)
        lot.exitReason = "mark"
        lot.marked = True
        book.closed.append(lot)


def _fillPrices(
    prepared: Prepared,
    params: BacktestParams,
    cache: dict | None,
) -> tuple[dict[int, float | None], dict[int, float | None]]:
    key = (int(params.delaySec), float(params.slippageBps))
    store = cache if cache is not None else {}
    if key not in store:
        store[key] = (
            _prices(
                prepared.path, prepared.tape, params.delaySec, params.slippageBps, True, "rowId"
            ),
            _prices(
                prepared.path, prepared.tape, params.delaySec, params.slippageBps, False, "rowId"
            ),
        )
    return store[key]


def _replay(
    prepared: Prepared, params: BacktestParams, priceCache: dict | None = None
) -> list[Lot]:
    book = Book()
    buyPrices, exitPrices = _fillPrices(prepared, params, priceCache)
    events: list[tuple] = []
    if prepared.path.height:
        for row in prepared.path.iter_rows(named=True):
            events.append((row["ts"], 0, int(row["rowId"]), "fill", row))
        resolved = (
            prepared.path.select("marketId", "winner", "resolvedAt")
            .unique(subset=["marketId"], keep="first")
            .drop_nulls(["winner", "resolvedAt"])
        )
        for row in resolved.iter_rows(named=True):
            when = row["resolvedAt"]
            if when < prepared.startTs or when > prepared.endTs:
                continue
            events.append((when, 1, 0, "resolve", row))
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    for _ts, _order, _id, kind, row in events:
        if kind == "fill":
            key = (row["accountGroup"], row["marketId"], row["outcome"])
            book.net[key] = float(row["netShares"])
            book.lastPrice[key] = float(row["price"])
            _maybeExit(book, key, row["ts"], exitPrices.get(int(row["rowId"])), params)
            if row["side"] == "BUY":
                _onBuy(book, row, buyPrices.get(int(row["rowId"])), params, prepared.endTs)
        else:
            _resolveMarket(book, row["marketId"], row["winner"], row["resolvedAt"])
    _markOpen(book, prepared.tape, prepared.endTs)
    return book.closed


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _maxDrawdown(lots: Sequence[Lot]) -> float:
    ordered = sorted(
        (lot for lot in lots if lot.pnl is not None and lot.exitTs is not None),
        key=lambda lot: (lot.exitTs, lot.tradeId),
    )
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for lot in ordered:
        equity += lot.pnl or 0.0
        if equity > peak:
            peak = equity
        worst = max(worst, peak - equity)
    return worst


def _summarize(lots: Sequence[Lot], startTs: datetime, endTs: datetime, digest: str) -> dict:
    summary = _blankSummary(startTs, endTs, digest)
    if not lots:
        return summary
    ordered = sorted(lots, key=lambda lot: lot.tradeId)
    realized = [lot for lot in ordered if lot.pnl is not None]
    total = sum(lot.pnl or 0.0 for lot in realized)
    capital = sum(lot.usd for lot in ordered)
    byEvent: dict[str, float] = {}
    for lot in realized:
        byEvent[lot.eventSlug] = byEvent.get(lot.eventSlug, 0.0) + (lot.pnl or 0.0)
    byEvent = dict(sorted(byEvent.items()))
    capitalByEvent: dict[str, float] = {}
    for lot in ordered:
        capitalByEvent[lot.eventSlug] = capitalByEvent.get(lot.eventSlug, 0.0) + lot.usd
    capitalByEvent = dict(sorted(capitalByEvent.items()))
    if byEvent:
        topEvent, topPnl = sorted(byEvent.items(), key=lambda item: (-item[1], item[0]))[0]
    else:
        topEvent, topPnl = None, 0.0
    topCapital = capitalByEvent.get(topEvent, 0.0) if topEvent is not None else 0.0
    capitalExTop = capital - topCapital
    pnlExTop = total - topPnl
    eventReturns = [
        byEvent[event] / cap
        for event, cap in capitalByEvent.items()
        if cap > 0 and event in byEvent
    ]
    wins = sum(1 for lot in realized if (lot.pnl or 0.0) > 0)
    summary.update(
        {
            "totalPnl": total,
            "capitalDeployed": capital,
            "returnOnDeployed": None if capital == 0 else total / capital,
            "tradeCount": len(ordered),
            "winRate": None if not realized else wins / len(realized),
            "maxDrawdown": _maxDrawdown(ordered),
            "pnlByEvent": byEvent,
            "capitalByEvent": capitalByEvent,
            "topEvent": topEvent,
            "topEventPnl": topPnl,
            "topEventPnlShare": None if total == 0 else topPnl / total,
            "pnlWithoutTopEvent": pnlExTop,
            "capitalWithoutTopEvent": capitalExTop,
            "returnWithoutTopEvent": None if capitalExTop == 0 else pnlExTop / capitalExTop,
            "medianEventReturn": _median(eventReturns),
            "eventCount": len(capitalByEvent),
            "markedCount": sum(1 for lot in ordered if lot.marked),
        }
    )
    return summary


def _tradesFrame(lots: Sequence[Lot]) -> pl.DataFrame:
    if not lots:
        return _emptyTrades()
    rows = []
    for lot in sorted(lots, key=lambda item: item.tradeId):
        rows.append(
            {
                "tradeId": lot.tradeId,
                "accountGroup": lot.accountGroup,
                "account": lot.account,
                "marketId": lot.marketId,
                "eventSlug": lot.eventSlug,
                "question": lot.question,
                "outcome": lot.outcome,
                "entryTs": lot.entryTs,
                "exitTs": lot.exitTs,
                "theirPrice": lot.theirPrice,
                "theirUsd": lot.theirUsd,
                "entryPrice": lot.entryPrice,
                "exitPrice": lot.exitPrice,
                "shares": lot.shares,
                "usd": lot.usd,
                "pnl": lot.pnl,
                "exitReason": lot.exitReason,
                "marked": lot.marked,
            }
        )
    return _utc(_utc(pl.DataFrame(rows, schema=tradeSchema), "entryTs"), "exitTs")


def runPrepared(
    prepared: Prepared,
    params: BacktestParams,
    priceCache: dict | None = None,
) -> BacktestResult:
    digest = paramsHash(params)
    lots = _replay(prepared, params, priceCache)
    return BacktestResult(
        params=params,
        paramsHash=digest,
        trades=_tradesFrame(lots),
        summary=_summarize(lots, prepared.startTs, prepared.endTs, digest),
    )


def runBacktest(
    fills: pl.DataFrame | pl.LazyFrame,
    markets: pl.DataFrame,
    accountsToCopy: Sequence[str],
    params: BacktestParams,
    startTs: datetime,
    endTs: datetime,
    clusterMap: dict[str, str] | None = None,
    runsDir: str | Path | None = None,
) -> BacktestResult:
    prepared = prepareBacktest(fills, markets, accountsToCopy, startTs, endTs, clusterMap)
    result = runPrepared(prepared, params)
    if runsDir is not None:
        writeRun(result, runsDir)
    return result


def writeRun(result: BacktestResult, runsDir: str | Path = "runs") -> Path:
    out = Path(runsDir) / result.paramsHash
    out.mkdir(parents=True, exist_ok=True)
    payload = result.params.model_dump(mode="json")
    (out / "params.yaml").write_text(yaml.safe_dump(payload, sort_keys=True))
    result.trades.write_parquet(out / "trades.parquet")
    (out / "summary.json").write_text(json.dumps(result.summary, indent=2, sort_keys=True) + "\n")
    return out


def formatSummary(result: BacktestResult) -> str:
    summary = result.summary
    ret = summary["returnOnDeployed"]
    win = summary["winRate"]
    share = summary["topEventPnlShare"]
    lines = [
        f"run {result.paramsHash}",
        f"trades {summary['tradeCount']}  marked {summary['markedCount']}",
        f"totalPnl {summary['totalPnl']:.2f}",
        f"capitalDeployed {summary['capitalDeployed']:.2f}",
        f"returnOnDeployed {ret if ret is None else f'{ret:.4f}'}",
        f"winRate {win if win is None else f'{win:.4f}'}",
        f"maxDrawdown {summary['maxDrawdown']:.2f}",
        (
            f"topEvent {summary['topEvent']}  pnl {summary['topEventPnl']:.2f}  "
            f"share {share if share is None else f'{share:.4f}'}"
        ),
        f"pnlWithoutTopEvent {summary['pnlWithoutTopEvent']:.2f}",
        f"returnWithoutTopEvent {summary['returnWithoutTopEvent']}",
        f"medianEventReturn {summary['medianEventReturn']}",
        f"events {summary['eventCount']}",
    ]
    return "\n".join(lines)


def addMonths(day: date, months: int) -> date:
    index = day.month - 1 + months
    year = day.year + index // 12
    month = index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def rollingWindows(startDate: date, endDate: date, stepMonths: int = 1) -> list[tuple[date, date]]:
    """Half-open windows covering [startDate, endDate)."""
    if stepMonths < 1:
        raise ValueError("stepMonths must be at least 1")
    windows: list[tuple[date, date]] = []
    cursor = startDate
    while cursor < endDate:
        nxt = min(addMonths(cursor, stepMonths), endDate)
        if nxt <= cursor:
            break
        windows.append((cursor, nxt))
        cursor = nxt
    return windows


def _asDate(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


@dataclass
class WindowResult:
    start: date
    end: date
    accountCount: int
    summary: dict
    trades: pl.DataFrame


@dataclass
class RollingResult:
    windows: list[WindowResult]
    summary: dict
    trades: pl.DataFrame


def _lotsFromTrades(trades: pl.DataFrame) -> list[Lot]:
    lots: list[Lot] = []
    if trades.height == 0:
        return lots
    for row in trades.iter_rows(named=True):
        lots.append(
            Lot(
                tradeId=int(row["tradeId"]),
                accountGroup=row["accountGroup"],
                account=row["account"],
                marketId=row["marketId"],
                eventSlug=row["eventSlug"],
                question=row["question"] or "",
                outcome=row["outcome"],
                entryTs=row["entryTs"],
                decisionTs=row["entryTs"],
                theirPrice=float(row["theirPrice"]),
                theirUsd=float(row["theirUsd"]),
                entryPrice=float(row["entryPrice"]),
                shares=float(row["shares"]),
                usd=float(row["usd"]),
                exitTs=row["exitTs"],
                exitPrice=None if row["exitPrice"] is None else float(row["exitPrice"]),
                exitReason=row["exitReason"],
                marked=bool(row["marked"]),
            )
        )
    return lots


def runRolling(
    fills: pl.DataFrame | pl.LazyFrame,
    markets: pl.DataFrame,
    accountsByWindow: Mapping[date | datetime, Sequence[str]],
    params: BacktestParams,
    startDate: date,
    endDate: date,
    stepMonths: int = 1,
    clusterMap: dict[str, str] | None = None,
) -> RollingResult:
    """Backtest each month with the accounts supplied for that window. No discovery."""
    windows = rollingWindows(startDate, endDate, stepMonths)
    byWindow = {_asDate(key): accounts for key, accounts in accountsByWindow.items()}
    windowRuns: list[WindowResult] = []
    frames: list[pl.DataFrame] = []
    for start, end in windows:
        startTs = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        endMidnight = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
        endTs = endMidnight - timedelta(microseconds=1)
        accounts = [str(account) for account in byWindow.get(start, ())]
        result = runBacktest(fills, markets, accounts, params, startTs, endTs, clusterMap)
        windowRuns.append(
            WindowResult(
                start=start,
                end=end,
                accountCount=len(accounts),
                summary=result.summary,
                trades=result.trades,
            )
        )
        if result.trades.height:
            frames.append(
                result.trades.with_columns(pl.lit(start.isoformat()).alias("windowStart"))
            )
    if frames:
        combined = pl.concat(frames, how="diagonal_relaxed").drop("tradeId")
        combined = combined.sort(["exitTs", "entryTs", "account", "marketId"]).with_row_index(
            "tradeId"
        )
    else:
        combined = _emptyTrades()
    if windows:
        first, last = windows[0][0], windows[-1][1]
        overallStart = datetime(first.year, first.month, first.day, tzinfo=timezone.utc)
        overallEnd = datetime(last.year, last.month, last.day, tzinfo=timezone.utc)
    else:
        overallStart = datetime(startDate.year, startDate.month, startDate.day, tzinfo=timezone.utc)
        overallEnd = datetime(endDate.year, endDate.month, endDate.day, tzinfo=timezone.utc)
    summary = _summarize(_lotsFromTrades(combined), overallStart, overallEnd, paramsHash(params))
    return RollingResult(windows=windowRuns, summary=summary, trades=combined)


def loadMarketFills(dataDirs: Sequence[str | Path]) -> tuple[pl.LazyFrame, pl.DataFrame]:
    """Concatenate datasets. Fills dedupe on fetch keys; markets dedupe on marketId."""
    dirs = [Path(item) for item in dataDirs]
    if not dirs:
        raise ValueError("at least one data dir is required")
    fills = pl.concat(
        [pl.scan_parquet(item / "fills.parquet") for item in dirs],
        how="diagonal_relaxed",
    ).unique(subset=list(fillDedupeKeys), keep="last")
    markets = pl.concat(
        [pl.read_parquet(item / "markets.parquet") for item in dirs],
        how="diagonal_relaxed",
    ).unique(subset=["marketId"], keep="first")
    return fills, markets


def _firstExisting(dirs: Sequence[Path], name: str) -> Path | None:
    for item in dirs:
        candidate = Path(item) / name
        if candidate.exists():
            return candidate
    return None


def resolveDataDirs(root: Path, requested: Sequence[str] | None, fallback: str) -> list[Path]:
    names = list(requested) if requested else [fallback]
    dirs = []
    for name in names:
        path = Path(name)
        dirs.append(path if path.is_absolute() else root / path)
    return dirs


def loadInputs(
    dataDirs: Sequence[str | Path],
) -> tuple[pl.LazyFrame, pl.DataFrame, list[str], dict[str, str] | None]:
    fills, markets = loadMarketFills(dataDirs)
    suspicious = _firstExisting(dataDirs, "suspicious.parquet")
    if suspicious is None:
        raise FileNotFoundError("suspicious.parquet not found in the data dirs")
    accounts = readCopyAccounts(suspicious)
    clusterFile = _firstExisting(dataDirs, "clusterAccounts.parquet")
    clusterMap = readClusterMap(clusterFile) if clusterFile else None
    return fills, markets, accounts, clusterMap


def readCopyAccounts(path: str | Path) -> list[str]:
    frame = pl.read_parquet(path).filter(pl.col("suspicious"))
    return frame.get_column("account").to_list()


def readClusterMap(path: str | Path) -> dict[str, str] | None:
    file = Path(path)
    if not file.exists() or file.stat().st_size == 0:
        return None
    frame = pl.read_parquet(file, columns=["clusterId", "account"])
    if frame.height == 0:
        return None
    frame = frame.with_columns(pl.col("account").str.to_lowercase()).unique(
        subset=["account"], keep="first"
    )
    return dict(zip(frame["account"].to_list(), frame["clusterId"].to_list(), strict=True))
