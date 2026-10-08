from collections import defaultdict
from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from polycrawler.config import loadConfig
from polycrawler.discovery import FundingResult, labelRecall, labelRows, runDiscover, runFunding
from polycrawler.fetch import runFetch

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
    funding = runFunding(loaded, refresh=refresh, extraAccounts=extra)
    echoFunding(funding)
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


def echoLabelClusters(labels: list, funding: FundingResult) -> None:
    byAccount = {
        row["account"]: row
        for row in funding.members.iter_rows(named=True)
    } if funding.members.height else {}
    parentByCluster = {
        row["clusterId"]: row["parent"]
        for row in funding.parents.iter_rows(named=True)
    } if funding.parents.height else {}
    labeledByCluster: dict[str, list[str]] = defaultdict(list)
    for label in labels:
        hit = byAccount.get(label.wallet)
        if hit is not None:
            labeledByCluster[hit["clusterId"]].append(label.wallet)
    typer.echo(f"{'wallet':<42}  {'case':<18}  cluster  parent  labeledWith")
    for label in labels:
        hit = byAccount.get(label.wallet)
        if hit is None:
            typer.echo(f"{label.wallet:<42}  {label.case:<18}  -")
            continue
        others = [item for item in labeledByCluster[hit["clusterId"]] if item != label.wallet]
        typer.echo(
            f"{label.wallet:<42}  {label.case:<18}  {hit['clusterId']}  "
            f"{parentByCluster.get(hit['clusterId'], '-')}  "
            f"{', '.join(others) if others else '-'}"
        )


@app.command()
def backtest() -> None:
    """Copy discovered clusters after splitDate."""
    typer.echo("not implemented yet")
    raise typer.Exit(1)


@app.command()
def sweep(sweepFile: Annotated[str | None, typer.Argument()] = None) -> None:
    """Run a grid of discover + backtest configs."""
    typer.echo("not implemented yet")
    raise typer.Exit(1)
