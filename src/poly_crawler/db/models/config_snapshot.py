from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from poly_crawler.db.types import JsonType

from ..base import Base, TimestampMixin, UUIDMixin


class ConfigSnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "config_snapshots"

    config_json: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
