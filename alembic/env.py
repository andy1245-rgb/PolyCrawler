"""Alembic environment config for async SQLAlchemy."""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

# Import all models so they register on Base.metadata
import poly_crawler.db.models  # noqa: F401
from alembic import context
from poly_crawler.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DEFAULT_DATABASE_URL = "postgresql+asyncpg://polycrawler:polycrawler@localhost:5432/poly_crawler"


def _database_url() -> str:
    """Resolve DB URL: POLY_DATABASE_URL → DATABASE_URL → alembic.ini → local default."""
    return (
        os.environ.get("POLY_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
        or DEFAULT_DATABASE_URL
    )


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _database_url()
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
