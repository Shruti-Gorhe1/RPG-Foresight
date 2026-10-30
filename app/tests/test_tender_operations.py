from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.auth import CurrentUser, get_current_user
from api.routers import delivery_status, rules, tender_operations
from db.base import Base, get_db_session
from db.models import (
    DeliveryAttempt,
    NotificationDelivery,
    RecipientAddress,
    RecipientDecision,
    TenderEvent,
    TenderOutcomeSnapshot,
)
from services.notification import NotificationResult


@pytest_asyncio.fixture
async def operations_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(tender_operations.router, prefix="/api/v1/tenders")
    app.include_router(rules.router, prefix="/api/v1/rules")
    app.include_router(delivery_status.router, prefix="/api/v1/delivery-status")

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("ops-user", "KEC-001")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_factory, app
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_tender_feedback_follow_up_and_report_are_tenant_scoped(operations_client):
    client, _session_factory, app = operations_client
    tender_response = await client.post(
        "/api/v1/tenders",
        json={
            "tender_id": "T-200",
            "project_name": "Transmission expansion",
            "stage": "Bid Submitted",
            "material_categories": ["Power cables"],
            "existing_win_probability_percent": 65,
            "region": "West",
            "tender_value": 1250000,
            "currency": "INR",
            "opening_at": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            "closing_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        },
    )
    assert tender_response.status_code == 201, tender_response.text
    assert tender_response.json()["existing_win_probability_percent"] is None
    assert tender_response.json()["opening_at"] is not None
    assert tender_response.json()["closing_at"] is not None
    event_id = tender_response.json()["event_id"]
    update_response = await client.patch(
        f"/api/v1/tenders/{event_id}",
        json={
            "tender_id": "T-200",
            "project_name": "Transmission expansion phase 2",
            "stage": "Reviewing",
            "material_categories": ["Power cables"],
            "existing_win_probability_percent": 70,
            "region": "West",
            "tender_value": 1300000,
            "currency": "INR",
            "closing_at": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["project_name"] == "Transmission expansion phase 2"
    assert update_response.json()["existing_win_probability_percent"] is None

    feedback_response = await client.put(
        f"/api/v1/tenders/{event_id}/feedback",
        json={"feedback": "Relevant", "reason": "Matches our cable business"},
    )
    follow_up_response = await client.put(
        f"/api/v1/tenders/{event_id}/follow-up",
        json={
            "assigned_to": "owner@example.test",
            "status": "Reviewing",
            "notes": "Confirm capacity",
            "follow_up_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
    )
    feedback_suggestions = await client.get("/api/v1/tenders/feedback/suggestions")
    follow_ups = await client.get("/api/v1/tenders/follow-ups?due_only=true")
    summary = await client.get("/api/v1/tenders/reports/summary")
    export = await client.get("/api/v1/tenders/reports/export.csv")

    assert feedback_response.status_code == 200
    assert follow_up_response.status_code == 200
    assert feedback_suggestions.json()["automatic_rule_changes"] is False
    assert len(follow_ups.json()) == 1
    assert follow_ups.json()[0]["is_due"] is True
    assert summary.json()["by_region"] == {"West": 1}
    assert summary.json()["by_deadline"]["8-30 days"] == 1
    assert "T-200" in export.text
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("other-user", "OTHER-TENANT")
    other_tenant_tenders = await client.get("/api/v1/tenders")
    assert other_tenant_tenders.status_code == 200
    assert other_tenant_tenders.json() == []


@pytest.mark.asyncio
async def test_manual_tender_gets_calculated_probability_from_tenant_history(operations_client):
    client, session_factory, _app = operations_client
    async with session_factory() as session:
        session.add_all([
            TenderOutcomeSnapshot(
                tenant_id="KEC-001",
                source_event_id=f"completed-tender-{index}",
                snapshot_key="bid-submitted",
                stage="Bid Submitted",
                material_categories=["Power cables"],
                region="West",
                tender_value=1_000_000,
                currency="INR",
                outcome="won" if index < 8 else "lost",
                is_demo=False,
                source_type="crm",
            )
            for index in range(12)
        ])
        await session.commit()

    created = await client.post(
        "/api/v1/tenders",
        json={
            "tender_id": "T-PROB-1",
            "project_name": "Cable expansion",
            "stage": "Bid Submitted",
            "material_categories": ["Power cables"],
            "existing_win_probability_percent": 1,
            "region": "West",
            "tender_value": 1_000_000,
            "currency": "INR",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["existing_win_probability_percent"] > 50
    assert created.json()["probability_updated_at"] is not None

    event_id = created.json()["event_id"]
    updated = await client.patch(
        f"/api/v1/tenders/{event_id}",
        json={
            "tender_id": "T-PROB-1",
            "project_name": "Cable expansion",
            "stage": "Stage with no labeled history",
            "material_categories": ["Power cables"],
            "region": "West",
            "tender_value": 1_000_000,
            "currency": "INR",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["existing_win_probability_percent"] is None
    assert updated.json()["probability_updated_at"] is None


@pytest.mark.asyncio
async def test_csv_import_previews_maps_and_returns_row_level_rejections(operations_client):
    client, _session_factory, _app = operations_client
    csv_bytes = (
        b"Ref,Project,Stage,Materials,Area,Win Probability\n"
        b"T-301,Substation upgrade,Preferred bidder,Power cables,South,80\n"
        b",Missing ID,Reviewing,Accessories,East,invalid\n"
    )
    preview = await client.post(
        "/api/v1/tenders/import/preview",
        files={"file": ("tenders.csv", csv_bytes, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["row_count"] == 2

    mapping = {
        "tender_id": "Ref",
        "project_name": "Project",
        "stage": "Stage",
        "material_categories": "Materials",
        "region": "Area",
    }
    imported = await client.post(
        "/api/v1/tenders/import",
        files={"file": ("tenders.csv", csv_bytes, "text/csv")},
        data={"mapping_json": json.dumps(mapping)},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1
    assert imported.json()["rejected_count"] == 1
    assert imported.json()["rejected_rows"][0]["row"] == 3
    tender_list = await client.get("/api/v1/tenders")
    assert [item["tender_id"] for item in tender_list.json()] == ["T-301"]


@pytest.mark.asyncio
async def test_disabled_rule_must_be_previewed_before_activation(operations_client):
    client, session_factory, _app = operations_client
    async with session_factory() as session:
        session.add(RecipientAddress(tenant_id="KEC-001", email="buyer@example.test"))
        await session.commit()
    now = datetime.now(timezone.utc)

    tender = await client.post(
        "/api/v1/tenders",
        json={
            "tender_id": "T-400",
            "project_name": "Cable supply",
            "stage": "Bid Submitted",
            "material_categories": ["Power cables"],
        },
    )
    assert tender.status_code == 201
    async with session_factory() as session:
        original = (
            await session.execute(
                select(TenderEvent).where(TenderEvent.event_id == tender.json()["event_id"])
            )
        ).scalar_one()
        session.add(TenderEvent(
            tenant_id=original.tenant_id,
            event_id=original.event_id,
            sender_entity_id=original.sender_entity_id,
            tender_ref=original.tender_ref,
            project_name=original.project_name,
            source_revision="older-revision",
            prior_stage="Reviewing",
            stage="Reviewing",
            occurred_at=now - timedelta(minutes=5),
            material_categories=original.material_categories,
            existing_win_probability_percent=original.existing_win_probability_percent,
            probability_updated_at=original.probability_updated_at,
            source_type=original.source_type,
            data_provenance=original.data_provenance,
            ingested_at=now - timedelta(minutes=5),
        ))
        await session.commit()
    rule = await client.post(
        "/api/v1/rules",
        json={
            "rule_id": "draft-preview",
            "name": "Preview before sending",
            "enabled": False,
            "trigger_stages": ["Bid Submitted"],
            "purpose": "Bid evaluation",
            "channel": "email",
            "selected_recipient_emails": ["buyer@example.test"],
            "routes": [{"material_categories": ["Power cables"]}],
        },
    )
    assert rule.status_code == 201, rule.text
    cannot_enable = await client.patch("/api/v1/rules/draft-preview/enabled", json={"enabled": True})
    assert cannot_enable.status_code == 409

    preview = await client.post("/api/v1/tenders/rules/draft-preview/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["matches"] == 1
    assert preview.json()["evaluated"] == 1
    enabled = await client.patch("/api/v1/rules/draft-preview/enabled", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True


@pytest.mark.asyncio
async def test_test_email_and_failed_delivery_retry_record_attempt_history(monkeypatch, operations_client):
    client, session_factory, _app = operations_client
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        event = TenderEvent(
            tenant_id="KEC-001",
            event_id="retry-event",
            sender_entity_id="KEC-001",
            tender_ref="T-500",
            project_name="Test project",
            source_revision="rev-1",
            prior_stage=None,
            stage="Bid Submitted",
            occurred_at=now,
            material_categories=["Power cables"],
            expected_need_window=None,
            existing_win_probability_percent=None,
            probability_updated_at=None,
            source_type="manual",
            data_provenance="test",
        )
        session.add(event)
        session.add(TenderEvent(
            tenant_id="KEC-001",
            event_id="retry-event",
            sender_entity_id="KEC-001",
            tender_ref="T-500",
            project_name="Test project - latest revision",
            source_revision="rev-2",
            prior_stage="Bid Submitted",
            stage="Bid Submitted",
            occurred_at=now + timedelta(minutes=1),
            ingested_at=now + timedelta(minutes=1),
            material_categories=["Power cables"],
            expected_need_window=None,
            existing_win_probability_percent=None,
            probability_updated_at=None,
            source_type="manual",
            data_provenance="test",
        ))
        session.add(RecipientAddress(tenant_id="KEC-001", email="buyer@example.test"))
        session.add(RecipientDecision(
            event_id="retry-event",
            tenant_id="KEC-001",
            subsidiary_entity_id="",
            recipient_user_id="buyer@example.test",
            disposition="candidate",
            reason="rule_matched",
            payload={"tender_ref": "T-500"},
        ))
        delivery = NotificationDelivery(
            event_id="retry-event",
            recipient_user_id="buyer@example.test",
            channel="email",
            status="failed",
            payload={"tender_ref": "T-500"},
            error_message="Temporary provider error",
            retry_count=1,
        )
        session.add(delivery)
        await session.flush()
        session.add(DeliveryAttempt(
            delivery_id=delivery.id,
            status="failed",
            error_message="Temporary provider error",
        ))
        await session.commit()
        delivery_id = delivery.id

    class FakeEmailAdapter:
        async def send(self, recipient, payload, approved_fields=None):
            return NotificationResult(
                recipient_user_id=recipient,
                channel="email",
                status="sent",
                message_id="fake-message-id",
            )

    monkeypatch.setattr(delivery_status, "get_adapter", lambda channel: FakeEmailAdapter())
    test_email = await client.post(
        "/api/v1/delivery-status/test-email",
        json={"recipient_email": "buyer@example.test"},
    )
    retry = await client.post(f"/api/v1/delivery-status/{delivery_id}/retry")
    attempts = await client.get(f"/api/v1/delivery-status/{delivery_id}/attempts")
    queue = await client.get("/api/v1/delivery-status/")
    stats = await client.get("/api/v1/delivery-status/stats")

    assert test_email.status_code == 200, test_email.text
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "sent"
    assert attempts.status_code == 200, attempts.text
    assert len(attempts.json()) == 2
    assert attempts.json()[0]["status"] == "sent"
    assert datetime.fromisoformat(attempts.json()[0]["created_at"]).utcoffset() == timedelta(0)
    assert queue.status_code == 200, queue.text
    assert len(queue.json()) == 1
    assert datetime.fromisoformat(queue.json()[0]["sent_at"]).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(queue.json()[0]["created_at"]).utcoffset() == timedelta(0)
    assert stats.status_code == 200, stats.text
    assert stats.json()["sent"] == 1
