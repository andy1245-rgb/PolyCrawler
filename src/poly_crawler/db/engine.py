"""Async DB engine, session factory, and dependency."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config.schema import Config

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(config: Config, database_url: str | None = None) -> None:
    """Initialise the global async engine and session factory.

    Called once at startup. Resolution order for the database URL:
    1. Explicit *database_url* argument
    2. ``config.database_url`` (set via ``POLY_DATABASE_URL`` env or YAML)
    3. ``POLY_DATABASE_URL`` / ``DATABASE_URL`` environment variables
    4. ``postgresql+asyncpg://polycrawler:polycrawler@localhost:5432/poly_crawler``
       (local-dev default; override in production)
    """
    global _engine, _session_factory

    db_url = (
        database_url
        or config.database_url
        or os.environ.get("POLY_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://polycrawler:polycrawler@localhost:5432/poly_crawler"
    )
    _engine = create_async_engine(db_url, pool_size=5, max_overflow=10)
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )


async def close_engine() -> None:
    """Dispose the engine. Called at shutdown."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
    _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async session."""
    if _session_factory is None:
        raise RuntimeError("Engine not initialised — call init_engine() first")
    async with _session_factory() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """CLI / script helper: commit on success, rollback on error."""
    if _session_factory is None:
        raise RuntimeError("Engine not initialised — call init_engine() first")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
