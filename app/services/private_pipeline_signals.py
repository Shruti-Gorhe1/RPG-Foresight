"""Deterministic rules for privately routing approved bid-pipeline signals.

This module prepares recipient-scoped alert candidates only. It does not read a
CRM, establish that supplied policies are authentic, or send notifications.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PipelineEvent(_StrictModel):
    tenant_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    sender_entity_id: str = Field(min_length=1)
    tender_ref: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    prior_stage: str | None = None
    stage: str = Field(min_length=1)
    occurred_at: datetime
    material_categories: list[str] = Field(min_length=1)
    expected_need_window: str | None = None
    existing_win_probability_percent: float | None = Field(default=None, ge=0, le=100)
    probability_updated_at: datetime | None = None
    region: str | None = None
    tender_value: float | None = None
    currency: str | None = None
    closing_at: datetime | None = None


class SubsidiaryRoute(_StrictModel):
    subsidiary_entity_id: str = ""
    recipient_user_ids: list[str] = Field(min_length=1)
    material_categories: list[str] = Field(min_length=1)


class SignalRule(_StrictModel):
    enabled: bool = False
    tenant_id: str = Field(min_length=1)
    sender_entity_id: str = Field(min_length=1)
    trigger_stages: list[str] = Field(min_length=1)
    min_win_probability_percent: float | None = Field(default=None, ge=0, le=100)
    purpose: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    max_event_age_seconds: int = Field(default=86_400, ge=0)
    max_probability_age_seconds: int = Field(default=604_800, ge=0)
    regions: list[str] = Field(default_factory=list)
    tender_currency: str | None = None
    minimum_tender_value: float | None = None
    maximum_tender_value: float | None = None
    minimum_days_to_close: int | None = Field(default=None, ge=0)
    maximum_days_to_close: int | None = Field(default=None, ge=0)
    routes: list[SubsidiaryRoute] = Field(default_factory=list)


class PrivateSignalRequest(_StrictModel):
    event: PipelineEvent
    rule: SignalRule


class RecipientDecision(_StrictModel):
    subsidiary_entity_id: str
    recipient_user_id: str
    disposition: Literal["candidate", "suppressed"]
    reason: str
    policy_id: str | None = None
    payload: dict | None = None


class PrivateSignalEvaluation(_StrictModel):
    tenant_id: str
    event_id: str
    status: str
    reason: str
    dispatch_status: Literal["not_implemented"] = "not_implemented"
    recipient_decisions: list[RecipientDecision] = Field(default_factory=list)


_SIGNAL_FIELDS = {
    "tender_ref",
    "project_name",
    "sender_entity_id",
    "stage",
    "material_categories",
    "existing_win_probability_percent",
    "expected_need_window",
}


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _suppressed(
    route: SubsidiaryRoute,
    recipient_user_id: str,
    reason: str,
) -> RecipientDecision:
    return RecipientDecision(
        subsidiary_entity_id=route.subsidiary_entity_id,
        recipient_user_id=recipient_user_id,
        disposition="suppressed",
        reason=reason,
    )


def evaluate_private_signal(
    request: PrivateSignalRequest,
    *,
    evaluated_at: datetime | None = None,
) -> PrivateSignalEvaluation:
    """Evaluate a source event and create only per-recipient, policy-scoped candidates."""
    now = evaluated_at or datetime.now(timezone.utc)
    event = request.event
    rule = request.rule

    def result(status: str, reason: str, decisions: list[RecipientDecision] | None = None) -> PrivateSignalEvaluation:
        return PrivateSignalEvaluation(
            tenant_id=event.tenant_id,
            event_id=event.event_id,
            status=status,
            reason=reason,
            recipient_decisions=decisions or [],
        )

    if not _is_aware(now) or not _is_aware(event.occurred_at):
        return result("suppressed", "timezone_required")
    if event.probability_updated_at is not None and not _is_aware(event.probability_updated_at):
        return result("suppressed", "probability_timezone_required")
    if not rule.enabled:
        return result("suppressed", "rule_disabled")
    if event.tenant_id != rule.tenant_id or event.sender_entity_id != rule.sender_entity_id:
        return result("suppressed", "rule_scope_mismatch")
    normalized_stage = event.stage.strip().casefold()
    normalized_prior_stage = (event.prior_stage or "").strip().casefold()
    trigger_stages = {stage.strip().casefold() for stage in rule.trigger_stages}
    if normalized_stage == normalized_prior_stage or normalized_stage not in trigger_stages:
        return result("not_triggered", "stage_transition_not_matched")

    event_age = now - event.occurred_at
    if event_age < timedelta(0):
        return result("suppressed", "event_timestamp_in_future")
    if event_age.total_seconds() > rule.max_event_age_seconds:
        return result("suppressed", "event_stale")

    if rule.min_win_probability_percent is not None:
        probability = event.existing_win_probability_percent
        probability_updated_at = event.probability_updated_at
        if probability is None or probability_updated_at is None:
            return result("not_triggered", "existing_probability_missing")
        probability_age = now - probability_updated_at
        if probability_age < timedelta(0):
            return result("suppressed", "probability_timestamp_in_future")
        if probability_age.total_seconds() > rule.max_probability_age_seconds:
            return result("not_triggered", "existing_probability_stale")
        if probability < rule.min_win_probability_percent:
            return result("not_triggered", "existing_probability_below_threshold")

    if rule.regions and (event.region is None or event.region.casefold() not in {item.casefold() for item in rule.regions}):
        return result("not_triggered", "region_not_matched")
    if rule.minimum_tender_value is not None:
        if rule.tender_currency and (event.currency or "").casefold() != rule.tender_currency.casefold():
            return result("not_triggered", "tender_currency_not_matched")
        if event.tender_value is None or event.tender_value < rule.minimum_tender_value:
            return result("not_triggered", "tender_value_below_minimum_or_missing")
    if rule.maximum_tender_value is not None:
        if rule.tender_currency and (event.currency or "").casefold() != rule.tender_currency.casefold():
            return result("not_triggered", "tender_currency_not_matched")
        if event.tender_value is None or event.tender_value > rule.maximum_tender_value:
            return result("not_triggered", "tender_value_above_maximum_or_missing")
    if rule.minimum_days_to_close is not None or rule.maximum_days_to_close is not None:
        if event.closing_at is None:
            return result("not_triggered", "closing_date_missing")
        days_to_close = (event.closing_at - now).total_seconds() / 86_400
        if days_to_close < 0:
            return result("not_triggered", "tender_already_closed")
        if rule.minimum_days_to_close is not None and days_to_close < rule.minimum_days_to_close:
            return result("not_triggered", "closing_date_too_soon")
        if rule.maximum_days_to_close is not None and days_to_close > rule.maximum_days_to_close:
            return result("not_triggered", "closing_date_too_far")

    event_categories = {
        category.strip().casefold(): category.strip()
        for category in event.material_categories
        if category.strip()
    }
    route_matches = [
        (
            route,
            sorted({
                event_categories[category.strip().casefold()]
                for category in route.material_categories
                if category.strip().casefold() in event_categories
            }),
        )
        for route in rule.routes
    ]
    route_matches = [(route, categories) for route, categories in route_matches if categories]
    if not route_matches:
        return result("no_route", "no_relevant_subsidiary")

    decisions: list[RecipientDecision] = []
    evaluated_recipients: set[str] = set()
    for route, matched_categories in route_matches:
        for recipient_user_id in route.recipient_user_ids:
            if recipient_user_id in evaluated_recipients:
                continue
            evaluated_recipients.add(recipient_user_id)

            available_payload = {
                "tender_ref": event.tender_ref,
                "project_name": event.project_name,
                "sender_entity_id": event.sender_entity_id,
                "stage": event.stage,
                "material_categories": matched_categories,
                "existing_win_probability_percent": event.existing_win_probability_percent,
                "expected_need_window": event.expected_need_window,
            }
            payload = {
                field: value
                for field, value in available_payload.items()
                if field in _SIGNAL_FIELDS and value is not None
            }
            decisions.append(
                RecipientDecision(
                    subsidiary_entity_id=route.subsidiary_entity_id,
                    recipient_user_id=recipient_user_id,
                    disposition="candidate",
                    reason="rule_matched",
                    payload=payload,
                )
            )

    if decisions:
        return result("candidate_ready", "rule_matched", decisions)
    return result("no_route", "no_recipients_selected")
