"""Unit tests for parent/cluster repository (Phase 1)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from poly_crawler.db.models import Cluster, Parent
from poly_crawler.db.repositories import parent_repo


async def test_create_parent(session) -> None:
    parent = await parent_repo.create_parent(session, "0x" + "a" * 40)
    await session.commit()

    assert parent.chain_address.startswith("0x")
    assert parent.is_ignored is False
    assert parent.metadata_ == {}


async def test_create_parent_duplicate_address(session) -> None:
    address = "0x" + "b" * 40
    await parent_repo.create_parent(session, address)
    await session.commit()

    with pytest.raises(IntegrityError):
        await parent_repo.create_parent(session, address)
        await session.commit()


async def test_create_cluster_for_parent(session) -> None:
    parent = await parent_repo.create_parent(session, "0x" + "c" * 40)
    await session.flush()
    cluster = await parent_repo.create_cluster_for_parent(session, parent.id)
    await session.commit()

    assert isinstance(cluster, Cluster)
    assert cluster.parent_id == parent.id
    assert cluster.cluster_score == 0.0
    assert cluster.score_variant == "sqrt"


async def test_get_parent_by_address(session) -> None:
    created = await parent_repo.create_parent(session, "0x" + "d" * 40)
    await session.commit()

    found = await parent_repo.get_parent_by_address(session, "0x" + "d" * 40)
    assert found is not None
    assert found.id == created.id


async def test_get_parent_by_address_not_found(session) -> None:
    found = await parent_repo.get_parent_by_address(session, "0x" + "e" * 40)
    assert found is None


async def test_list_parents_excludes_ignored(session) -> None:
    active = await parent_repo.create_parent(session, "0x" + "f" * 40)
    ignored = await parent_repo.create_parent(session, "0x" + "1" * 40)
    await session.flush()
    await parent_repo.ignore_parent(session, ignored.chain_address)
    await session.commit()

    listed = await parent_repo.list_parents(session, include_ignored=False)
    ids = {p.id for p in listed}
    assert active.id in ids
    assert ignored.id not in ids

    all_parents = await parent_repo.list_parents(session, include_ignored=True)
    assert {p.id for p in all_parents} >= {active.id, ignored.id}


async def test_ignore_parent(session) -> None:
    parent = await parent_repo.create_parent(session, "0x" + "2" * 40)
    await session.commit()

    await parent_repo.ignore_parent(session, parent.chain_address)
    await session.commit()

    refreshed = await parent_repo.get_parent_by_address(session, parent.chain_address)
    assert refreshed is not None
    assert refreshed.is_ignored is True


async def test_seed_parent_with_cluster_skips_duplicate(session) -> None:
    address = "0x" + "3" * 40
    first, created_first = await parent_repo.seed_parent_with_cluster(session, address)
    second, created_second = await parent_repo.seed_parent_with_cluster(session, address)
    await session.commit()

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert isinstance(first, Parent)
