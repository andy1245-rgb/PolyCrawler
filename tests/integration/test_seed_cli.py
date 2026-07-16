"""Integration tests for ``poly-crawler seed`` against Postgres."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from typer.testing import CliRunner

from poly_crawler.cli import app
from poly_crawler.db.models import Cluster, Parent

runner = CliRunner()

ADDR_A = "0x" + "a" * 40
ADDR_B = "0x" + "b" * 40
ADDR_C = "0x" + "c" * 40


def _database_url() -> str:
    return (
        os.environ.get("POLY_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://polycrawler:polycrawler@localhost:5432/poly_crawler"
    )


async def _can_connect(url: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest.fixture
async def postgres_ready():
    url = _database_url()
    if not await _can_connect(url):
        pytest.skip("Postgres not available")
    os.environ["POLY_DATABASE_URL"] = url
    yield url

    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(delete(Cluster))
            await conn.execute(delete(Parent))
    finally:
        await engine.dispose()


async def _has_cluster_for(url: str, address: str) -> bool:
    from eth_utils import to_checksum_address

    checksum = to_checksum_address(address)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            parent_id = (
                await conn.execute(
                    select(Parent.id).where(Parent.chain_address == checksum)
                )
            ).scalar_one_or_none()
            if parent_id is None:
                return False
            cluster_id = (
                await conn.execute(
                    select(Cluster.id).where(Cluster.parent_id == parent_id)
                )
            ).scalar_one_or_none()
            return cluster_id is not None
    finally:
        await engine.dispose()


def test_seed_single_parent(postgres_ready: str) -> None:
    result = runner.invoke(app, ["seed", "--parent", ADDR_A])
    assert result.exit_code == 0, result.output
    assert "Seeded 1" in result.output


def test_seed_creates_cluster_row(postgres_ready: str) -> None:
    result = runner.invoke(app, ["seed", "--parent", ADDR_A])
    assert result.exit_code == 0, result.output

    async def check() -> bool:
        return await _has_cluster_for(postgres_ready, ADDR_A)

    assert asyncio.run(check())


def test_seed_multiple_parents(postgres_ready: str) -> None:
    result = runner.invoke(app, ["seed", "--parent", ADDR_A, "--parent", ADDR_B])
    assert result.exit_code == 0, result.output
    assert "Seeded 2" in result.output


def test_seed_from_file(postgres_ready: str, tmp_path: Path) -> None:
    path = tmp_path / "parents.txt"
    path.write_text(f"{ADDR_A}\n# comment\n{ADDR_B}\n\n")
    result = runner.invoke(app, ["seed", "--from-file", str(path)])
    assert result.exit_code == 0, result.output
    assert "Seeded 2" in result.output


def test_seed_duplicate_skipped(postgres_ready: str) -> None:
    first = runner.invoke(app, ["seed", "--parent", ADDR_A])
    assert first.exit_code == 0
    second = runner.invoke(app, ["seed", "--parent", ADDR_A])
    assert second.exit_code == 0
    assert "already exists" in second.output.lower() or "skipped" in second.output.lower()
    assert "Seeded 0" in second.output


def test_seed_list(postgres_ready: str) -> None:
    runner.invoke(app, ["seed", "--parent", ADDR_A])
    result = runner.invoke(app, ["seed", "--list"])
    assert result.exit_code == 0, result.output
    assert ADDR_A.lower() in result.output.lower()


def test_seed_ignore(postgres_ready: str) -> None:
    runner.invoke(app, ["seed", "--parent", ADDR_C])
    result = runner.invoke(app, ["seed", "--ignore", ADDR_C])
    assert result.exit_code == 0, result.output
    assert "ignored" in result.output.lower()

    listed = runner.invoke(app, ["seed", "--list"])
    assert listed.exit_code == 0
    assert ADDR_C.lower() not in listed.output.lower()


def test_seed_invalid_address(postgres_ready: str) -> None:
    result = runner.invoke(app, ["seed", "--parent", "not-an-address"])
    assert result.exit_code != 0
    assert "invalid" in result.output.lower()
