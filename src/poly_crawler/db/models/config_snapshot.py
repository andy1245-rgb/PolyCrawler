from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class ConfigSnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "config_snapshots"

    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
