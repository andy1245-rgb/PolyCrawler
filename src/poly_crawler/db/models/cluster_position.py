from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as UUIDType  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin


class ClusterPosition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cluster_positions"

    cluster_id: Mapped[UUID] = mapped_column(
        ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    market_id: Mapped[str] = mapped_column(String(64), nullable=False)
    market_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    market_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    market_tags: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=list, nullable=False
    )

    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="watching", index=True
    )
    net_exposure: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_known_net: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mirrored_yes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mirrored_no: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    sibling_balances: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    tp_sl_suspended: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    last_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_closed_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    config_snapshot_id: Mapped[UUID | None] = mapped_column(
        UUIDType(as_uuid=True),
        ForeignKey("config_snapshots.id"),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    cluster = relationship("Cluster", back_populates="positions")
    config_snapshot = relationship("ConfigSnapshot")
    trades = relationship(
        "PaperTrade", back_populates="position", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("cluster_id", "market_id", name="uq_cluster_position"),
    )
