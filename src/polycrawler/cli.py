from typing import Annotated

import typer

from polycrawler.config import loadConfig
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
def discover() -> None:
    """Score accounts and group them by funder."""
    typer.echo("not implemented yet")
    raise typer.Exit(1)


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
