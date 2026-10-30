from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.auth import CurrentUser, get_current_user
from api.routers import recipients, rules
from api.routers.data_ingestion import sync_connector
from api.routers.recipients import RecipientAddressIn, create_recipient, update_recipient
from api.routers.rules import create_rule
from api.schemas.routing import RoutingRuleIn
from db.base import Base, get_db_session
from db.models import AuditEvent, RecipientAddress, RoutingRule as RoutingRuleModel
from db.models import SubsidiaryRoute, TenderEvent
from ingestion.connectors.registry import registry
from services.notification import NotificationAdapter, NotificationResult
from services.routing_service import run_routing_and_delivery


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_rule_uses_address_book_email_without_entity_policy(db_session) -> None:
    db_session.add(RecipientAddress(
        tenant_id="tenant-a",
        email="buyer@example.test",
        display_name="Tender Buyer",
    ))
    await db_session.commit()

    rule = await create_rule(
        RoutingRuleIn(
            rule_id="email-rule",
            name="Tender email alert",
            enabled=True,
            trigger_stages=["Bid Submitted"],
            purpose="Tender notification",
            channel="email",
            selected_recipient_emails=["buyer@example.test"],
            routes=[{"material_categories": ["Power cables"]}],
        ),
        db_session,
        CurrentUser("admin", "tenant-a"),
    )

    assert rule.rule_id == "email-rule"
    assert rule.tenant_id == "tenant-a"
    assert rule.selected_recipient_emails == ["buyer@example.test"]
    assert rule.routes[0].subsidiary_entity_id == ""
    assert rule.routes[0].material_categories == ["Power cables"]


@pytest.mark.asyncio
async def test_create_rule_rejects_addresses_not_in_tenant_address_book(db_session) -> None:
    with pytest.raises(HTTPException) as error:
        await create_rule(
            RoutingRuleIn(
                rule_id="unknown-recipient-rule",
                name="Tender email alert",
                trigger_stages=["Bid Submitted"],
                purpose="Tender notification",
                channel="email",
                selected_recipient_emails=["buyer@example.test"],
                routes=[{"material_categories": ["Power cables"]}],
            ),
            db_session,
            CurrentUser("admin", "tenant-a"),
        )

    assert error.value.status_code == 422
    assert "address book" in error.value.detail


@pytest.mark.asyncio
async def test_create_and_list_recipient_address_is_tenant_scoped(db_session) -> None:
    result = await create_recipient(
        RecipientAddressIn(email="  buyer@example.test ", display_name=" Buyer "),
        db_session,
        CurrentUser("admin", "tenant-a"),
    )

    assert result.email == "buyer@example.test"
    assert result.display_name == "Buyer"
    listed = await recipients.list_recipients(db_session, CurrentUser("admin", "tenant-a"))
    other_tenant = await recipients.list_recipients(db_session, CurrentUser("admin", "tenant-b"))
    assert [item.email for item in listed] == ["buyer@example.test"]
    assert other_tenant == []


@pytest.mark.asyncio
async def test_editing_address_updates_existing_rule_and_audits(db_session) -> None:
    recipient = RecipientAddress(tenant_id="tenant-a", email="old@example.test")
    rule = RoutingRuleModel(
        rule_id="editable-rule",
        tenant_id="tenant-a",
        name="Tender email",
        enabled=True,
        trigger_stages=["Bid Submitted"],
        purpose="Tender notification",
        channel="email",
        selected_recipient_email="old@example.test",
        selected_recipient_emails=["old@example.test", "other@example.test"],
        max_event_age_seconds=86400,
        max_probability_age_seconds=604800,
        version=1,
    )
    rule.routes.append(SubsidiaryRoute(subsidiary_entity_id="", material_categories=["Power cables"]))
    db_session.add_all([recipient, rule])
    await db_session.commit()

    updated = await update_recipient(
        recipient.id,
        RecipientAddressIn(email="new@example.test", display_name="Buyer"),
        db_session,
        CurrentUser("admin", "tenant-a"),
    )

    assert updated.email == "new@example.test"
    await db_session.refresh(rule)
    assert rule.selected_recipient_email == "new@example.test"
    assert rule.selected_recipient_emails == ["new@example.test", "other@example.test"]
    assert rule.version == 2
    audit = (
        await db_session.execute(
            select(AuditEvent).where(AuditEvent.action == "recipient_address_updated")
        )
    ).scalar_one()
    assert audit.actor == "admin"
    assert audit.details == {"previous_email": "old@example.test", "email": "new@example.test"}


@pytest.mark.asyncio
async def test_recipient_api_matches_frontend_and_enforces_tenant_scope(db_session) -> None:
    app = FastAPI()
    app.include_router(rules.router, prefix="/api/v1/rules")
    app.include_router(recipients.router, prefix="/api/v1/recipients")

    async def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("admin", "tenant-a")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/recipients")
        created = await client.post(
            "/api/v1/recipients",
            json={"email": "buyer@example.test", "display_name": "Buyer"},
        )
        duplicate = await client.post(
            "/api/v1/recipients",
            json={"email": "buyer@example.test"},
        )
        recipient_id = created.json()["id"]
        app.dependency_overrides[get_current_user] = lambda: CurrentUser("other", "tenant-b")
        cross_tenant_update = await client.patch(
            f"/api/v1/recipients/{recipient_id}",
            json={"email": "attacker@example.test"},
        )
        cross_tenant_delete = await client.delete(f"/api/v1/recipients/{recipient_id}")

    assert listing.status_code == 200
    assert created.status_code == 201
    assert created.json()["email"] == "buyer@example.test"
    assert duplicate.status_code == 409
    assert cross_tenant_update.status_code == 404
    assert cross_tenant_delete.status_code == 404


@pytest.mark.asyncio
async def test_delete_routing_rule_is_tenant_scoped_and_audited(db_session) -> None:
    rule = RoutingRuleModel(
        rule_id="deletable-rule",
        tenant_id="tenant-a",
        name="Rule to delete",
        enabled=True,
        trigger_stages=["Bid Submitted"],
        purpose="Tender notification",
        channel="email",
        selected_recipient_email="buyer@example.test",
        selected_recipient_emails=["buyer@example.test"],
        max_event_age_seconds=86400,
        max_probability_age_seconds=604800,
        version=1,
    )
    rule.routes.append(SubsidiaryRoute(subsidiary_entity_id="", material_categories=["Power cables"]))
    db_session.add(rule)
    await db_session.commit()

    app = FastAPI()
    app.include_router(rules.router, prefix="/api/v1/rules")

    async def override_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("admin", "tenant-a")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/v1/rules/deletable-rule")
        app.dependency_overrides[get_current_user] = lambda: CurrentUser("other", "tenant-b")
        cross_tenant = await client.delete("/api/v1/rules/deletable-rule")

    assert response.status_code == 204
    assert cross_tenant.status_code == 404
    assert (
        await db_session.execute(
            select(RoutingRuleModel).where(RoutingRuleModel.rule_id == "deletable-rule")
        )
    ).scalar_one_or_none() is None
    audit = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "routing_rule_deleted",
                AuditEvent.object_id == "deletable-rule",
            )
        )
    ).scalar_one()
    assert audit.actor == "admin"


@pytest.mark.asyncio
async def test_matching_rules_send_once_to_address_book_email(monkeypatch, db_session) -> None:
    now = datetime.now(timezone.utc)
    event = TenderEvent(
        tenant_id="tenant-a",
        event_id="tender-event",
        sender_entity_id="source",
        tender_ref="T-123",
        project_name="Cable project",
        source_revision="rev-1",
        prior_stage="Technical evaluation",
        stage="Bid Submitted",
        occurred_at=now,
        material_categories=["Power cables"],
        expected_need_window=None,
        existing_win_probability_percent=None,
        probability_updated_at=None,
        source_type="manual",
        data_provenance="test",
    )
    db_session.add(RecipientAddress(tenant_id="tenant-a", email="buyer@example.test"))
    for rule_id in ("email-rule-1", "email-rule-2"):
        rule = RoutingRuleModel(
            rule_id=rule_id,
            tenant_id="tenant-a",
            name=rule_id,
            enabled=True,
            trigger_stages=["Bid Submitted"],
            purpose="Tender notification",
            channel="email",
            selected_recipient_email="buyer@example.test",
            selected_recipient_emails=["buyer@example.test"],
            max_event_age_seconds=3600,
            max_probability_age_seconds=3600,
            version=1,
        )
        rule.routes.append(SubsidiaryRoute(subsidiary_entity_id="", material_categories=["Power cables"]))
        db_session.add(rule)
    db_session.add(event)
    await db_session.commit()

    class FakeEmailAdapter(NotificationAdapter):
        def __init__(self):
            super().__init__("email")
            self.sent = 0

        async def send(self, recipient_user_id, payload, approved_fields=None):
            self.sent += 1
            return NotificationResult(recipient_user_id, "email", "sent", "test-message")

    adapter = FakeEmailAdapter()
    monkeypatch.setattr("services.routing_service.get_adapter", lambda channel: adapter)
    result = await run_routing_and_delivery(db_session)

    assert result["rules_applied"] == 2
    assert result["decisions_created"] == 1
    assert result["deliveries_created"] == 1
    assert adapter.sent == 1


@pytest.mark.asyncio
async def test_disabled_connector_cannot_be_synced_manually(monkeypatch, db_session) -> None:
    monkeypatch.setattr(
        registry,
        "get",
        lambda connector_id: SimpleNamespace(is_active=True, is_enabled=False),
    )

    with pytest.raises(HTTPException) as error:
        await sync_connector("zoho", db_session, CurrentUser("admin", "tenant-a"))

    assert error.value.status_code == 409
