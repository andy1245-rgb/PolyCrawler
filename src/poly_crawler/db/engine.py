"""Async DB engine, session factory, and dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config.schema import Config

_engine = None
_session_factory = None


def init_engine(config: Config, database_url: str | None = None):
    """Initialise the global async engine and session factory.

    Called once at startup. Uses the provided *database_url* or falls back
    to ``POLY_DATABASE_URL`` / ``DATABASE_URL`` environment variables.
    """
    global _engine, _session_factory

    db_url = database_url or "postgresql+asyncpg://localhost:5432/poly_crawler"
    _engine = create_async_engine(db_url, pool_size=5, max_overflow=10)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def close_engine():
    """Dispose the engine. Called at shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async session."""
    if _session_factory is None:
        raise RuntimeError("Engine not initialised — call init_engine() first")
    async with _session_factory() as session:
        yield session
