"""Integration tests for ``poly-crawler seed`` CLI (Phase 1)."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

import poly_crawler.db.models  # noqa: F401
from poly_crawler.cli import app
from poly_crawler.db.base import Base
from poly_crawler.db.repositories import parent_repo as repo

VALID_A = "0x" + "a" * 40
VALID_B = "0x" + "b" * 40
VALID_C = "0x" + "c" * 40

runner = CliRunner()


@pytest.fixture
def sqlite_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("POLY_DATABASE_URL", url)
    return url


async def _prepare_schema(url: str) -> None:
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await eng.dispose()


async def _get_parent(url: str, address: str):
    eng = create_async_engine(url)
    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        parent = await repo.get_parent_by_address(session, address)
    await eng.dispose()
    return parent


def test_seed_single_parent(sqlite_url: str):
    asyncio.run(_prepare_schema(sqlite_url))
    result = runner.invoke(app, ["seed", "--parent", VALID_A])
    assert result.exit_code == 0, result.output
    assert "Seeded" in result.output
    assert "created=1" in result.output

    parent = asyncio.run(_get_parent(sqlite_url, VALID_A))
    assert parent is not None
    assert parent.cluster is not None
    assert parent.cluster.score_variant == "sqrt"


def test_seed_multiple_and_duplicate_skip(sqlite_url: str):
    asyncio.run(_prepare_schema(sqlite_url))
    result = runner.invoke(app, ["seed", "--parent", VALID_A, "--parent", VALID_B])
    assert result.exit_code == 0, result.output
    assert "created=2" in result.output

    dup = runner.invoke(app, ["seed", "--parent", VALID_A])
    assert dup.exit_code == 0, dup.output
    assert "skipped=1" in dup.output


def test_seed_from_file(sqlite_url: str, tmp_path: Path):
    asyncio.run(_prepare_schema(sqlite_url))
    parents_file = tmp_path / "parents.txt"
    parents_file.write_text(f"{VALID_A}\n# comment\n{VALID_C}\n")

    result = runner.invoke(app, ["seed", "--from-file", str(parents_file)])
    assert result.exit_code == 0, result.output
    assert "created=2" in result.output


def test_seed_list(sqlite_url: str):
    asyncio.run(_prepare_schema(sqlite_url))
    runner.invoke(app, ["seed", "--parent", VALID_A])
    result = runner.invoke(app, ["seed", "--list"])
    assert result.exit_code == 0, result.output
    assert repo.normalize_address(VALID_A) in result.output
    assert "score=0.0" in result.output


def test_seed_ignore(sqlite_url: str):
    asyncio.run(_prepare_schema(sqlite_url))
    runner.invoke(app, ["seed", "--parent", VALID_A])
    result = runner.invoke(app, ["seed", "--ignore", VALID_A])
    assert result.exit_code == 0, result.output
    assert "Ignored" in result.output

    parent = asyncio.run(_get_parent(sqlite_url, VALID_A))
    assert parent is not None
    assert parent.is_ignored is True


def test_seed_invalid_address(sqlite_url: str):
    asyncio.run(_prepare_schema(sqlite_url))
    result = runner.invoke(app, ["seed", "--parent", "not-valid"])
    assert result.exit_code == 1
    assert "Invalid Ethereum address" in result.output
