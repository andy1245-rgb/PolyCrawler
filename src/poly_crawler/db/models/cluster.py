from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin


class Cluster(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "clusters"

    parent_id: Mapped[UUID] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"), unique=True, nullable=False)
    cluster_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    score_variant: Mapped[str] = mapped_column(String(10), nullable=False, default="sqrt")
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sibling_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vetted_sibling_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    parent = relationship("Parent", back_populates="cluster")
    positions = relationship("ClusterPosition", back_populates="cluster", cascade="all, delete-orphan")
