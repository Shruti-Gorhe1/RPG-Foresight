"""Routing rules API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db.base import get_db_session
from db.models import AuditEvent, RecipientAddress, RoutingRule, SubsidiaryRoute
from api.auth import get_current_user, CurrentUser, require_tenant
from api.schemas.routing import RoutingRuleOut, SubsidiaryRouteOut, RoutingRuleIn
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.rules")


class RuleEnabledIn(BaseModel):
    enabled: bool


@router.get("", response_model=list[RoutingRuleOut], include_in_schema=False)
@router.get("/", response_model=list[RoutingRuleOut])
async def list_rules(
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RoutingRuleOut]:
    """List routing rules for the authenticated tenant."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.routes))
        .where(RoutingRule.tenant_id == tenant_id)
        .order_by(RoutingRule.created_at.desc())
    )
    rules = result.scalars().all()
    return [
        RoutingRuleOut(
            id=r.id,
            rule_id=r.rule_id,
            tenant_id=r.tenant_id,
            name=r.name,
            description=r.description,
            enabled=r.enabled,
            trigger_stages=list(r.trigger_stages or []),
            min_win_probability_percent=r.min_win_probability_percent,
            purpose=r.purpose,
            channel=r.channel,
            selected_recipient_email=r.selected_recipient_email,
            selected_recipient_emails=list(r.selected_recipient_emails or []) or ([r.selected_recipient_email] if r.selected_recipient_email else []),
            regions=list(r.regions or []),
            tender_currency=r.tender_currency,
            minimum_tender_value=r.minimum_tender_value,
            maximum_tender_value=r.maximum_tender_value,
            minimum_days_to_close=r.minimum_days_to_close,
            maximum_days_to_close=r.maximum_days_to_close,
            max_event_age_seconds=r.max_event_age_seconds,
            max_probability_age_seconds=r.max_probability_age_seconds,
            version=r.version,
            created_at=r.created_at,
            previewed_at=r.previewed_at,
            routes=[
                SubsidiaryRouteOut(
                    id=sr.id,
                    rule_id=sr.rule_id,
                    subsidiary_entity_id=sr.subsidiary_entity_id,
                    material_categories=list(sr.material_categories or []),
                )
                for sr in (r.routes or [])
            ],
        )
        for r in rules
    ]


@router.get("/{rule_id}", response_model=RoutingRuleOut)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoutingRuleOut:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.routes))
        .where(RoutingRule.rule_id == rule_id, RoutingRule.tenant_id == tenant_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return RoutingRuleOut(
        id=rule.id,
        rule_id=rule.rule_id,
        tenant_id=rule.tenant_id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        trigger_stages=list(rule.trigger_stages or []),
        min_win_probability_percent=rule.min_win_probability_percent,
        purpose=rule.purpose,
        channel=rule.channel,
        selected_recipient_email=rule.selected_recipient_email,
        selected_recipient_emails=list(rule.selected_recipient_emails or []) or ([rule.selected_recipient_email] if rule.selected_recipient_email else []),
        regions=list(rule.regions or []),
        tender_currency=rule.tender_currency,
        minimum_tender_value=rule.minimum_tender_value,
        maximum_tender_value=rule.maximum_tender_value,
        minimum_days_to_close=rule.minimum_days_to_close,
        maximum_days_to_close=rule.maximum_days_to_close,
        max_event_age_seconds=rule.max_event_age_seconds,
        max_probability_age_seconds=rule.max_probability_age_seconds,
        version=rule.version,
        created_at=rule.created_at,
        previewed_at=rule.previewed_at,
        routes=[
            SubsidiaryRouteOut(
                id=sr.id,
                rule_id=sr.rule_id,
                subsidiary_entity_id=sr.subsidiary_entity_id,
                material_categories=list(sr.material_categories or []),
            )
            for sr in (rule.routes or [])
        ],
    )


@router.post("", response_model=RoutingRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RoutingRuleIn,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoutingRuleOut:
    tenant_id = require_tenant(current_user)
    selected_emails = list(dict.fromkeys(
        ([payload.selected_recipient_email] if payload.selected_recipient_email else [])
        + payload.selected_recipient_emails
    ))
    if not selected_emails:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one email recipient from the address book",
        )
    if payload.minimum_tender_value is not None and payload.maximum_tender_value is not None and payload.minimum_tender_value > payload.maximum_tender_value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Minimum tender value cannot exceed maximum")
    if payload.minimum_days_to_close is not None and payload.maximum_days_to_close is not None and payload.minimum_days_to_close > payload.maximum_days_to_close:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Minimum days to close cannot exceed maximum")
    if (payload.minimum_tender_value is not None or payload.maximum_tender_value is not None) and not payload.tender_currency:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a currency when setting tender value limits")
    address_result = await db.execute(
        select(RecipientAddress.email).where(
            RecipientAddress.tenant_id == tenant_id,
            RecipientAddress.email.in_(selected_emails),
        )
    )
    saved_emails = set(address_result.scalars().all())
    unknown_emails = set(selected_emails) - saved_emails
    if unknown_emails:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Add recipient(s) to the address book before selecting them: {', '.join(sorted(unknown_emails))}",
        )
    existing = await db.execute(select(RoutingRule).where(RoutingRule.rule_id == payload.rule_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rule ID already exists")
    rule = RoutingRule(
        rule_id=payload.rule_id,
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        trigger_stages=list(payload.trigger_stages),
        min_win_probability_percent=payload.min_win_probability_percent,
        purpose=payload.purpose,
        channel=payload.channel,
        selected_recipient_email=selected_emails[0],
        selected_recipient_emails=selected_emails,
        regions=[region.strip() for region in payload.regions if region.strip()],
        tender_currency=payload.tender_currency.strip().upper() if payload.tender_currency else None,
        minimum_tender_value=payload.minimum_tender_value,
        maximum_tender_value=payload.maximum_tender_value,
        minimum_days_to_close=payload.minimum_days_to_close,
        maximum_days_to_close=payload.maximum_days_to_close,
        max_event_age_seconds=payload.max_event_age_seconds,
        max_probability_age_seconds=payload.max_probability_age_seconds,
        version=1,
    )
    try:
        db.add(rule)
        await db.flush()
        for r in payload.routes:
            db.add(SubsidiaryRoute(rule_id=rule.rule_id, subsidiary_entity_id=r.subsidiary_entity_id, material_categories=list(r.material_categories)))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        log.exception("rule_create_failed", rule_id=payload.rule_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A rule with this ID already exists",
        ) from exc
    result = await db.execute(select(RoutingRule).options(selectinload(RoutingRule.routes)).where(RoutingRule.rule_id == rule.rule_id))
    rule = result.scalar_one()
    return RoutingRuleOut(
        id=rule.id,
        rule_id=rule.rule_id,
        tenant_id=rule.tenant_id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        trigger_stages=list(rule.trigger_stages or []),
        min_win_probability_percent=rule.min_win_probability_percent,
        purpose=rule.purpose,
        channel=rule.channel,
        selected_recipient_email=rule.selected_recipient_email,
        selected_recipient_emails=list(rule.selected_recipient_emails or []) or ([rule.selected_recipient_email] if rule.selected_recipient_email else []),
        regions=list(rule.regions or []),
        tender_currency=rule.tender_currency,
        minimum_tender_value=rule.minimum_tender_value,
        maximum_tender_value=rule.maximum_tender_value,
        minimum_days_to_close=rule.minimum_days_to_close,
        maximum_days_to_close=rule.maximum_days_to_close,
        max_event_age_seconds=rule.max_event_age_seconds,
        max_probability_age_seconds=rule.max_probability_age_seconds,
        version=rule.version,
        created_at=rule.created_at,
        previewed_at=rule.previewed_at,
        routes=[SubsidiaryRouteOut(id=sr.id, rule_id=sr.rule_id, subsidiary_entity_id=sr.subsidiary_entity_id, material_categories=list(sr.material_categories or [])) for sr in rule.routes],
    )


@router.patch("/{rule_id}/enabled", response_model=RoutingRuleOut)
async def set_rule_enabled(
    rule_id: str,
    payload: RuleEnabledIn,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> RoutingRuleOut:
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RoutingRule).options(selectinload(RoutingRule.routes)).where(
            RoutingRule.rule_id == rule_id, RoutingRule.tenant_id == tenant_id
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if payload.enabled and rule.previewed_at is None:
        raise HTTPException(status_code=409, detail="Preview this rule against recent tenders before enabling it")
    rule.enabled = payload.enabled
    await db.commit()
    return await get_rule(rule_id, db, current_user)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete one tenant-owned routing rule and preserve its audit record."""
    tenant_id = require_tenant(current_user)
    result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.routes))
        .where(RoutingRule.rule_id == rule_id, RoutingRule.tenant_id == tenant_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    db.add(AuditEvent(
        tenant_id=tenant_id,
        actor=current_user.user_id,
        action="routing_rule_deleted",
        object_type="routing_rule",
        object_id=rule.rule_id,
        details={
            "name": rule.name,
            "enabled": rule.enabled,
            "selected_recipient_emails": list(rule.selected_recipient_emails or [])
            or ([rule.selected_recipient_email] if rule.selected_recipient_email else []),
        },
        result="success",
    ))
    await db.delete(rule)
    await db.commit()
