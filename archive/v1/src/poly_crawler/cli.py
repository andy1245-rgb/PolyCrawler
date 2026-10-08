import asyncio
from typing import Optional

import typer

app = typer.Typer()


@app.command()
def seed(
    parent: Optional[list[str]] = typer.Option(
        None, "--parent", help="Parent wallet address (0x-prefixed). Repeat for multiple."
    ),
    from_file: Optional[str] = typer.Option(
        None, "--from-file", help="File with one address per line."
    ),
    list_parents: bool = typer.Option(False, "--list", help="Show all seeded parents."),
    ignore: Optional[str] = typer.Option(None, "--ignore", help="Mark a parent as ignored."),
) -> None:
    """Seed parent wallets into the database."""
    asyncio.run(
        _seed(parents=parent, from_file=from_file, list_parents=list_parents, ignore=ignore)
    )


async def _seed(
    parents: Optional[list[str]],
    from_file: Optional[str],
    list_parents: bool,
    ignore: Optional[str],
) -> None:
    # Phase 1: Seed parent wallets + create cluster rows.
    typer.echo("Seed command not implemented yet (Phase 1).")


@app.command()
def run() -> None:
    """Start the crawler (alias for uvicorn)."""
    import uvicorn

    uvicorn.run("poly_crawler.main:app", reload=True)
