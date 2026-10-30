from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.auth import CurrentUser, get_current_user
from api.routers import data_ingestion
from db.base import Base, get_db_session
from db.models import TenderEvent
from ingestion.connectors.subsidiary_demo import SubsidiaryDemoConnector
from ingestion.connectors.registry import registry


@pytest_asyncio.fixture
async def subsidiary_client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(data_ingestion.router, prefix="/api/v1/data-ingestion")

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        "ops-user", "KEC-001", roles=["admin"]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_factory, app
    await engine.dispose()


@pytest.mark.asyncio
async def test_subsidiary_demo_connector_normalizes_each_company():
    registered = registry.get("subsidiary-demo")
    assert registered is not None and registered.is_enabled
    connector = SubsidiaryDemoConnector("test-subsidiary-demo")
    fetched = await connector.fetch()
    normalized = [await connector.normalize(record) for record in fetched.records]

    assert len(normalized) == 9
    assert {record["tenant_id"] for record in normalized if record} == {
        "KEC-001",
        "CEAT-001",
        "RAYCHEM-001",
    }
    assert {record["stage"] for record in normalized if record} == {
        "Won",
        "Lost",
        "In Progress",
    }
    assert all(record["data_provenance"].startswith("Demo data:") for record in normalized if record)
    assert len({(record["event_id"], record["source_revision"]) for record in normalized if record}) == 9


@pytest.mark.asyncio
async def test_subsidiary_dashboard_access_and_manual_detail_creation(subsidiary_client):
    client, session_factory, app = subsidiary_client
    async with session_factory() as session:
        session.add_all([
            TenderEvent(
                tenant_id=tenant_id,
                event_id=f"{tenant_id}-event",
                sender_entity_id=f"{tenant_id}-ENTITY",
                tender_ref=f"{tenant_id}-ref",
                project_name=f"{tenant_id} project",
                source_revision="demo-v1",
                prior_stage=None,
                stage="Won",
                occurred_at=datetime.now(timezone.utc),
                material_categories=["Power systems"],
                expected_need_window=None,
                existing_win_probability_percent=None,
                probability_updated_at=None,
                source_type="crm",
                data_provenance="Demo data: test fixture",
            )
            for tenant_id in ("KEC-001", "CEAT-001")
        ])
        session.add(TenderEvent(
            tenant_id="KEC-001",
            event_id="DEMO-KEC-001",
            sender_entity_id="KEC-ENTITY",
            tender_ref="DEMO-KEC-001",
            project_name="KEC synthetic subsidiary record",
            source_revision="demo-v1",
            prior_stage=None,
            stage="Won",
            occurred_at=datetime.now(timezone.utc),
            material_categories=["Power systems"],
            expected_need_window=None,
            existing_win_probability_percent=None,
            probability_updated_at=None,
            source_type="crm",
            data_provenance="Demo data: synthetic subsidiary CRM records",
        ))
        await session.commit()

    dashboard_tenders = await client.get("/api/v1/data-ingestion/tenders")
    assert dashboard_tenders.status_code == 200
    assert [item["event_id"] for item in dashboard_tenders.json()] == ["KEC-001-event"]

    subsidiaries = await client.get("/api/v1/data-ingestion/subsidiaries")
    assert subsidiaries.status_code == 200
    assert [item["name"] for item in subsidiaries.json()] == ["KEC", "CEAT", "RayChem"]

    ceat_tenders = await client.get("/api/v1/data-ingestion/subsidiaries/ceat/tenders")
    assert ceat_tenders.status_code == 200
    assert [item["tenant_id"] for item in ceat_tenders.json()] == ["CEAT-001"]
    kec_tenders = await client.get("/api/v1/data-ingestion/subsidiaries/kec/tenders")
    assert kec_tenders.status_code == 200
    assert {item["event_id"] for item in kec_tenders.json()} == {
        "KEC-001-event",
        "DEMO-KEC-001",
    }

    created = await client.post(
        "/api/v1/data-ingestion/subsidiaries/raychem/tenders",
        json={
            "tender_id": "RC-100",
            "project_name": "Cable protection package",
            "stage": "In Progress",
            "material_categories": ["Cable accessories"],
            "tender_value": 250000,
            "currency": "INR",
            "opening_at": "2026-02-01T00:00:00Z",
            "closing_at": "2026-03-01T00:00:00Z",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["tenant_id"] == "RAYCHEM-001"
    assert created.json()["sender_entity_id"] == "RAYCHEM-ENTITY"
    assert created.json()["stage"] == "In Progress"

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        "viewer", "KEC-001", roles=["reader"]
    )
    forbidden = await client.get("/api/v1/data-ingestion/subsidiaries")
    assert forbidden.status_code == 403
