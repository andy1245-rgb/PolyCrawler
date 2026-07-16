"""PolyCrawler CLI — seed parents and run the API process."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from poly_crawler.config import load_config
from poly_crawler.db import close_engine, init_engine
from poly_crawler.db.engine import session_scope
from poly_crawler.db.models import Parent
from poly_crawler.db.repositories import parent_repo
from poly_crawler.db.repositories.parent_repo import InvalidAddressError

app = typer.Typer(no_args_is_help=True)


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


def _read_addresses_from_file(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    addresses: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        addresses.append(stripped)
    return addresses


async def _seed(
    parents: Optional[list[str]],
    from_file: Optional[str],
    list_parents: bool,
    ignore: Optional[str],
) -> None:
    config = load_config()
    init_engine(config)
    try:
        if list_parents:
            await _list_parents()
            return
        if ignore:
            await _ignore_parent(ignore)
            return

        addresses: list[str] = list(parents or [])
        if from_file:
            addresses.extend(_read_addresses_from_file(from_file))

        if not addresses:
            typer.echo(
                "Nothing to do. Pass --parent, --from-file, --list, or --ignore.",
                err=True,
            )
            raise typer.Exit(code=1)

        await _seed_addresses(addresses)
    finally:
        await close_engine()


async def _seed_addresses(addresses: list[str]) -> None:
    created_count = 0
    skipped_count = 0
    try:
        async with session_scope() as session:
            for address in addresses:
                _parent, created = await parent_repo.seed_parent_with_cluster(
                    session, address
                )
                if created:
                    created_count += 1
                    typer.echo(f"Seeded {_parent.chain_address}")
                else:
                    skipped_count += 1
                    typer.echo(f"Skipped (already exists): {_parent.chain_address}")
    except InvalidAddressError as exc:
        typer.echo(f"Invalid address: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Seeded {created_count} parent(s)"
        + (f", skipped {skipped_count}." if skipped_count else ".")
        + " Use --list to view."
    )


async def _list_parents() -> None:
    async with session_scope() as session:
        result = await session.execute(
            select(Parent)
            .options(selectinload(Parent.cluster))
            .where(Parent.is_ignored.is_(False))
            .order_by(Parent.created_at.asc())
        )
        parents = list(result.scalars().all())

    if not parents:
        typer.echo("No seeded parents.")
        return

    typer.echo(f"{'ADDRESS':<44}  {'SCORE':>8}  VARIANT")
    for parent in parents:
        score = parent.cluster.cluster_score if parent.cluster else 0.0
        variant = parent.cluster.score_variant if parent.cluster else "-"
        typer.echo(f"{parent.chain_address:<44}  {score:>8.2f}  {variant}")


async def _ignore_parent(address: str) -> None:
    try:
        async with session_scope() as session:
            parent = await parent_repo.ignore_parent(session, address)
            typer.echo(f"Ignored parent: {parent.chain_address}")
    except InvalidAddressError as exc:
        typer.echo(f"Invalid address: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except LookupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def run() -> None:
    """Start the crawler (alias for uvicorn)."""
    import uvicorn

    uvicorn.run("poly_crawler.main:app", reload=True)
