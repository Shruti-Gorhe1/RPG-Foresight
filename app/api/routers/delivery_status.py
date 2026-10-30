"""Delivery status API — notification delivery stats and queue."""
from __future__ import annotations

import re
from typing import Any

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db.base import get_db_session
from db.models import DeliveryAttempt, NotificationDelivery, RecipientAddress, RecipientDecision, TenderEvent
from api.auth import get_current_user, CurrentUser, require_tenant
from api.schemas.routing import DeliveryStatsOut, NotificationDeliveryOut
from services.notification import get_adapter
import services.email_adapter  # noqa: F401
from shared.config import get_settings
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.delivery_status")


class TestEmailInput(BaseModel):
    recipient_email: str = Field(min_length=3, max_length=254)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.get("/stats", response_model=DeliveryStatsOut)
async def delivery_stats(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DeliveryStatsOut:
    """Aggregate delivery status counts for the authenticated tenant."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(NotificationDelivery.status, func.count(NotificationDelivery.id))
        .where(
            NotificationDelivery.event_id.in_(
                select(TenderEvent.event_id).where(TenderEvent.tenant_id == tenant_id)
            )
        )
        .group_by(NotificationDelivery.status)
    )
    counts = {status: count for status, count in result.all()}
    return DeliveryStatsOut(
        total=sum(counts.values()),
        pending=counts.get("pending", 0),
        sent=counts.get("sent", 0),
        delivered=counts.get("delivered", 0),
        failed=counts.get("failed", 0),
        suppressed=counts.get("suppressed", 0),
    )


@router.get("/", response_model=list[NotificationDeliveryOut])
async def list_deliveries(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[NotificationDeliveryOut]:
    """Delivery queue for the authenticated tenant, newest first."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.event_id.in_(
                select(TenderEvent.event_id).where(TenderEvent.tenant_id == tenant_id)
            )
        )
        .order_by(NotificationDelivery.created_at.desc())
        .limit(100)
    )
    deliveries = result.scalars().all()
    return [
        NotificationDeliveryOut(
            id=d.id,
            event_id=d.event_id,
            recipient_user_id=d.recipient_user_id,
            channel=d.channel,
            status=d.status,
            message_id=d.message_id,
            payload=d.payload or {},
            sent_at=_utc(d.sent_at) if d.sent_at else None,
            delivered_at=_utc(d.delivered_at) if d.delivered_at else None,
            error_message=d.error_message,
            retry_count=d.retry_count,
            created_at=_utc(d.created_at) if d.created_at else None,
        )
        for d in deliveries
    ]


@router.get("/configuration")
async def email_configuration(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    provider = settings.email_provider.strip().lower()
    if provider == "resend":
        configured = bool(settings.resend_api_key and settings.resend_from)
        sender = settings.resend_from
    elif provider == "smtp":
        configured = bool(settings.smtp_host and settings.smtp_port and settings.smtp_from)
        sender = settings.smtp_from
    else:
        configured = False
        sender = None
    return {"provider": provider, "configured": configured, "sender": sender, "secret_exposed": False}


@router.post("/test-email")
async def send_test_email(
    payload: TestEmailInput,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", payload.recipient_email) is None:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    tenant_id = require_tenant(current_user)
    recipient_result = await db.execute(
        select(RecipientAddress.id).where(
            RecipientAddress.tenant_id == tenant_id,
            RecipientAddress.email == payload.recipient_email,
        )
    )
    if recipient_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="Test email can only be sent to an address in this workspace's recipient address book")
    adapter = get_adapter("email")
    if adapter is None:
        raise HTTPException(status_code=503, detail="Email adapter is not available")
    result = await adapter.send(
        payload.recipient_email,
        {"project_name": "RPG Foresight email configuration test", "stage": "Test message"},
    )
    if result.status != "sent":
        raise HTTPException(status_code=502, detail=result.error or "Test email was not accepted by the provider")
    return {"status": "sent", "recipient": payload.recipient_email, "message_id": result.message_id}


@router.get("/{delivery_id}/attempts")
async def delivery_attempts(
    delivery_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    tenant_id = require_tenant(current_user)
    delivery_result = await db.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
    )
    delivery = delivery_result.scalar_one_or_none()
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    event_result = await db.execute(
        select(TenderEvent.id)
        .where(TenderEvent.event_id == delivery.event_id, TenderEvent.tenant_id == tenant_id)
        .limit(1)
    )
    if event_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    result = await db.execute(
        select(DeliveryAttempt)
        .where(DeliveryAttempt.delivery_id == delivery_id)
        .order_by(DeliveryAttempt.created_at.desc(), DeliveryAttempt.id.desc())
    )
    return [
        {
            "id": attempt.id,
            "delivery_id": attempt.delivery_id,
            "status": attempt.status,
            "message_id": attempt.message_id,
            "error_message": attempt.error_message,
            "created_at": _utc(attempt.created_at).isoformat() if attempt.created_at else None,
        }
        for attempt in result.scalars().all()
    ]


@router.post("/{delivery_id}/retry")
async def retry_delivery(
    delivery_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
    )
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    event_result = await db.execute(
        select(TenderEvent)
        .where(TenderEvent.event_id == delivery.event_id, TenderEvent.tenant_id == tenant_id)
        .order_by(TenderEvent.ingested_at.desc(), TenderEvent.id.desc())
        .limit(1)
    )
    event = event_result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if delivery.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed deliveries can be retried")

    decision_result = await db.execute(
        select(RecipientDecision).where(
            RecipientDecision.event_id == event.event_id,
            RecipientDecision.tenant_id == tenant_id,
            RecipientDecision.recipient_user_id == delivery.recipient_user_id,
            RecipientDecision.disposition == "candidate",
        ).order_by(RecipientDecision.decided_at.desc())
    )
    decision = decision_result.scalars().first()
    if decision is None:
        raise HTTPException(status_code=409, detail="No matching rule decision is available for retry")
    recipient_result = await db.execute(
        select(RecipientAddress.id).where(
            RecipientAddress.tenant_id == tenant_id,
            RecipientAddress.email == delivery.recipient_user_id,
        )
    )
    if recipient_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=409, detail="Recipient is no longer in the address book; delivery cannot be retried")
    adapter = get_adapter(delivery.channel)
    if adapter is None:
        raise HTTPException(status_code=503, detail=f"No adapter registered for channel '{delivery.channel}'")
    try:
        send_result = await adapter.send(
            delivery.recipient_user_id,
            delivery.payload or {},
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("manual_delivery_retry_failed", delivery_id=delivery_id, error=str(exc))
        send_result = None
        error_message = f"Delivery retry failed: {type(exc).__name__}"
    else:
        error_message = send_result.error
    delivery.status = send_result.status if send_result else "failed"
    delivery.message_id = send_result.message_id if send_result else None
    delivery.error_message = error_message
    delivery.sent_at = datetime.now(timezone.utc) if delivery.status == "sent" else None
    delivery.retry_count += 1
    db.add(DeliveryAttempt(
        delivery_id=delivery.id,
        status=delivery.status,
        message_id=delivery.message_id,
        error_message=delivery.error_message,
    ))
    await db.commit()
    return {"delivery_id": delivery_id, "status": delivery.status, "error_message": delivery.error_message}
