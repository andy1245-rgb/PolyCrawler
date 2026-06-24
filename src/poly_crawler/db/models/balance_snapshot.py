from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class SiblingBalanceSnapshot(UUIDMixin, Base):
    __tablename__ = "sibling_balance_snapshots"

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    cluster_id: Mapped[UUID] = mapped_column(ForeignKey("clusters.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(String(64), nullable=False)
    yes_shares: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    no_shares: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    polled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
