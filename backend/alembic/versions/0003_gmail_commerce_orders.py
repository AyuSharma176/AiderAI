"""Add Gmail connections and normalized commerce orders.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    expected_tables = {
        "email_connections",
        "commerce_orders",
        "commerce_order_items",
        "order_source_events",
    }
    if expected_tables.issubset(set(sa.inspect(op.get_bind()).get_table_names())):
        return
    op.create_table(
        "email_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("granted_scopes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_history_id", sa.String(128), nullable=True),
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_email_connection_user_provider"),
    )
    op.create_index("ix_email_connections_user_id", "email_connections", ["user_id"])
    op.create_index("ix_email_connections_status", "email_connections", ["status"])

    op.create_table(
        "commerce_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("marketplace_order_id", sa.String(120), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("expected_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tracking_number", sa.String(160), nullable=True),
        sa.Column("carrier", sa.String(120), nullable=True),
        sa.Column("marketplace_url", sa.String(2048), nullable=True),
        sa.Column("last_source_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "marketplace",
            "marketplace_order_id",
            name="uq_commerce_order_owner_marketplace_id",
        ),
    )
    op.create_index("ix_commerce_orders_user_id", "commerce_orders", ["user_id"])
    op.create_index("ix_commerce_orders_marketplace", "commerce_orders", ["marketplace"])
    op.create_index("ix_commerce_orders_status", "commerce_orders", ["status"])
    op.create_index(
        "ix_commerce_orders_last_source_message_at",
        "commerce_orders",
        ["last_source_message_at"],
    )

    op.create_table(
        "commerce_order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("marketplace_product_id", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["commerce_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commerce_order_items_order_id", "commerce_order_items", ["order_id"])

    op.create_table(
        "order_source_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider_message_id_hash", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parser_name", sa.String(80), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["email_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["commerce_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "provider_message_id_hash",
            name="uq_order_source_connection_message",
        ),
    )
    op.create_index("ix_order_source_events_order_id", "order_source_events", ["order_id"])
    op.create_index(
        "ix_order_source_events_connection_id", "order_source_events", ["connection_id"]
    )
    op.create_index("ix_order_source_events_event_type", "order_source_events", ["event_type"])
    op.create_index("ix_order_source_events_event_at", "order_source_events", ["event_at"])


def downgrade() -> None:
    op.drop_table("order_source_events")
    op.drop_table("commerce_order_items")
    op.drop_table("commerce_orders")
    op.drop_table("email_connections")
