"""add single-column indexes on messages.session_id and messages.created_at

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a7
Create Date: 2026-03-19

Keeps existing composite ``ix_messages_session_created``; adds ORM-aligned btree
indexes for ``session_id`` and ``created_at`` columns.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_messages_session_id"), "messages", ["session_id"], unique=False
    )
    op.create_index(
        op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_index(op.f("ix_messages_session_id"), table_name="messages")
