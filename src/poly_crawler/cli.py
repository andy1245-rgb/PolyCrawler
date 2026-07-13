"""CLI seed command — Phase 1."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from poly_crawler.config.loader import load_config
from poly_crawler.db.engine import close_engine, get_session_factory, init_engine
from poly_crawler.db.repositories import parent_repo as repo

app = typer.Typer(add_completion=False)


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
    config = load_config()
    init_engine(config)
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            if list_parents:
                rows = await repo.list_parents(session, include_ignored=True)
                if not rows:
                    typer.echo("No parents seeded.")
                    return
                for row in rows:
                    score = row.cluster.cluster_score if row.cluster else 0.0
                    ignored = " [ignored]" if row.is_ignored else ""
                    typer.echo(f"{row.chain_address}  score={score}{ignored}")
                return

            if ignore:
                try:
                    parent_row = await repo.ignore_parent(session, ignore)
                except repo.InvalidAddressError as exc:
                    typer.echo(f"Error: {exc}", err=True)
                    raise typer.Exit(code=1) from exc
                except LookupError as exc:
                    typer.echo(f"Error: {exc}", err=True)
                    raise typer.Exit(code=1) from exc
                typer.echo(f"Ignored {parent_row.chain_address}")
                return

            addresses = list(parents or [])
            if from_file:
                path = Path(from_file)
                if not path.exists():
                    typer.echo(f"Error: file not found: {from_file}", err=True)
                    raise typer.Exit(code=1)
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        addresses.append(line)

            if not addresses:
                typer.echo(
                    "Error: provide --parent, --from-file, --list, or --ignore",
                    err=True,
                )
                raise typer.Exit(code=1)

            created_count = 0
            skipped_count = 0
            for address in addresses:
                try:
                    _parent, created = await repo.seed_parent(session, address)
                except repo.InvalidAddressError as exc:
                    typer.echo(f"Error: {exc}", err=True)
                    raise typer.Exit(code=1) from exc
                if created:
                    created_count += 1
                    typer.echo(f"Seeded {_parent.chain_address}")
                else:
                    skipped_count += 1
                    typer.echo(f"Skipped duplicate {_parent.chain_address}")

            typer.echo(f"Done. created={created_count} skipped={skipped_count}")
    finally:
        await close_engine()


@app.command()
def run() -> None:
    """Start the crawler (alias for uvicorn)."""
    import uvicorn

    uvicorn.run("poly_crawler.main:app", reload=True)
