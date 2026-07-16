from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, JsonType, TimestampMixin, UUIDMixin


class ConfigSnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "config_snapshots"

    config_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
