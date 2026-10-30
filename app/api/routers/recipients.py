"""Tenant-scoped recipient email address book."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import CurrentUser, get_current_user, require_tenant
from api.schemas.routing import RecipientAddressOut, RecipientDecisionOut
from db.base import get_db_session
from db.models import AuditEvent, RecipientAddress, RecipientDecision, RoutingRule
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.recipients")


class RecipientAddressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    display_name: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is None:
            raise ValueError("Enter a valid email address")
        return value.casefold()

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


@router.get("", response_model=list[RecipientAddressOut], include_in_schema=False)
@router.get("/", response_model=list[RecipientAddressOut])
async def list_recipients(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RecipientAddressOut]:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RecipientAddress)
        .where(RecipientAddress.tenant_id == tenant_id)
        .order_by(RecipientAddress.email)
    )
    return [
        RecipientAddressOut(
            id=recipient.id,
            email=recipient.email,
            display_name=recipient.display_name,
            created_at=recipient.created_at,
        )
        for recipient in result.scalars().all()
    ]


@router.get("/decisions", response_model=list[RecipientDecisionOut])
async def list_decisions(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RecipientDecisionOut]:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RecipientDecision)
        .where(RecipientDecision.tenant_id == tenant_id)
        .order_by(RecipientDecision.decided_at.desc())
    )
    return [
        RecipientDecisionOut(
            id=decision.id,
            event_id=decision.event_id,
            tenant_id=decision.tenant_id,
            subsidiary_entity_id=decision.subsidiary_entity_id,
            recipient_user_id=decision.recipient_user_id,
            disposition=decision.disposition,
            reason=decision.reason,
            payload=decision.payload or {},
            decided_at=decision.decided_at,
        )
        for decision in result.scalars().all()
    ]


@router.post("", response_model=RecipientAddressOut, status_code=status.HTTP_201_CREATED)
async def create_recipient(
    payload: RecipientAddressIn,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> RecipientAddressOut:
    tenant_id = require_tenant(current_user)
    recipient = RecipientAddress(
        tenant_id=tenant_id,
        email=payload.email,
        display_name=payload.display_name,
    )
    db.add(recipient)
    try:
        await db.flush()
        db.add(AuditEvent(
            tenant_id=tenant_id,
            actor=current_user.user_id,
            action="recipient_address_created",
            object_type="recipient_address",
            object_id=str(recipient.id),
            details={"email": recipient.email},
            result="success",
        ))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already in the address book",
        ) from exc
    await db.refresh(recipient)
    return RecipientAddressOut(
        id=recipient.id,
        email=recipient.email,
        display_name=recipient.display_name,
        created_at=recipient.created_at,
    )


@router.patch("/{recipient_id}", response_model=RecipientAddressOut)
async def update_recipient(
    recipient_id: int,
    payload: RecipientAddressIn,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> RecipientAddressOut:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RecipientAddress).where(
            RecipientAddress.id == recipient_id,
            RecipientAddress.tenant_id == tenant_id,
        )
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    old_email = recipient.email
    recipient.email = payload.email
    recipient.display_name = payload.display_name
    if old_email != recipient.email:
        rules_result = await db.execute(
            select(RoutingRule).where(RoutingRule.tenant_id == tenant_id)
        )
        for rule in rules_result.scalars().all():
            addresses = list(rule.selected_recipient_emails or [])
            if not addresses and rule.selected_recipient_email:
                addresses = [rule.selected_recipient_email]
            if old_email not in addresses:
                continue
            rule.selected_recipient_emails = list(dict.fromkeys(
                recipient.email if email == old_email else email for email in addresses
            ))
            if rule.selected_recipient_email == old_email:
                rule.selected_recipient_email = recipient.email
            rule.version += 1
    db.add(AuditEvent(
        tenant_id=tenant_id,
        actor=current_user.user_id,
        action="recipient_address_updated",
        object_type="recipient_address",
        object_id=str(recipient.id),
        details={"previous_email": old_email, "email": recipient.email},
        result="success",
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already in the address book",
        ) from exc
    await db.refresh(recipient)
    return RecipientAddressOut(
        id=recipient.id,
        email=recipient.email,
        display_name=recipient.display_name,
        created_at=recipient.created_at,
    )


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipient(
    recipient_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RecipientAddress).where(
            RecipientAddress.id == recipient_id,
            RecipientAddress.tenant_id == tenant_id,
        )
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    result = await db.execute(
        select(RoutingRule).where(RoutingRule.tenant_id == tenant_id)
    )
    for rule in result.scalars().all():
        addresses = list(rule.selected_recipient_emails or [])
        if not addresses and rule.selected_recipient_email:
            addresses = [rule.selected_recipient_email]
        if recipient.email not in addresses:
            continue
        rule.selected_recipient_emails = [
            email for email in addresses if email != recipient.email
        ]
        rule.selected_recipient_email = (
            rule.selected_recipient_emails[0]
            if rule.selected_recipient_emails
            else None
        )
        rule.version += 1
    db.add(AuditEvent(
        tenant_id=tenant_id,
        actor=current_user.user_id,
        action="recipient_address_deleted",
        object_type="recipient_address",
        object_id=str(recipient.id),
        details={"email": recipient.email},
        result="success",
    ))
    await db.execute(
        delete(RecipientAddress).where(
            RecipientAddress.id == recipient.id,
            RecipientAddress.tenant_id == tenant_id,
        )
    )
    await db.commit()
