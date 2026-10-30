"""Add tender operations, rule filters, feedback, follow-up, and delivery attempts."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_tender_operations"
down_revision = "0004_selected_rule_recipient"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _add_column(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    for column in (
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("tender_value", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("closing_at", sa.DateTime(timezone=True), nullable=True),
    ):
        _add_column("tender_events", column)

    for column in (
        sa.Column("selected_recipient_emails", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("regions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tender_currency", sa.String(length=8), nullable=True),
        sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minimum_tender_value", sa.Float(), nullable=True),
        sa.Column("maximum_tender_value", sa.Float(), nullable=True),
        sa.Column("minimum_days_to_close", sa.Integer(), nullable=True),
        sa.Column("maximum_days_to_close", sa.Integer(), nullable=True),
    ):
        _add_column("routing_rules", column)

    if not _has_table("signal_feedback"):
        op.create_table(
            "signal_feedback",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=128), nullable=False),
            sa.Column("feedback", sa.String(length=32), nullable=False),
            sa.Column("reason", sa.String(length=1000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["event_id"], ["tender_events.event_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("signal_feedback", "ix_signal_feedback_event_id"):
        op.create_index("ix_signal_feedback_event_id", "signal_feedback", ["event_id"])
    if not _has_index("signal_feedback", "ix_signal_feedback_tenant_id"):
        op.create_index("ix_signal_feedback_tenant_id", "signal_feedback", ["tenant_id"])

    if not _has_table("tender_follow_ups"):
        op.create_table(
            "tender_follow_ups",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("assigned_to", sa.String(length=254), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="New"),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_by", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["event_id"], ["tender_events.event_id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", name="uq_tender_follow_ups_event_id"),
        )
    if not _has_index("tender_follow_ups", "ix_tender_follow_ups_event_id"):
        op.create_index("ix_tender_follow_ups_event_id", "tender_follow_ups", ["event_id"])
    if not _has_index("tender_follow_ups", "ix_tender_follow_ups_tenant_id"):
        op.create_index("ix_tender_follow_ups_tenant_id", "tender_follow_ups", ["tenant_id"])

    if not _has_table("delivery_attempts"):
        op.create_table(
            "delivery_attempts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("delivery_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("message_id", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["delivery_id"], ["notification_deliveries.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("delivery_attempts", "ix_delivery_attempts_delivery_id"):
        op.create_index("ix_delivery_attempts_delivery_id", "delivery_attempts", ["delivery_id"])


def downgrade() -> None:
    if _has_table("delivery_attempts"):
        if _has_index("delivery_attempts", "ix_delivery_attempts_delivery_id"):
            op.drop_index("ix_delivery_attempts_delivery_id", table_name="delivery_attempts")
        op.drop_table("delivery_attempts")
    if _has_table("tender_follow_ups"):
        if _has_index("tender_follow_ups", "ix_tender_follow_ups_tenant_id"):
            op.drop_index("ix_tender_follow_ups_tenant_id", table_name="tender_follow_ups")
        if _has_index("tender_follow_ups", "ix_tender_follow_ups_event_id"):
            op.drop_index("ix_tender_follow_ups_event_id", table_name="tender_follow_ups")
        op.drop_table("tender_follow_ups")
    if _has_table("signal_feedback"):
        if _has_index("signal_feedback", "ix_signal_feedback_tenant_id"):
            op.drop_index("ix_signal_feedback_tenant_id", table_name="signal_feedback")
        if _has_index("signal_feedback", "ix_signal_feedback_event_id"):
            op.drop_index("ix_signal_feedback_event_id", table_name="signal_feedback")
        op.drop_table("signal_feedback")

    for column in (
        "maximum_days_to_close",
        "minimum_days_to_close",
        "maximum_tender_value",
        "minimum_tender_value",
        "regions",
        "tender_currency",
        "previewed_at",
        "selected_recipient_emails",
    ):
        if _has_column("routing_rules", column):
            op.drop_column("routing_rules", column)
    for column in ("closing_at", "currency", "tender_value", "region"):
        if _has_column("tender_events", column):
            op.drop_column("tender_events", column)
