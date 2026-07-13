"""Unit tests for parent / cluster repository (Phase 1)."""

import pytest
from sqlalchemy.exc import IntegrityError

from poly_crawler.db.repositories import parent_repo as repo

VALID_A = "0x" + "a" * 40
VALID_B = "0x" + "b" * 40
INVALID = "not-an-address"


@pytest.mark.asyncio
async def test_create_parent_and_cluster(session):
    parent, created = await repo.seed_parent(session, VALID_A)
    assert created is True
    assert parent.chain_address == repo.normalize_address(VALID_A)
    assert parent.is_ignored is False
    assert parent.cluster is not None
    assert parent.cluster.cluster_score == 0.0
    assert parent.cluster.score_variant == "sqrt"


@pytest.mark.asyncio
async def test_duplicate_seed_skips(session):
    first, created1 = await repo.seed_parent(session, VALID_A)
    second, created2 = await repo.seed_parent(session, VALID_A.lower())
    assert created1 is True
    assert created2 is False
    assert first.id == second.id


@pytest.mark.asyncio
async def test_create_parent_integrity_error(session):
    await repo.create_parent(session, VALID_A)
    await session.commit()
    with pytest.raises(IntegrityError):
        await repo.create_parent(session, VALID_A)


@pytest.mark.asyncio
async def test_get_parent_by_address(session):
    await repo.seed_parent(session, VALID_A)
    found = await repo.get_parent_by_address(session, VALID_A)
    missing = await repo.get_parent_by_address(session, VALID_B)
    assert found is not None
    assert found.cluster is not None
    assert missing is None


@pytest.mark.asyncio
async def test_list_parents_filters_ignored(session):
    await repo.seed_parent(session, VALID_A)
    await repo.seed_parent(session, VALID_B)
    await repo.ignore_parent(session, VALID_B)

    active = await repo.list_parents(session, include_ignored=False)
    all_parents = await repo.list_parents(session, include_ignored=True)

    assert len(active) == 1
    assert active[0].chain_address == repo.normalize_address(VALID_A)
    assert len(all_parents) == 2


@pytest.mark.asyncio
async def test_ignore_parent_missing(session):
    with pytest.raises(LookupError):
        await repo.ignore_parent(session, VALID_A)


@pytest.mark.asyncio
async def test_invalid_address_rejected():
    with pytest.raises(repo.InvalidAddressError):
        repo.normalize_address(INVALID)


@pytest.mark.asyncio
async def test_create_cluster_for_parent(session):
    parent = await repo.create_parent(session, VALID_A)
    cluster = await repo.create_cluster_for_parent(session, parent.id)
    await session.commit()
    assert cluster.parent_id == parent.id
    assert cluster.sibling_count == 0
