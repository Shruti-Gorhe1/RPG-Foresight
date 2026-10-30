"""Add connector, rule, policy, decision, notification, audit tables

Revision ID: 0002_crm_free_architecture
Revises: de69cad196da
Create Date: 2026-10-16 00:00:00.000000

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_crm_free_architecture'
down_revision: Union[str, Sequence[str], None] = 'de69cad196da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── connectors ──
    op.create_table(
        'connectors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('connector_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('connector_id'),
    )
    op.create_index(op.f('ix_connectors_connector_id'), 'connectors', ['connector_id'], unique=False)

    # ── connector_runs ──
    op.create_table(
        'connector_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('connector_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('records_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_normalized', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['connector_id'], ['connectors.connector_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_connector_runs_connector_id'), 'connector_runs', ['connector_id'], unique=False)

    # ── routing_rules ──
    op.create_table(
        'routing_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('trigger_stages', sa.JSON(), nullable=False),
        sa.Column('min_win_probability_percent', sa.Float(), nullable=True),
        sa.Column('purpose', sa.String(length=128), nullable=False),
        sa.Column('channel', sa.String(length=64), nullable=False),
        sa.Column('max_event_age_seconds', sa.Integer(), nullable=False, server_default='86400'),
        sa.Column('max_probability_age_seconds', sa.Integer(), nullable=False, server_default='604800'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_id'),
    )
    op.create_index(op.f('ix_routing_rules_rule_id'), 'routing_rules', ['rule_id'], unique=False)
    op.create_index(op.f('ix_routing_rules_tenant_id'), 'routing_rules', ['tenant_id'], unique=False)

    # ── subsidiary_routes ──
    op.create_table(
        'subsidiary_routes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rule_id', sa.String(length=64), nullable=False),
        sa.Column('subsidiary_entity_id', sa.String(length=64), nullable=False),
        sa.Column('material_categories', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['routing_rules.rule_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subsidiary_routes_rule_id'), 'subsidiary_routes', ['rule_id'], unique=False)

    # ── sharing_policies ──
    op.create_table(
        'sharing_policies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('policy_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('sender_entity_id', sa.String(length=64), nullable=False),
        sa.Column('receiver_entity_id', sa.String(length=64), nullable=False),
        sa.Column('recipient_user_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('purpose', sa.String(length=128), nullable=False),
        sa.Column('channel', sa.String(length=64), nullable=False),
        sa.Column('allowed_fields', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id'),
    )
    op.create_index(op.f('ix_sharing_policies_policy_id'), 'sharing_policies', ['policy_id'], unique=False)
    op.create_index(op.f('ix_sharing_policies_tenant_id'), 'sharing_policies', ['tenant_id'], unique=False)

    # ── recipient_decisions ──
    op.create_table(
        'recipient_decisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('subsidiary_entity_id', sa.String(length=64), nullable=False),
        sa.Column('recipient_user_id', sa.String(length=64), nullable=False),
        sa.Column('disposition', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.String(length=256), nullable=False),
        sa.Column('policy_id', sa.String(length=64), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['tender_events.event_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_recipient_decisions_event_id'), 'recipient_decisions', ['event_id'], unique=False)
    op.create_index(op.f('ix_recipient_decisions_tenant_id'), 'recipient_decisions', ['tenant_id'], unique=False)

    # ── notification_deliveries ──
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('recipient_user_id', sa.String(length=64), nullable=False),
        sa.Column('channel', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('message_id', sa.String(length=128), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['tender_events.event_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notification_deliveries_event_id'), 'notification_deliveries', ['event_id'], unique=False)

    # ── audit_events ──
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=64), nullable=False),
        sa.Column('trace_id', sa.String(length=128), nullable=True),
        sa.Column('actor', sa.String(length=128), nullable=True),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('object_type', sa.String(length=64), nullable=True),
        sa.Column('object_id', sa.String(length=64), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('result', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_events_tenant_id'), 'audit_events', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_events')
    op.drop_table('notification_deliveries')
    op.drop_table('recipient_decisions')
    op.drop_table('sharing_policies')
    op.drop_table('subsidiary_routes')
    op.drop_table('routing_rules')
    op.drop_table('connector_runs')
    op.drop_table('connectors')