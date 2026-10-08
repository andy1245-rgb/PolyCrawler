from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin


class Parent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "parents"

    chain_address: Mapped[str] = mapped_column(
        String(42), unique=True, nullable=False, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_ignored: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )

    accounts = relationship(
        "Account", back_populates="parent", cascade="all, delete-orphan"
    )
    cluster = relationship(
        "Cluster", back_populates="parent", uselist=False, cascade="all, delete-orphan"
    )
