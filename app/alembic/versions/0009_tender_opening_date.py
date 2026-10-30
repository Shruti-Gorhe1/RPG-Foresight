"""Add tender opening date."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_tender_opening_date"
down_revision = "0008_tender_outcome_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tender_events")}
    if "opening_at" not in columns:
        op.add_column(
            "tender_events",
            sa.Column("opening_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tender_events")}
    if "opening_at" in columns:
        op.drop_column("tender_events", "opening_at")
