"""Unit tests for ORM models against in-memory SQLite."""

from __future__ import annotations

from poly_crawler.db.models import (
    Account,
    Cluster,
    ClusterPosition,
    ConfigSnapshot,
    Parent,
    Session,
)


async def test_create_parent_account_cluster(
    session, parent_kwargs, account_kwargs, cluster_kwargs
) -> None:
    parent = Parent(**parent_kwargs)
    session.add(parent)
    await session.flush()

    account = Account(**account_kwargs)
    cluster = Cluster(**cluster_kwargs)
    session.add_all([account, cluster])
    await session.commit()

    assert parent.chain_address.startswith("0x")
    assert account.parent_id == parent.id
    assert cluster.parent_id == parent.id
    assert cluster.cluster_score == 0.0


async def test_session_and_config_snapshot(
    session, session_kwargs, config_snapshot_kwargs
) -> None:
    snap = ConfigSnapshot(**config_snapshot_kwargs)
    trading_session = Session(**session_kwargs)
    session.add_all([snap, trading_session])
    await session.commit()

    assert snap.config_json == {}
    assert trading_session.mode == "paper"
    assert trading_session.review_mode == "live_only"
    assert trading_session.status == "running"


async def test_cluster_position_json_fields(
    session, parent_kwargs, cluster_kwargs, config_snapshot_kwargs
) -> None:
    parent = Parent(**parent_kwargs)
    cluster = Cluster(**cluster_kwargs)
    snap = ConfigSnapshot(**config_snapshot_kwargs)
    session.add_all([parent, cluster, snap])
    await session.flush()

    position = ClusterPosition(
        cluster_id=cluster.id,
        market_id="0xmarket",
        market_tags=["politics"],
        sibling_balances={"0xabc": {"yes": 100, "no": 0}},
        config_snapshot_id=snap.id,
    )
    session.add(position)
    await session.commit()

    assert position.market_tags == ["politics"]
    assert position.sibling_balances["0xabc"]["yes"] == 100
    assert position.state == "watching"
