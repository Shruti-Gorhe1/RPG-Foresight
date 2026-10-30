from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from db.base import Base
from db.models import (
    Connector,
    NotificationDelivery,
    RecipientAddress,
    RecipientDecision,
    RoutingRule,
    SubsidiaryRoute,
    TenderEvent,
    TenderOutcomeSnapshot,
)
from ingestion.connectors.base import BaseConnector, ConnectorResult
from ingestion.connectors.itrack import ITrackConnector
from ingestion.connectors.registry import ConnectorRegistry, registry
from ingestion.connectors.zoho import ZohoConnector
from agents.tools.sync_pipeline_tools import persist_tender_events
from services.ingestion_service import run_ingestion_pipeline
from services.notification import NotificationAdapter, NotificationResult
from services.routing_service import run_routing_and_delivery


@pytest.mark.asyncio
async def test_registry_skips_disabled_connectors_and_captures_connector_errors() -> None:
    class StubConnector(BaseConnector):
        source_name = "stub"

        def __init__(self, connector_id: str, enabled: bool, should_fail: bool = False) -> None:
            super().__init__(connector_id)
            self.is_enabled = enabled
            self.should_fail = should_fail

        async def fetch(self) -> ConnectorResult:
            if self.should_fail:
                raise RuntimeError("connector unavailable")
            return ConnectorResult(self.connector_id, self.source_name)

        async def normalize(self, raw_record):
            return raw_record

    connectors = ConnectorRegistry()
    connectors.register(StubConnector("disabled", enabled=False))
    connectors.register(StubConnector("broken", enabled=True, should_fail=True))

    result = await connectors.run_all(set())

    assert list(result) == ["broken"]
    assert result["broken"].errors == ["connector unavailable"]


@pytest.mark.asyncio
async def test_itrack_reuses_stable_demo_tenders_across_syncs() -> None:
    connector = ITrackConnector()
    existing_ids: set[tuple[str, str]] = set()

    first_sync = await connector.run(existing_ids)
    second_sync = await connector.run(existing_ids)

    first_ids = {record["event_id"] for record in first_sync.records}
    second_ids = {record["event_id"] for record in second_sync.records}
    assert first_ids == {
        "IT-2026-1001",
        "IT-2026-1002",
        "IT-2026-1003",
        "IT-2026-1004",
    }
    assert second_ids == set()


def test_zoho_connector_stays_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ingestion.connectors.zoho.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "zoho_connector_enabled": False,
                "zoho_client_id": "configured",
                "zoho_client_secret": "configured",
                "zoho_refresh_token": "configured",
            },
        )(),
    )

    assert not ZohoConnector().is_enabled


@pytest_asyncio.fixture
async def workflow_sessions(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all        )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr("db.base.AsyncSessionLocal", session_factory)
        monkeypatch.setattr(registry, "_connectors", {"itrack": ITrackConnector()})
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_mock_ingestion_routes_and_retries_email_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    workflow_sessions,
) -> None:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    monkeypatch.setattr(trace, "get_tracer", tracer_provider.get_tracer)

    now = datetime.now(timezone.utc)
    async with workflow_sessions() as db:
        db.add(
            Connector(
                connector_id="itrack",
                name="iTrack Tender Tracking",
                source_type="crm",
                source_name="iTrack",
                config={},
                is_active=True,
                is_enabled=True,
            )
        )
        rule = RoutingRule(
            rule_id="demo-email-rule",
            tenant_id="KEC-001",
            name="Demo tender email",
            enabled=True,
            trigger_stages=["Bid Submitted"],
            min_win_probability_percent=40,
            purpose="Bid evaluation",
            channel="email",
            selected_recipient_email="buyer@example.test",
            max_event_age_seconds=86_400,
            max_probability_age_seconds=604_800,
            version=1,
        )
        rule.routes.append(
            SubsidiaryRoute(
                subsidiary_entity_id="",
                material_categories=["Power cables", "Cable accessories"],
            )
        )
        db.add(RecipientAddress(tenant_id="KEC-001", email="buyer@example.test"))
        db.add(rule)
        await db.commit()

    class FakeEmailAdapter(NotificationAdapter):
        def __init__(self) -> None:
            super().__init__("email")
            self.outcomes = ["failed", "sent"]
            self.messages: list[tuple[str, dict, list[str] | None]] = []

        async def send(self, recipient_user_id, payload, approved_fields=None):
            self.messages.append((recipient_user_id, payload, approved_fields))
            status = self.outcomes.pop(0) if self.outcomes else "sent"
            return NotificationResult(
                recipient_user_id,
                "email",
                status,
                message_id="workflow-test-message" if status == "sent" else None,
                error="temporary SMTP failure" if status == "failed" else None,
            )

    adapter = FakeEmailAdapter()
    monkeypatch.setattr("services.routing_service.get_adapter", lambda channel: adapter)

    failed = await run_ingestion_pipeline()
    assert failed["status"] == "failed"
    assert failed["total_created"] == 3
    assert failed["routing"]["deliveries_failed"] == 1
    assert len(adapter.messages) == 1
    assert adapter.messages[0][0] == "buyer@example.test"
    first_tender_ref = adapter.messages[0][1]["tender_ref"]
    assert first_tender_ref == "IT-2026-1001"
    async with workflow_sessions() as db:
        demo_events = (await db.execute(select(TenderEvent))).scalars().all()
        assert len(demo_events) == 3
        assert all(event.tender_value is not None for event in demo_events)
        assert all(event.currency == "INR" for event in demo_events)
        assert all(event.closing_at is not None for event in demo_events)
        assert all(event.opening_at is not None for event in demo_events)
        assert all(event.data_provenance.startswith("Demo data:") for event in demo_events)
        assert all(event.existing_win_probability_percent is not None for event in demo_events)
        assert all(event.probability_updated_at is not None for event in demo_events)
        history = (await db.execute(select(TenderOutcomeSnapshot))).scalars().all()
        assert len(history) >= 100
        assert {snapshot.outcome for snapshot in history} == {"won", "lost"}
        assert all(snapshot.is_demo for snapshot in history)
        late_stage_samples = [
            snapshot for snapshot in history
            if snapshot.stage == "Technical evaluation"
        ]
        assert 0 < len(late_stage_samples) < 40
        assert {snapshot.outcome for snapshot in late_stage_samples} == {"won", "lost"}


    async with workflow_sessions() as db:
        failed_event_id = (
            await db.execute(
                select(NotificationDelivery.event_id).where(
                    NotificationDelivery.status == "failed"
                )
            )
        ).scalar_one()
        retried = await run_routing_and_delivery(db, event_ids={failed_event_id})
    assert retried["status"] == "completed"
    assert retried["deliveries_retried"] == 1
    assert retried["deliveries_sent"] == 1
    assert len(adapter.messages) == 2
    assert adapter.messages[1][1]["tender_ref"] == first_tender_ref

    third_sync = await run_ingestion_pipeline()
    assert third_sync["total_created"] == 0
    assert third_sync["routing"]["deliveries_sent"] == 0
    assert len(adapter.messages) == 2
    async with workflow_sessions() as db:
        decisions = (await db.execute(select(RecipientDecision))).scalars().all()
        deliveries = (await db.execute(select(NotificationDelivery))).scalars().all()
        assert len(decisions) == 1
        assert len(deliveries) == 1
        assert deliveries[0].status == "sent"
        assert deliveries[0].retry_count == 1

    spans = span_exporter.get_finished_spans()
    span_names = {span.name for span in spans}
    assert {
        "rpg_foresight.ingestion.run",
        "rpg_foresight.agent.sync_signal_supervisor",
        "rpg_foresight.agent.ingestion_supervisor",
        "rpg_foresight.agent.identify_connectors",
        "rpg_foresight.agent.connector_runner",
        "rpg_foresight.agent.db_writer",
        "rpg_foresight.agent.route_signals",
        "rpg_foresight.connector.run",
        "rpg_foresight.tool.load_existing_tender_revisions",
        "rpg_foresight.tool.select_ingestion_specialist",
        "rpg_foresight.tool.run_enabled_connectors",
        "rpg_foresight.tool.persist_tender_events",
        "rpg_foresight.tool.route_tender_signals",
        "rpg_foresight.routing.run",
        "rpg_foresight.tool.match_routing_rules",
        "rpg_foresight.tool.evaluate_routing_rule",
        "rpg_foresight.tool.deliver_notification",
    }.issubset(span_names)
    first_sync_root = next(
        span for span in spans if span.name == "rpg_foresight.ingestion.run"
    )
    first_sync_spans = [
        span for span in spans
        if span.context.trace_id == first_sync_root.context.trace_id
    ]
    assert {
        "rpg_foresight.agent.sync_signal_supervisor",
        "rpg_foresight.agent.identify_connectors",
        "rpg_foresight.agent.connector_runner",
        "rpg_foresight.agent.db_writer",
        "rpg_foresight.agent.route_signals",
        "rpg_foresight.tool.load_existing_tender_revisions",
        "rpg_foresight.tool.select_ingestion_specialist",
        "rpg_foresight.tool.run_enabled_connectors",
        "rpg_foresight.tool.persist_tender_events",
        "rpg_foresight.tool.route_tender_signals",
    }.issubset({span.name for span in first_sync_spans})

    def has_parent(child_name: str, parent_name: str) -> bool:
        parents = {
            span.context.span_id: span
            for span in first_sync_spans
        }
        return any(
            span.name == child_name
            and span.parent is not None
            and parents.get(span.parent.span_id, None) is not None
            and parents[span.parent.span_id].name == parent_name
            for span in first_sync_spans
        )

    assert has_parent(
        "rpg_foresight.tool.load_existing_tender_revisions",
        "rpg_foresight.agent.identify_connectors",
    )
    assert has_parent(
        "rpg_foresight.agent.ingestion_supervisor",
        "rpg_foresight.agent.sync_signal_supervisor",
    )
    assert has_parent(
        "rpg_foresight.tool.run_enabled_connectors",
        "rpg_foresight.agent.connector_runner",
    )
    assert has_parent(
        "rpg_foresight.tool.persist_tender_events",
        "rpg_foresight.agent.db_writer",
    )
    assert has_parent(
        "rpg_foresight.tool.route_tender_signals",
        "rpg_foresight.agent.route_signals",
    )
    tool_spans = [
        span for span in first_sync_spans
        if ".tool." in span.name
    ]
    assert tool_spans
    assert all(
        span.attributes["openinference.span.kind"] == "TOOL"
        for span in tool_spans
    )
    rule_evaluation_spans = [
        span for span in spans
        if span.name == "rpg_foresight.tool.evaluate_routing_rule"
    ]
    assert rule_evaluation_spans
    assert all(
        "rpg_foresight.rule.id" in span.attributes
        and "rpg_foresight.rule.evaluation_status" in span.attributes
        for span in rule_evaluation_spans
    )
    tracer_provider.shutdown()


@pytest.mark.asyncio
async def test_sync_recalculates_probabilities_for_existing_tenant_tenders(workflow_sessions):
    async with workflow_sessions() as db:
        db.add(TenderEvent(
            tenant_id="KEC-001",
            event_id="older-demo-tender",
            sender_entity_id="KEC-ENTITY",
            tender_ref="T-OLD",
            project_name="Older demo tender",
            source_revision="rev1",
            stage="Bid Submitted",
            occurred_at=datetime.now(timezone.utc),
            material_categories=["Power cables"],
            existing_win_probability_percent=None,
            probability_updated_at=None,
            source_type="crm",
            data_provenance="Demo data: synthetic iTrack records",
            region="West",
            tender_value=1_000_000,
            currency="INR",
        ))
        await db.commit()

    history = [
        {
            "source_event_id": f"completed-{index}",
            "snapshot_key": "bid-submitted",
            "stage": "Bid Submitted",
            "material_categories": ["Power cables"],
            "region": "West",
            "tender_value": 1_000_000,
            "currency": "INR",
            "outcome": "won" if index < 7 else "lost",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        for index in range(12)
    ]
    await persist_tender_events({
        "itrack": {
            "records": [{
                "tenant_id": "KEC-001",
                "event_id": "new-demo-tender",
                "sender_entity_id": "KEC-ENTITY",
                "tender_ref": "T-NEW",
                "project_name": "New demo tender",
                "source_revision": "rev1",
                "stage": "Bid Submitted",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "material_categories": ["Power cables"],
                "tender_value": 1_000_000,
                "currency": "INR",
                "source_type": "crm",
                "data_provenance": "Demo data: synthetic iTrack records",
                "historical_outcomes": history,
            }],
            "errors": [],
        }
    })

    async with workflow_sessions() as db:
        older_tender = (
            await db.execute(
                select(TenderEvent).where(TenderEvent.event_id == "older-demo-tender")
            )
        ).scalar_one()
        assert older_tender.existing_win_probability_percent is not None
        assert older_tender.probability_updated_at is not None


@pytest.mark.asyncio
async def test_successful_ingestion_returns_completed_status(workflow_sessions):
    async with workflow_sessions() as db:
        db.add(Connector(
            connector_id="itrack",
            name="iTrack Tender Tracking",
            source_type="crm",
            source_name="iTrack",
            config={},
            is_active=True,
            is_enabled=True,
        ))
        await db.commit()

    result = await run_ingestion_pipeline()

    assert result["status"] == "completed"
    assert result["errors"] == []
    assert result["connectors_run"] == 1
    assert result["total_created"] == 3
    repeated = await run_ingestion_pipeline()
    assert repeated["status"] == "completed"
    assert repeated["total_created"] == 0
