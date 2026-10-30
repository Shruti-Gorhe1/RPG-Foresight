"""Add a simple tenant-scoped recipient email address book."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_recipient_address_book"
down_revision = "0006_pursuit_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipient_addresses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_recipient_address_tenant_email"),
    )
    op.create_index(
        "ix_recipient_addresses_tenant_id",
        "recipient_addresses",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recipient_addresses_tenant_id", table_name="recipient_addresses")
    op.drop_table("recipient_addresses")
