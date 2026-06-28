"""Shared test fixtures — async engine, session, and factories."""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from poly_crawler.db.base import Base


@pytest_asyncio.fixture
async def engine():
    """Create an in-memory SQLite engine for unit tests."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session backed by the in-memory SQLite engine."""
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


# ---------------------------------------------------------------------------
# Factory helpers — build minimal model instances with sensible defaults.
# ---------------------------------------------------------------------------

@pytest.fixture
def parent_kwargs() -> dict:
    return {
        "id": uuid4(),
        "chain_address": "0x" + "a" * 40,
        "metadata_": {},
    }


@pytest.fixture
def account_kwargs(parent_kwargs) -> dict:
    return {
        "id": uuid4(),
        "polymarket_address": "0x" + "b" * 40,
        "parent_id": parent_kwargs["id"],
        "metadata_": {},
    }


@pytest.fixture
def cluster_kwargs(parent_kwargs) -> dict:
    return {
        "id": uuid4(),
        "parent_id": parent_kwargs["id"],
    }


@pytest.fixture
def session_kwargs() -> dict:
    return {
        "id": uuid4(),
        "mode": "paper",
        "review_mode": "manual",
        "config_snapshot": {},
        "started_at": datetime.now(timezone.utc),
        "status": "running",
    }


@pytest.fixture
def config_snapshot_kwargs() -> dict:
    return {
        "id": uuid4(),
        "config_json": {},
    }
