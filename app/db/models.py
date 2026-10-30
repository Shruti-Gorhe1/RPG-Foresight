"""ORM models. Replace / extend these with your domain entities.

The example ``Session`` model mirrors the accelerator's session-centric pattern:
each interactive run is a row keyed by ``session_id`` with a JSON ``state`` blob
that holds the agent graph state, plus indexed columns for querying.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import JSON, DateTime, String, func, Boolean, ForeignKey, Integer, Text, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    current_step: Mapped[str] = mapped_column(String(64), default="start")
    # Full agent-graph state, persisted for resume + audit.
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenderEvent(Base):
    __tablename__ = "tender_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # source_event_id
    sender_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tender_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    prior_stage: Mapped[str] = mapped_column(String(32), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    material_categories: Mapped[list] = mapped_column(JSON, nullable=False)
    expected_need_window: Mapped[str] = mapped_column(String(64), nullable=True)
    existing_win_probability_percent: Mapped[float] = mapped_column(nullable=True)
    probability_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # CRM-free architecture fields
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # csv, public_portal, manual, crm
    data_provenance: Mapped[str] = mapped_column(String(256), nullable=False)  # origin + authorization level
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    material_requirements_raw: Mapped[str] = mapped_column(String(256), nullable=True)
    region: Mapped[str] = mapped_column(String(128), nullable=True)
    tender_value: Mapped[float] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=True)
    opening_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    closing_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    decisions: Mapped[list["RecipientDecision"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    notifications: Mapped[list["NotificationDelivery"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class TenderOutcomeSnapshot(Base):
    __tablename__ = "tender_outcome_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_event_id",
            "snapshot_key",
            name="uq_tender_outcome_snapshot_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot_key: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    material_categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    region: Mapped[str] = mapped_column(String(128), nullable=True)
    tender_value: Mapped[float] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)  # e.g. "itrack", "cppp"
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # crm, public_portal
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "iTrack", "CPPP"
    description: Mapped[str] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # connection config, API endpoints, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # tenant must enable
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    runs: Mapped[list["ConnectorRun"]] = relationship(back_populates="connector", cascade="all, delete-orphan")


class ConnectorRun(Base):
    __tablename__ = "connector_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(64), ForeignKey("connectors.connector_id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running, completed, failed, partial
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_normalized: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    connector: Mapped["Connector"] = relationship(back_populates="runs")


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trigger_stages: Mapped[list] = mapped_column(JSON, nullable=False)  # list of stage names
    min_win_probability_percent: Mapped[float] = mapped_column(nullable=True)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_recipient_email: Mapped[str] = mapped_column(String(254), nullable=True)
    selected_recipient_emails: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    regions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tender_currency: Mapped[str] = mapped_column(String(8), nullable=True)
    minimum_tender_value: Mapped[float] = mapped_column(Float, nullable=True)
    maximum_tender_value: Mapped[float] = mapped_column(Float, nullable=True)
    minimum_days_to_close: Mapped[int] = mapped_column(Integer, nullable=True)
    maximum_days_to_close: Mapped[int] = mapped_column(Integer, nullable=True)
    max_event_age_seconds: Mapped[int] = mapped_column(Integer, default=86_400, nullable=False)
    max_probability_age_seconds: Mapped[int] = mapped_column(Integer, default=604_800, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    previewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=True)

    routes: Mapped[list["SubsidiaryRoute"]] = relationship(back_populates="rule", cascade="all, delete-orphan")


class SubsidiaryRoute(Base):
    __tablename__ = "subsidiary_routes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), ForeignKey("routing_rules.rule_id"), nullable=False, index=True)
    subsidiary_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    material_categories: Mapped[list] = mapped_column(JSON, nullable=False)

    rule: Mapped["RoutingRule"] = relationship(back_populates="routes")


class SharingPolicy(Base):
    __tablename__ = "sharing_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sender_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    receiver_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # pending, approved, denied, revoked
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_fields: Mapped[list] = mapped_column(JSON, default=list)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RecipientAddress(Base):
    __tablename__ = "recipient_addresses"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_recipient_address_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecipientDecision(Base):
    __tablename__ = "recipient_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("tender_events.event_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subsidiary_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_user_id: Mapped[str] = mapped_column(String(254), nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)  # candidate, suppressed
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    policy_id: Mapped[str] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["TenderEvent"] = relationship(back_populates="decisions")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("tender_events.event_id"), nullable=False, index=True)
    recipient_user_id: Mapped[str] = mapped_column(String(254), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # pending, sent, delivered, failed, suppressed
    message_id: Mapped[str] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["TenderEvent"] = relationship(back_populates="notifications")


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("notification_deliveries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message_id: Mapped[str] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalFeedback(Base):
    __tablename__ = "signal_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("tender_events.event_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    feedback: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenderFollowUp(Base):
    __tablename__ = "tender_follow_ups"
    __table_args__ = (UniqueConstraint("event_id", name="uq_tender_follow_ups_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("tender_events.event_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    assigned_to: Mapped[str] = mapped_column(String(254), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="New")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    follow_up_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PursuitAssessment(Base):
    __tablename__ = "pursuit_assessments"

    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), ForeignKey("tender_events.event_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    report: Mapped[dict] = mapped_column(JSON, nullable=False)
    document_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    decision: Mapped[str] = mapped_column(String(16), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, nullable=True)
    decision_by: Mapped[str] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=True)  # user or service
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=True)
    object_id: Mapped[str] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(String(32), nullable=False)  # success, failure, suppressed
    reason: Mapped[str] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())