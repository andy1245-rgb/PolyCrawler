"""Portable SQLAlchemy column types (Postgres in prod, SQLite in tests)."""

from typing import Any

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine

# JSON on SQLite / generic; JSONB on PostgreSQL.
JsonType: TypeEngine[Any] = JSON().with_variant(JSONB(), "postgresql")
