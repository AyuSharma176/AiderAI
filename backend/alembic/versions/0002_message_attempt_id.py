"""Add idempotent chat attempt identifiers.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("messages")}
    if "client_message_id" not in columns:
        op.add_column("messages", sa.Column("client_message_id", sa.Uuid(), nullable=True))
    constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("messages")
    }
    if "uq_message_client_attempt" not in constraints:
        op.create_unique_constraint(
            "uq_message_client_attempt",
            "messages",
            ["conversation_id", "client_message_id"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_message_client_attempt", "messages", type_="unique")
    op.drop_column("messages", "client_message_id")
