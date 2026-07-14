"""add_is_derived_derived_at_reactivated_at_to_sessions

Revision ID: 917d82f0e15e
Revises: 9827da4fd5e5
Create Date: 2026-06-25 15:14:16.238155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '917d82f0e15e'
down_revision: Union[str, Sequence[str], None] = '9827da4fd5e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agregar is_derived con default False para filas existentes
    op.add_column(
        "sessions",
        sa.Column("is_derived", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column("sessions", "is_derived", server_default=None)
    
    # Agregar derived_at (nullable)
    op.add_column(
        "sessions",
        sa.Column("derived_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    
    # Agregar reactivated_at (nullable)
    op.add_column(
        "sessions",
        sa.Column("reactivated_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sessions", "reactivated_at")
    op.drop_column("sessions", "derived_at")
    op.drop_column("sessions", "is_derived")
