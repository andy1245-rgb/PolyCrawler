from uuid import UUID

from sqlalchemy import BigInteger, Double, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDMixin


class PaperTrade(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "paper_trades"

    cluster_position_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cluster_positions.id"), nullable=True, index=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sibling_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    net_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_delta: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    our_side: Mapped[str | None] = mapped_column(String(4), nullable=True)
    our_shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    our_fill_price: Mapped[float | None] = mapped_column(Double, nullable=True)
    our_fill_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
    source_tx: Mapped[str | None] = mapped_column(String(66), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    book_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slippage_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)

    position = relationship("ClusterPosition", back_populates="trades")
