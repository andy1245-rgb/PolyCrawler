"""Parent / cluster repository — Phase 1 seed operations."""

from __future__ import annotations

from uuid import UUID

from eth_utils import is_hex_address, to_checksum_address  # type: ignore[attr-defined]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from poly_crawler.db.models.cluster import Cluster
from poly_crawler.db.models.parent import Parent


class InvalidAddressError(ValueError):
    """Raised when a wallet address fails hex / checksum validation."""


def normalize_address(chain_address: str) -> str:
    """Validate and return EIP-55 checksummed address."""
    candidate = chain_address.strip()
    if not is_hex_address(candidate):
        raise InvalidAddressError(f"Invalid Ethereum address: {chain_address!r}")
    return to_checksum_address(candidate)


async def get_parent_by_address(
    session: AsyncSession, chain_address: str
) -> Parent | None:
    address = normalize_address(chain_address)
    result = await session.execute(
        select(Parent)
        .options(selectinload(Parent.cluster))
        .where(Parent.chain_address == address)
    )
    return result.scalar_one_or_none()


async def create_parent(session: AsyncSession, chain_address: str) -> Parent:
    """Insert a parent row. Caller should create the cluster separately."""
    address = normalize_address(chain_address)
    parent = Parent(chain_address=address, is_ignored=False, metadata_={})
    session.add(parent)
    await session.flush()
    return parent


async def create_cluster_for_parent(
    session: AsyncSession, parent_id: UUID
) -> Cluster:
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


async def seed_parent(session: AsyncSession, chain_address: str) -> tuple[Parent, bool]:
    """Create parent + cluster if new.

    Returns ``(parent, created)`` where ``created`` is False when the address
    already existed (duplicate skip).
    """
    existing = await get_parent_by_address(session, chain_address)
    if existing is not None:
        return existing, False

    parent = await create_parent(session, chain_address)
    await create_cluster_for_parent(session, parent.id)
    await session.commit()
    # Refresh with cluster relationship
    refreshed = await get_parent_by_address(session, parent.chain_address)
    assert refreshed is not None
    return refreshed, True


async def list_parents(
    session: AsyncSession, *, include_ignored: bool = False
) -> list[Parent]:
    stmt = select(Parent).options(selectinload(Parent.cluster)).order_by(
        Parent.created_at.asc()
    )
    if not include_ignored:
        stmt = stmt.where(Parent.is_ignored.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def ignore_parent(session: AsyncSession, chain_address: str) -> Parent:
    parent = await get_parent_by_address(session, chain_address)
    if parent is None:
        raise LookupError(f"Parent not found: {chain_address}")
    parent.is_ignored = True
    await session.commit()
    return parent
