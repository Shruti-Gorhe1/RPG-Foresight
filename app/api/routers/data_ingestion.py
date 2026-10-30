"""Data ingestion router — automated data flow, no manual entry.

Endpoints:
  GET    /api/v1/data-ingestion/tenders        — List tender events (dashboard, tenant-scoped)
  GET    /api/v1/data-ingestion/subsidiaries   — List subsidiaries (admin/subsidiary-viewer)
  GET    /api/v1/data-ingestion/subsidiaries/{id}/tenders — List subsidiary tender events
  POST   /api/v1/data-ingestion/subsidiaries/{id}/tenders — Add a subsidiary tender record
  POST   /api/v1/data-ingestion/sync           — Trigger agentic ingestion pipeline
  GET    /api/v1/data-ingestion/connectors     — List registered connectors
  POST   /api/v1/data-ingestion/connectors/{id}/sync — Sync a specific connector
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.base import get_db_session
from db.models import TenderEvent, Connector, ConnectorRun
from api.auth import get_current_user, CurrentUser, require_tenant
from shared.subsidiaries import SUBSIDIARIES
from services.ingestion_service import run_ingestion_pipeline
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.data_ingestion")
SUBSIDIARY_ACCESS_ROLES = {"admin", "subsidiary_viewer"}


class SubsidiaryTenderInput(BaseModel):
    tender_id: str = Field(min_length=1, max_length=64)
    project_name: str = Field(min_length=1, max_length=128)
    stage: Literal["Won", "Lost", "In Progress"]
    material_categories: list[str] = Field(default_factory=lambda: ["General"], min_length=1)
    tender_value: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default="INR", min_length=3, max_length=8)
    opening_at: datetime | None = None
    closing_at: datetime | None = None


def _require_subsidiary_access(current_user: CurrentUser) -> None:
    if not SUBSIDIARY_ACCESS_ROLES.intersection(current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access subsidiary tender records",
        )


def _serialize_event(event: TenderEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "event_id": event.event_id,
        "tender_id": event.tender_ref,
        "project_name": event.project_name,
        "stage": event.stage,
        "prior_stage": event.prior_stage,
        "source_type": event.source_type,
        "data_provenance": event.data_provenance,
        "existing_win_probability_percent": event.existing_win_probability_percent,
        "tender_value": event.tender_value,
        "currency": event.currency,
        "opening_at": event.opening_at.isoformat() if event.opening_at else None,
        "closing_at": event.closing_at.isoformat() if event.closing_at else None,
        "source_updated_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
        "sender_entity_id": event.sender_entity_id,
        "tenant_id": event.tenant_id,
        "material_categories": event.material_categories or [],
        "source_revision": event.source_revision,
    }


def _get_subsidiary(subsidiary_id: str) -> dict[str, str]:
    subsidiary = SUBSIDIARIES.get(subsidiary_id.casefold())
    if subsidiary is None:
        raise HTTPException(status_code=404, detail="Subsidiary not found")
    return subsidiary


@router.get("/subsidiaries")
async def list_subsidiaries(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, str]]:
    _require_subsidiary_access(current_user)
    return [
        {"id": subsidiary_id, "name": subsidiary["name"]}
        for subsidiary_id, subsidiary in SUBSIDIARIES.items()
    ]


@router.get("/subsidiaries/{subsidiary_id}/tenders")
async def list_subsidiary_tenders(
    subsidiary_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    _require_subsidiary_access(current_user)
    subsidiary = _get_subsidiary(subsidiary_id)
    result = await db.execute(
        select(TenderEvent)
        .where(TenderEvent.tenant_id == subsidiary["tenant_id"])
        .order_by(TenderEvent.ingested_at.desc())
    )
    return [_serialize_event(event) for event in result.scalars().all()]


@router.post(
    "/subsidiaries/{subsidiary_id}/tenders",
    status_code=status.HTTP_201_CREATED,
)
async def create_subsidiary_tender(
    subsidiary_id: str,
    payload: SubsidiaryTenderInput,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _require_subsidiary_access(current_user)
    subsidiary = _get_subsidiary(subsidiary_id)
    now = datetime.now(timezone.utc)
    event = TenderEvent(
        tenant_id=subsidiary["tenant_id"],
        event_id=f"manual-{uuid.uuid4().hex}",
        sender_entity_id=subsidiary["sender_entity_id"],
        tender_ref=payload.tender_id.strip(),
        project_name=payload.project_name.strip(),
        source_revision=f"manual-{uuid.uuid4().hex[:12]}",
        prior_stage=None,
        stage=payload.stage,
        occurred_at=now,
        material_categories=payload.material_categories,
        expected_need_window=None,
        existing_win_probability_percent=None,
        probability_updated_at=None,
        source_type="manual",
        data_provenance=f"Manual entry by {current_user.user_id}",
        ingested_at=now,
        region=None,
        tender_value=payload.tender_value,
        currency=payload.currency,
        opening_at=payload.opening_at,
        closing_at=payload.closing_at,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return _serialize_event(event)


@router.get("/tenders")
async def list_tenders(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return pipeline events, excluding records reserved for the subsidiary view."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(TenderEvent)
        .where(
            TenderEvent.tenant_id == tenant_id,
            ~TenderEvent.data_provenance.like(
                "Demo data: synthetic subsidiary CRM records%"
            ),
        )
        .order_by(TenderEvent.ingested_at.desc())
    )
    events = result.scalars().all()
    return [_serialize_event(event) for event in events]


@router.post("/sync")
async def sync_data(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger the agentic ingestion pipeline.

    Runs all enabled connectors, normalizes, deduplicates, and writes
    new tender events to the database. No manual data entry required.
    """
    log.info("sync_initiated", user_id=current_user.user_id, tenant_id=current_user.tenant_id)
    try:
        summary = await run_ingestion_pipeline()
        return summary
    except Exception as exc:  # noqa: BLE001
        log.exception("sync_failed", user_id=current_user.user_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion sync failed: {str(exc)}",
        )


@router.get("/connectors")
async def list_connectors(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all registered connectors with their status."""
    from ingestion.connectors.registry import registry

    connectors = registry.list()
    result = []
    for c in connectors:
        last_run = await db.execute(
            select(ConnectorRun)
            .where(ConnectorRun.connector_id == c.connector_id)
            .order_by(ConnectorRun.started_at.desc())
            .limit(1)
        )
        run = last_run.scalar_one_or_none()

        result.append({
            "connector_id": c.connector_id,
            "name": c.name,
            "source_type": c.source_type,
            "source_name": c.source_name,
            "description": c.description,
            "is_active": c.is_active,
            "is_enabled": c.is_enabled,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "last_success_at": c.last_success_at.isoformat() if c.last_success_at else None,
            "last_error": c.last_error,
            "last_run": {
                "status": run.status if run else None,
                "records_fetched": run.records_fetched if run else 0,
                "records_created": run.records_created if run else 0,
                "started_at": run.started_at.isoformat() if run and run.started_at else None,
                "errors": run.errors or [] if run else [],
            } if run else None,
        })
    return result


@router.post("/connectors/{connector_id}/sync")
async def sync_connector(
    connector_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Sync a single connector on demand."""
    from ingestion.connectors.registry import registry

    connector = registry.get(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found",
        )
    if not connector.is_active or not connector.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Connector '{connector_id}' is disabled",
        )

    existing_ids: set[tuple[str, str]] = set()
    result = await db.execute(select(TenderEvent.event_id, TenderEvent.source_revision))
    for eid, rev in result.all():
        existing_ids.add((eid or "", rev or ""))

    result_obj = await connector.run(existing_ids)

    from agents.nodes.db_writer import db_writer_node
    from agents.state import AgentState

    state: AgentState = {
        "session_id": f"sync-{connector_id}",
        "messages": [],
        "current_step": "write",
        "step_status": "in_progress",
        "turn_count": 1,
        "collected": {
            "ingestion": {
                "connector_results": {
                    connector_id: {
                        "source_name": result_obj.source_name,
                        "records": result_obj.records,
                        "errors": result_obj.errors,
                        "count": len(result_obj.records),
                    }
                },
                "total_created": 0,
                "errors": result_obj.errors,
            }
        },
    }
    state = await db_writer_node(state)

    from agents.nodes.route_signals_agent import route_signals_agent_node

    state = await route_signals_agent_node(state)
    routing_summary = state.get("collected", {}).get("ingestion", {}).get("routing", {})

    errors = list(result_obj.errors)
    if routing_summary.get("status") != "completed":
        reason = routing_summary.get("error") or routing_summary.get("reason") or "unknown"
        errors.append(f"routing_{routing_summary['status']}: {reason}")
    elif routing_summary.get("deliveries_failed", 0):
        errors.append(
            f"{routing_summary['deliveries_failed']} notification delivery attempt(s) failed"
        )

    return {
        "connector_id": connector_id,
        "source_name": result_obj.source_name,
        "records_fetched": len(result_obj.records),
        "status": "failed" if errors else "completed",
        "errors": errors,
        "routing": routing_summary,
    }