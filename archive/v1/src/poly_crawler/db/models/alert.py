from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Double, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class Alert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("parents.id"), nullable=True, index=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    cluster_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clusters.id"), nullable=True, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    amount_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
    cluster_score_at_event: Mapped[float | None] = mapped_column(Double, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    is_false_positive: Mapped[bool | None] = mapped_column(
        Boolean, default=None, nullable=True, index=True
    )
