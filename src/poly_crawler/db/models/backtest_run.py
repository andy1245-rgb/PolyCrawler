from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class BacktestRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "backtest_runs"

    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    score_variant: Mapped[str | None] = mapped_column(String(10), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
