from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from polycrawler.config import loadConfig
from polycrawler.discovery import labelRecall, labelRows, runDiscover
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
) -> None:
    """Flag suspicious accounts from fills before splitDate."""
    loaded = loadConfig(config, setOverrides or [])
    result = runDiscover(loaded, refresh=refresh)
    typer.echo(f"candidates {result.candidates}")
    typer.echo(f"suspicious {result.suspicious}")
    if result.prefilterNote:
        typer.echo(result.prefilterNote)
    if labels:
        markets = pl.read_parquet(Path(loaded.fetch.dataDir) / "markets.parquet")
        rows = labelRows(markets, result.frame, labels)
        flagged, eligible = labelRecall(rows)
        typer.echo(f"{'wallet':<42}  {'case':<18}  candidate  suspicious  signals")
        for row in rows:
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
    typer.echo("funding lookup and cluster grouping are pending (steps 2-3)")


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
