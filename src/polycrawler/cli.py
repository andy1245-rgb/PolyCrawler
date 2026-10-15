import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from polycrawler.backtest import (
    BacktestParams,
    dirsFromConfig,
    formatSummary,
    loadInputs,
    prepareBacktest,
    runBacktest,
)
from polycrawler.config import loadConfig
from polycrawler.discovery import FundingResult, labelRecall, labelRows, runDiscover, runFunding
from polycrawler.fetch import runFetch
from polycrawler.sweep import formatSweep, loadSweep, runSweep, writeSweep

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def fetch(
    config: Annotated[str, typer.Option("--config")] = "configs/base.yaml",
    setOverrides: Annotated[list[str] | None, typer.Option("--set")] = None,
    eventSlug: Annotated[list[str] | None, typer.Option("--event-slug")] = None,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
) -> None:
    """Download markets and fills into data/."""
    loaded = loadConfig(config, setOverrides or [])
    usingSlugs = eventSlug if eventSlug else loaded.fetch.eventSlugs
    if not usingSlugs:
        typer.echo(f"no event slugs; fetching tags {', '.join(loaded.fetch.marketTags)}")
    summary = runFetch(loaded, eventSlugs=eventSlug, refresh=refresh)
    typer.echo(f"markets {summary.markets}")
    typer.echo(f"fills {summary.fills}")
    typer.echo(f"accounts {summary.accounts}")


@app.command()
def discover(
    config: Annotated[str, typer.Option("--config")] = "configs/base.yaml",
    setOverrides: Annotated[list[str] | None, typer.Option("--set")] = None,
    labels: Annotated[str | None, typer.Option("--labels")] = None,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    step1Only: Annotated[bool, typer.Option("--step1-only")] = False,
) -> None:
    """Flag suspicious accounts, then trace funding and write clusters."""
    loaded = loadConfig(config, setOverrides or [])
    result = runDiscover(loaded, refresh=refresh)
    typer.echo(f"candidates {result.candidates}")
    typer.echo(f"suspicious {result.suspicious}")
    if result.prefilterNote:
        typer.echo(result.prefilterNote)
    labelTable = None
    if labels:
        markets = pl.read_parquet(Path(loaded.fetch.dataDir) / "markets.parquet")
        labelTable = labelRows(markets, result.frame, labels)
        flagged, eligible = labelRecall(labelTable)
        typer.echo(f"{'wallet':<42}  {'case':<18}  candidate  suspicious  signals")
        for row in labelTable:
            typer.echo(
                f"{row.wallet:<42}  {row.case:<18}  "
                f"{'yes' if row.candidate else 'no':<9}  "
                f"{'yes' if row.suspicious else 'no':<10}  "
                f"{row.signals}"
                f"{'' if row.caseInData else '  (case markets not in data)'}"
            )
        if eligible:
            typer.echo(f"recall {flagged}/{eligible}")
        else:
            typer.echo("recall n/a (no labeled case markets in data)")
    if step1Only:
        return
    extra = [row.wallet for row in labelTable] if labelTable else []
    started = time.perf_counter()
    funding = runFunding(loaded, refresh=refresh, extraAccounts=extra)
    echoFunding(funding)
    typer.echo(f"discover seconds {time.perf_counter() - started:.1f}")
    if labelTable is not None:
        echoLabelClusters(labelTable, funding)


def echoFunding(funding: FundingResult) -> None:
    typer.echo(f"accounts traced {funding.traced}")
    typer.echo(f"hubs {len(funding.hubs)}")
    for hub in funding.hubs:
        typer.echo(
            f"hub {hub.address} counterparties {hub.counterparties} accounts {hub.accounts}"
        )
    typer.echo(f"clusters {funding.clusters}")
    if funding.parents.height:
        for row in funding.parents.iter_rows(named=True):
            typer.echo(
                f"cluster {row['clusterId']} parent {row['parent']} "
                f"suspicious {row['suspiciousCount']} accounts {row['accountCount']} "
                f"links {row['linkTypes']}"
            )
    collateral = " ".join(
        f"{name} {count}" for name, count in sorted(funding.collateralCounts.items())
    )
    typer.echo(f"collateral {collateral}" if collateral else "collateral none")
    typer.echo(f"funding rows {funding.fundingRows}")
    typer.echo(f"skipped polymarket {funding.skippedPolymarket}")
    if funding.otherTokens:
        shown = ", ".join(f"{name} {count}" for name, count in funding.otherTokens)
        typer.echo(f"other incoming {shown}")
    typer.echo(f"etherscan fetched {funding.fetched} cached {funding.cached}")
    typer.echo(
        f"origins {funding.origins} users {funding.originUsers} "
        f"unresolved {funding.unresolvedOrigins} deposits {funding.bridgeDeposits}"
    )
    typer.echo(f"origin chains {funding.originChainText or '-'}")
    if funding.bridgeHubs:
        typer.echo(f"bridge hubs {' '.join(funding.bridgeHubs)}")
    typer.echo(
        f"siblings {funding.siblings} outsideSuspicious {funding.siblingsOutside} "
        f"firstAfterSplit {funding.siblingsAfterSplit}"
    )
    typer.echo(f"coTrade edges {funding.coTradeEdges}")
    counts: Counter[str] = Counter()
    if funding.members.height:
        for row in funding.members.iter_rows(named=True):
            for kind in str(row["linkType"]).split(","):
                if kind:
                    counts[kind] += 1
    if counts:
        typer.echo("link accounts " + " ".join(f"{kind} {counts[kind]}" for kind in sorted(counts)))
    else:
        typer.echo("link accounts none")
    typer.echo(
        f"relay calls {funding.relayCalls} cache {funding.relayCacheHits} "
        f"rateLimits {funding.relayRateLimits} seconds {funding.relaySeconds:.1f}"
    )
    if funding.alchemyBlock is not None:
        typer.echo(
            f"alchemy block {funding.alchemyBlock} payoutConfirmed {funding.alchemyPayoutConfirmed}"
        )


def echoLabelClusters(labels: list, funding: FundingResult) -> None:
    byAccount = {
        row["account"]: row
        for row in funding.members.iter_rows(named=True)
    } if funding.members.height else {}
    byCluster = {
        row["clusterId"]: row
        for row in funding.parents.iter_rows(named=True)
    } if funding.parents.height else {}
    labeledByCluster: dict[str, list[str]] = defaultdict(list)
    for label in labels:
        hit = byAccount.get(label.wallet)
        if hit is not None:
            labeledByCluster[hit["clusterId"]].append(label.wallet)
    typer.echo(f"{'wallet':<42}  {'case':<18}  {'cluster':<12}  size  links  parent")
    for label in labels:
        hit = byAccount.get(label.wallet)
        if hit is None:
            typer.echo(f"{label.wallet:<42}  {label.case:<18}  -")
            continue
        cluster = byCluster.get(hit["clusterId"], {})
        size = cluster.get("accountCount", "-")
        links = hit["linkType"]
        parent = cluster.get("parent", "-")
        typer.echo(
            f"{label.wallet:<42}  {label.case:<18}  {hit['clusterId']:<12}  "
            f"{size}  {links}  {parent}"
        )


@app.command()
def backtest(
    config: Annotated[str, typer.Option("--config")] = "configs/insiderCases.yaml",
    setOverrides: Annotated[list[str] | None, typer.Option("--set")] = None,
    dataDir: Annotated[list[str] | None, typer.Option("--data-dir")] = None,
    runsDir: Annotated[str, typer.Option("--runs-dir")] = "runs",
) -> None:
    """Run one backtest from a config file and the local parquet tape."""
    root = Path.cwd()
    configPath = Path(config)
    if not configPath.is_absolute():
        configPath = root / configPath
    loaded = loadConfig(str(configPath), setOverrides or [])
    params = BacktestParams.model_validate(loaded.strategy.model_dump())
    dirs = dirsFromConfig(root, dataDir or None, loaded)
    fills, markets, accounts, clusterMap = loadInputs(dirs)
    endTs = fills.select(pl.col("ts").max()).collect().item()
    startTs = datetime(
        loaded.splitDate.year, loaded.splitDate.month, loaded.splitDate.day, tzinfo=timezone.utc
    )
    result = runBacktest(
        fills,
        markets,
        accounts,
        params,
        startTs,
        endTs,
        clusterMap=clusterMap,
        runsDir=root / runsDir,
    )
    typer.echo(formatSummary(result))
    typer.echo(f"wrote {root / runsDir / result.paramsHash}")


@app.command()
def sweep(
    sweepFile: Annotated[str, typer.Argument()] = "configs/sweeps/basic.yaml",
    config: Annotated[str, typer.Option("--config")] = "configs/insiderCases.yaml",
    dataDir: Annotated[list[str] | None, typer.Option("--data-dir")] = None,
    runsDir: Annotated[str, typer.Option("--runs-dir")] = "runs",
    limit: Annotated[int, typer.Option("--limit")] = 25,
) -> None:
    """Run a grid of backtest configs and rank them."""
    root = Path.cwd()
    configPath = Path(config)
    sweepPath = Path(sweepFile)
    if not configPath.is_absolute():
        configPath = root / configPath
    if not sweepPath.is_absolute():
        sweepPath = root / sweepPath
    loaded = loadConfig(str(configPath))
    spec = loadSweep(sweepPath)
    params = BacktestParams.model_validate(loaded.strategy.model_dump())
    dirs = dirsFromConfig(root, dataDir or None, loaded)
    fills, markets, accounts, clusterMap = loadInputs(dirs)
    endTs = fills.select(pl.col("ts").max()).collect().item()
    startTs = datetime(
        loaded.splitDate.year, loaded.splitDate.month, loaded.splitDate.day, tzinfo=timezone.utc
    )
    prepared = prepareBacktest(fills, markets, accounts, startTs, endTs, clusterMap)
    ranked = runSweep(prepared, params, spec.grid, spec.objective, spec.minTrades, spec.minEvents)
    out = writeSweep(ranked, spec.name, root / runsDir)
    kept = int(ranked.filter(pl.col("eligible")).height) if ranked.height else 0
    typer.echo(formatSweep(ranked, spec.objective, limit=limit))
    typer.echo(
        f"wrote {out}  ({ranked.height} runs, {kept} eligible, "
        f"objective {spec.objective}, minTrades {spec.minTrades}, minEvents {spec.minEvents})"
    )
