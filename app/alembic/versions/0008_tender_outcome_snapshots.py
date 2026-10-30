"""Store point-in-time tender features and final outcomes for probability training."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_tender_outcome_snapshots"
down_revision = "0007_recipient_address_book"
branch_labels = None
depends_on = None


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table("tender_outcome_snapshots")


def upgrade() -> None:
    op.execute(
        "UPDATE tender_events "
        "SET existing_win_probability_percent = NULL, probability_updated_at = NULL"
    )
    if not _has_table():
        op.create_table(
            "tender_outcome_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("source_event_id", sa.String(length=128), nullable=False),
            sa.Column("snapshot_key", sa.String(length=128), nullable=False),
            sa.Column("stage", sa.String(length=64), nullable=False),
            sa.Column("material_categories", sa.JSON(), nullable=False),
            sa.Column("region", sa.String(length=128), nullable=True),
            sa.Column("tender_value", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=True),
            sa.Column("outcome", sa.String(length=16), nullable=False),
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "source_event_id",
                "snapshot_key",
                name="uq_tender_outcome_snapshot_source",
            ),
        )
    indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("tender_outcome_snapshots")
    }
    if "ix_tender_outcome_snapshots_tenant_id" not in indexes:
        op.create_index(
            "ix_tender_outcome_snapshots_tenant_id",
            "tender_outcome_snapshots",
            ["tenant_id"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_tender_outcome_snapshots_tenant_id",
        table_name="tender_outcome_snapshots",
    )
    op.drop_table("tender_outcome_snapshots")
