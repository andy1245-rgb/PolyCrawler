from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin


class Account(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    polymarket_address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"), nullable=False, index=True)
    watch_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    first_funded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    parent = relationship("Parent", back_populates="accounts")
