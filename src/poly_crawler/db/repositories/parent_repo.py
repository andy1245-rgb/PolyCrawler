"""Parent / cluster persistence helpers for manual seed (Phase 1)."""

from __future__ import annotations

from uuid import UUID

from eth_utils import is_address, to_checksum_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from poly_crawler.db.models import Cluster, Parent


class InvalidAddressError(ValueError):
    """Raised when a wallet address fails Ethereum address validation."""


def normalize_address(chain_address: str) -> str:
    """Validate and return a checksummed 0x address."""
    candidate = chain_address.strip()
    if not is_address(candidate):
        raise InvalidAddressError(f"Invalid Ethereum address: {chain_address!r}")
    return to_checksum_address(candidate)


async def create_parent(session: AsyncSession, chain_address: str) -> Parent:
    parent = Parent(
        chain_address=normalize_address(chain_address),
        is_ignored=False,
        metadata_={},
    )
    session.add(parent)
    await session.flush()
    return parent


async def create_cluster_for_parent(session: AsyncSession, parent_id: UUID) -> Cluster:
    cluster = Cluster(
        parent_id=parent_id,
        cluster_score=0.0,
        score_variant="sqrt",
        sibling_count=0,
        vetted_sibling_count=0,
    )
    session.add(cluster)
    await session.flush()
    return cluster


async def get_parent_by_address(session: AsyncSession, chain_address: str) -> Parent | None:
    normalized = normalize_address(chain_address)
    result = await session.execute(
        select(Parent).where(Parent.chain_address == normalized)
    )
    return result.scalar_one_or_none()


async def list_parents(
    session: AsyncSession, *, include_ignored: bool = False
) -> list[Parent]:
    stmt = select(Parent).order_by(Parent.created_at.asc())
    if not include_ignored:
        stmt = stmt.where(Parent.is_ignored.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def ignore_parent(session: AsyncSession, chain_address: str) -> Parent:
    parent = await get_parent_by_address(session, chain_address)
    if parent is None:
        raise LookupError(f"Parent not found: {chain_address}")
    parent.is_ignored = True
    await session.flush()
    return parent


async def seed_parent_with_cluster(
    session: AsyncSession, chain_address: str
) -> tuple[Parent, bool]:
    """Insert parent + cluster if new.

    Returns ``(parent, created)`` where ``created`` is False when the address
    already existed (cluster is ensured if somehow missing).
    """
    existing = await get_parent_by_address(session, chain_address)
    if existing is not None:
        result = await session.execute(
            select(Cluster).where(Cluster.parent_id == existing.id)
        )
        if result.scalar_one_or_none() is None:
            await create_cluster_for_parent(session, existing.id)
        return existing, False

    parent = await create_parent(session, chain_address)
    await create_cluster_for_parent(session, parent.id)
    return parent, True
