"""Postgres integration checks — skipped when DB is unreachable."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_TABLES = {
    "parents",
    "accounts",
    "clusters",
    "cluster_positions",
    "alerts",
    "paper_trades",
    "sibling_balance_snapshots",
    "sessions",
    "config_snapshots",
    "rpc_logs",
    "backtest_runs",
}


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
async def postgres_url():
    url = _database_url()
    if not await _can_connect(url):
        pytest.skip("Postgres not available")
    return url


async def test_all_phase0_tables_exist(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                )
            )
            tables = {row[0] for row in result}
        assert EXPECTED_TABLES.issubset(tables), f"missing: {EXPECTED_TABLES - tables}"
        assert len(EXPECTED_TABLES) == 11
    finally:
        await engine.dispose()


async def test_alembic_at_head(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            version = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
        assert version == "0001"
    finally:
        await engine.dispose()
