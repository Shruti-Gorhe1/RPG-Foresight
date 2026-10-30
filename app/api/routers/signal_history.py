"""Signal history API — tender events + audit trail."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.base import get_db_session
from db.models import AuditEvent, TenderEvent
from api.auth import get_current_user, CurrentUser, require_tenant
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.signal_history")


@router.get("/", response_model=list[dict[str, Any]])
async def list_signal_history(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Tender signal history for the authenticated tenant, newest first."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(TenderEvent)
        .where(TenderEvent.tenant_id == tenant_id)
        .order_by(TenderEvent.ingested_at.desc())
    )
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "event_id": e.event_id,
            "tender_id": e.tender_ref,
            "project_name": e.project_name,
            "stage": e.stage,
            "prior_stage": e.prior_stage,
            "source_type": e.source_type,
            "data_provenance": e.data_provenance,
            "existing_win_probability_percent": e.existing_win_probability_percent,
            "material_categories": e.material_categories or [],
            "source_updated_at": e.occurred_at.isoformat() if e.occurred_at else None,
            "ingested_at": e.ingested_at.isoformat() if e.ingested_at else None,
            "sender_entity_id": e.sender_entity_id,
            "tenant_id": e.tenant_id,
            "source_revision": e.source_revision,
        }
        for e in events
    ]


@router.get("/audit", response_model=list[dict[str, Any]])
async def list_audit_events(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Audit trail for the authenticated tenant."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "actor": e.actor,
            "action": e.action,
            "object_type": e.object_type,
            "object_id": e.object_id,
            "result": e.result,
            "reason": e.reason,
            "details": e.details or {},
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
