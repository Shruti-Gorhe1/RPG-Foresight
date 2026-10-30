"""Store the selected email recipient on routing rules."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_selected_rule_recipient"
down_revision = "0003_email_recipient_addresses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "routing_rules",
        sa.Column("selected_recipient_email", sa.String(length=254), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("routing_rules", "selected_recipient_email")
