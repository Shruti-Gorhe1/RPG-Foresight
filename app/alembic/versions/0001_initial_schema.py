"""initial schema — sessions table

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00

Regenerate for your own models with:
    alembic revision --autogenerate -m "your change"
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("current_step", sa.String(length=64), nullable=False, server_default="start"),
        sa.Column("state", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_status", "sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_table("sessions")
