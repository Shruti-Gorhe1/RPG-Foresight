"""Persist agentic pursuit assessments and human decisions."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_pursuit_assessments"
down_revision = "0005_tender_operations"
branch_labels = None
depends_on = None


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table("pursuit_assessments")


def upgrade() -> None:
    if not _has_table():
        op.create_table(
            "pursuit_assessments",
            sa.Column("assessment_id", sa.String(length=64), nullable=False),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("recommendation", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
            sa.Column("report", sa.JSON(), nullable=False),
            sa.Column("document_names", sa.JSON(), nullable=False),
            sa.Column("decision", sa.String(length=16), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("decision_by", sa.String(length=128), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["event_id"], ["tender_events.event_id"]),
            sa.PrimaryKeyConstraint("assessment_id"),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("pursuit_assessments")}
    if "ix_pursuit_assessments_event_id" not in indexes:
        op.create_index("ix_pursuit_assessments_event_id", "pursuit_assessments", ["event_id"])
    if "ix_pursuit_assessments_tenant_id" not in indexes:
        op.create_index("ix_pursuit_assessments_tenant_id", "pursuit_assessments", ["tenant_id"])


def downgrade() -> None:
    if _has_table():
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("pursuit_assessments")}
        if "ix_pursuit_assessments_tenant_id" in indexes:
            op.drop_index("ix_pursuit_assessments_tenant_id", table_name="pursuit_assessments")
        if "ix_pursuit_assessments_event_id" in indexes:
            op.drop_index("ix_pursuit_assessments_event_id", table_name="pursuit_assessments")
        op.drop_table("pursuit_assessments")
