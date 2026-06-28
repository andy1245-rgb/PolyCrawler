"""Initial migration — create all 11 tables.

Revision ID: 0001
Revises:
Create Date: 2026-06-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, BIGINT, DOUBLE_PRECISION

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- parents ---
    op.create_table(
        "parents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("chain_address", sa.String(42), unique=True, nullable=False, index=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_ignored", sa.Boolean(), default=False, nullable=False, index=True),
        sa.Column("metadata", JSONB, default=dict, nullable=False),
    )

    # --- config_snapshots ---
    op.create_table(
        "config_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("config_json", JSONB, nullable=False),
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("review_mode", sa.String(10), nullable=False),
        sa.Column("config_snapshot", JSONB, nullable=False),
        sa.Column("private", sa.Boolean(), default=False, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="running"),
    )

    # --- accounts ---
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("polymarket_address", sa.String(42), unique=True, nullable=False),
        sa.Column("account_type", sa.String(20), nullable=False, default="unknown"),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("parents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("watch_status", sa.String(20), nullable=False, default="active", index=True),
        sa.Column("first_funded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, default=dict, nullable=False),
    )

    # --- clusters ---
    op.create_table(
        "clusters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("parents.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("cluster_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("score_variant", sa.String(10), nullable=False, default="sqrt"),
        sa.Column("last_scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sibling_count", sa.Integer(), nullable=False, default=0),
        sa.Column("vetted_sibling_count", sa.Integer(), nullable=False, default=0),
    )

    # --- cluster_positions ---
    op.create_table(
        "cluster_positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cluster_id", UUID(as_uuid=True), sa.ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("market_id", sa.String(64), nullable=False),
        sa.Column("market_slug", sa.String(255), nullable=True),
        sa.Column("market_title", sa.Text(), nullable=True),
        sa.Column("market_tags", JSONB, default=list, nullable=False),
        sa.Column("state", sa.String(20), nullable=False, default="watching", index=True),
        sa.Column("net_exposure", BIGINT(), default=0, nullable=False),
        sa.Column("last_known_net", BIGINT(), default=0, nullable=False),
        sa.Column("mirrored_yes", BIGINT(), default=0, nullable=False),
        sa.Column("mirrored_no", BIGINT(), default=0, nullable=False),
        sa.Column("sibling_balances", JSONB, default=dict, nullable=False),
        sa.Column("tp_sl_suspended", sa.Boolean(), default=False, nullable=False),
        sa.Column("last_closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_closed_reason", sa.String(40), nullable=True),
        sa.Column("config_snapshot_id", UUID(as_uuid=True), sa.ForeignKey("config_snapshots.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cluster_id", "market_id", name="uq_cluster_position"),
    )

    # --- alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("parents.id"), nullable=True, index=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("cluster_id", UUID(as_uuid=True), sa.ForeignKey("clusters.id"), nullable=True, index=True),
        sa.Column("alert_type", sa.String(30), nullable=False, index=True),
        sa.Column("amount_usd", DOUBLE_PRECISION(), nullable=True),
        sa.Column("cluster_score_at_event", DOUBLE_PRECISION(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("metadata", JSONB, default=dict, nullable=False),
        sa.Column("is_false_positive", sa.Boolean(), default=None, nullable=True, index=True),
    )

    # --- paper_trades ---
    op.create_table(
        "paper_trades",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cluster_position_id", UUID(as_uuid=True), sa.ForeignKey("cluster_positions.id"), nullable=True, index=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True, index=True),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("sibling_account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("net_before", BIGINT(), nullable=True),
        sa.Column("net_after", BIGINT(), nullable=True),
        sa.Column("net_delta", BIGINT(), nullable=True),
        sa.Column("our_side", sa.String(4), nullable=True),
        sa.Column("our_shares", BIGINT(), nullable=True),
        sa.Column("our_fill_price", DOUBLE_PRECISION(), nullable=True),
        sa.Column("our_fill_usd", DOUBLE_PRECISION(), nullable=True),
        sa.Column("source_tx", sa.String(66), nullable=True),
        sa.Column("reason", sa.String(40), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("book_snapshot_id", sa.String(64), nullable=True),
        sa.Column("slippage_bps", sa.Integer(), nullable=True),
    )

    # --- sibling_balance_snapshots ---
    op.create_table(
        "sibling_balance_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False, index=True),
        sa.Column("cluster_id", UUID(as_uuid=True), sa.ForeignKey("clusters.id"), nullable=False),
        sa.Column("market_id", sa.String(64), nullable=False),
        sa.Column("yes_shares", BIGINT(), default=0, nullable=False),
        sa.Column("no_shares", BIGINT(), default=0, nullable=False),
        sa.Column("polled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- rpc_logs ---
    op.create_table(
        "rpc_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("method", sa.String(100), nullable=False),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )

    # --- backtest_runs ---
    op.create_table(
        "backtest_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("config_snapshot", JSONB, nullable=True),
        sa.Column("score_variant", sa.String(10), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="running"),
    )


def downgrade() -> None:
    op.drop_table("backtest_runs")
    op.drop_table("rpc_logs")
    op.drop_table("sibling_balance_snapshots")
    op.drop_table("paper_trades")
    op.drop_table("alerts")
    op.drop_table("cluster_positions")
    op.drop_table("clusters")
    op.drop_table("accounts")
    op.drop_table("sessions")
    op.drop_table("config_snapshots")
    op.drop_table("parents")
