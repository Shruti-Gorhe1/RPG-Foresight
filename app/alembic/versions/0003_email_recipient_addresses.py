"""Support standard-length email addresses for signal recipients.

Revision ID: 0003_email_recipient_addresses
Revises: 0002_crm_free_architecture
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_email_recipient_addresses"
down_revision = "0002_crm_free_architecture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in (
        "sharing_policies",
        "recipient_decisions",
        "notification_deliveries",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "recipient_user_id",
                existing_type=sa.String(length=64),
                type_=sa.String(length=254),
                existing_nullable=False,
            )


def downgrade() -> None:
    for table_name in (
        "notification_deliveries",
        "recipient_decisions",
        "sharing_policies",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "recipient_user_id",
                existing_type=sa.String(length=254),
                type_=sa.String(length=64),
                existing_nullable=False,
            )
