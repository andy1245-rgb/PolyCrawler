from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class RpcLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "rpc_logs"

    method: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
