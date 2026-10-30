"""Routing & notification delivery service.

Implements routing and notification delivery. After tender events are
ingested, the evaluator:

  1. Loads enabled routing rules (+ subsidiary routes) from trusted storage.
  2. For each event, checks trigger stages and the win-probability threshold.
  3. Finds subsidiary routes whose material categories match the event.
  4. Selects recipients configured on the rule and present in the tenant's
     address book.
  5. Creates RecipientDecision rows (candidate / suppressed).
  6. For candidates, delivers via the notification adapter and records
     NotificationDelivery (sent / failed / suppressed).
  7. Writes audit_events.

Only the notification adapter performs the actual channel send; everything
else is deterministic and persisted to the database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    AuditEvent,
    DeliveryAttempt,
    NotificationDelivery,
    RecipientAddress,
    RecipientDecision,
    RoutingRule,
    TenderEvent,
)
from services.notification import get_adapter
import services.email_adapter  # noqa: F401  (registers the "email" adapter)
import services.teams_adapter  # noqa: F401  (auto-registers the "teams" adapter)
from services.private_pipeline_signals import (
    PipelineEvent,
    PrivateSignalRequest,
    SignalRule,
    PrivateSignalEvaluation,
    SubsidiaryRoute,
    evaluate_private_signal,
)
from shared.logger import get_logger
from observability.tracing import traced_span

log = get_logger("services.routing")

def _utc(value: datetime | None) -> datetime | None:
    """Normalise a (possibly naive) stored timestamp to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _audit(
    db: AsyncSession,
    tenant_id: str,
    action: str,
    object_type: str | None,
    object_id: str | None,
    result: str,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    actor: str = "routing-service",
    trace_id: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            trace_id=trace_id,
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details or {},
            result=result,
            reason=reason,
        )
    )


@traced_span("rpg_foresight.tool.deliver_notification")
async def _deliver(
    db: AsyncSession,
    event: TenderEvent,
    decision: Any,
    channel: str,
    existing_delivery: NotificationDelivery | None = None,
) -> bool:
    """Deliver one candidate decision through the notification adapter."""
    message_id: str | None = None
    error_message: str | None = None
    adapter = get_adapter(channel)
    if adapter is None:
        status = "failed"
        error_message = f"No notification adapter is registered for channel '{channel}'"
    else:
        try:
            result = await adapter.send(
                decision.recipient_user_id,
                decision.payload or {},
            )
            status = result.status
            message_id = result.message_id
            error_message = result.error
        except Exception as exc:  # noqa: BLE001
            log.exception("notification_send_failed", recipient=decision.recipient_user_id, error=str(exc))
            status = "failed"
            error_message = str(exc)

    if existing_delivery is None:
        delivery = NotificationDelivery(
                event_id=event.event_id,
                recipient_user_id=decision.recipient_user_id,
                channel=channel,
                status=status,
                message_id=message_id,
                payload=decision.payload or {},
                sent_at=datetime.now(timezone.utc) if status == "sent" else None,
                error_message=error_message,
                retry_count=0,
            )
        db.add(delivery)
        await db.flush()
    else:
        delivery = existing_delivery
        existing_delivery.status = status
        existing_delivery.message_id = message_id
        existing_delivery.payload = decision.payload or {}
        existing_delivery.sent_at = datetime.now(timezone.utc) if status == "sent" else None
        existing_delivery.error_message = error_message
        existing_delivery.retry_count += 1
    db.add(
        DeliveryAttempt(
            delivery_id=delivery.id,
            status=status,
            message_id=message_id,
            error_message=error_message,
        )
    )
    _audit(
        db,
        event.tenant_id,
        "delivery",
        "notification_delivery",
        decision.recipient_user_id,
        status,
        reason=None if status == "sent" else error_message,
        details={"event_id": event.event_id, "channel": channel},
    )
    return status == "sent"


@traced_span("rpg_foresight.tool.evaluate_routing_rule")
def _evaluate_event_for_rule(
    event: TenderEvent,
    rule: RoutingRule,
    recipient_emails: list[str],
) -> PrivateSignalEvaluation:
    """Evaluate one event against one rule and its scoped recipients."""
    from opentelemetry import trace

    route_list = []
    selected_emails = set(recipient_emails)
    for subsidiary_route in rule.routes or []:
        if not selected_emails:
            continue
        route_recipients = sorted(selected_emails)
        if route_recipients:
            route_list.append(
                SubsidiaryRoute(
                    subsidiary_entity_id=subsidiary_route.subsidiary_entity_id,
                    recipient_user_ids=route_recipients,
                    material_categories=list(subsidiary_route.material_categories or []),
                )
            )

    request = PrivateSignalRequest(
        event=PipelineEvent(
            tenant_id=event.tenant_id,
            event_id=event.event_id,
            sender_entity_id=event.sender_entity_id,
            tender_ref=event.tender_ref,
            project_name=event.project_name,
            source_revision=event.source_revision,
            prior_stage=event.prior_stage,
            stage=event.stage,
            occurred_at=_utc(event.occurred_at),
            material_categories=list(event.material_categories or []),
            expected_need_window=event.expected_need_window,
            existing_win_probability_percent=event.existing_win_probability_percent,
            probability_updated_at=_utc(event.probability_updated_at),
            region=event.region,
            tender_value=event.tender_value,
            currency=event.currency,
            closing_at=_utc(event.closing_at),
        ),
        rule=SignalRule(
            enabled=rule.enabled,
            tenant_id=rule.tenant_id,
            sender_entity_id=event.sender_entity_id,
            trigger_stages=list(rule.trigger_stages or []),
            min_win_probability_percent=rule.min_win_probability_percent,
            purpose=rule.purpose,
            channel=rule.channel,
            max_event_age_seconds=rule.max_event_age_seconds,
            max_probability_age_seconds=rule.max_probability_age_seconds,
            regions=list(rule.regions or []),
            tender_currency=rule.tender_currency,
            minimum_tender_value=rule.minimum_tender_value,
            maximum_tender_value=rule.maximum_tender_value,
            minimum_days_to_close=rule.minimum_days_to_close,
            maximum_days_to_close=rule.maximum_days_to_close,
            routes=route_list,
        ),
    )
    evaluation = evaluate_private_signal(request)
    span = trace.get_current_span()
    span.set_attribute("rpg_foresight.rule.id", rule.rule_id)
    span.set_attribute("rpg_foresight.rule.name", rule.name)
    span.set_attribute("rpg_foresight.rule.evaluation_status", evaluation.status)
    span.set_attribute("rpg_foresight.rule.evaluation_reason", evaluation.reason)
    span.set_attribute(
        "rpg_foresight.rule.recipient_decisions",
        len(evaluation.recipient_decisions),
    )
    span.set_attribute(
        "rpg_foresight.rule.candidates",
        sum(item.disposition == "candidate" for item in evaluation.recipient_decisions),
    )
    span.set_attribute(
        "rpg_foresight.rule.suppressed",
        sum(item.disposition == "suppressed" for item in evaluation.recipient_decisions),
    )
    return evaluation


@traced_span("rpg_foresight.tool.match_routing_rules")
def _matching_rules_for_event(
    event: TenderEvent,
    rules: list[RoutingRule],
) -> list[RoutingRule]:
    """Select enabled rules belonging to the tender's tenant."""
    from opentelemetry import trace

    matching_rules = [rule for rule in rules if rule.tenant_id == event.tenant_id]
    span = trace.get_current_span()
    span.set_attribute("rpg_foresight.rules.available", len(rules))
    span.set_attribute("rpg_foresight.rules.matched", len(matching_rules))
    span.set_attribute("rpg_foresight.rules.match", bool(matching_rules))
    return matching_rules


def _latest_tender_events_statement(tenant_id: str | None = None):
    latest_revision = (
        select(
            TenderEvent.id.label("event_row_id"),
            func.row_number()
            .over(
                partition_by=(TenderEvent.tenant_id, TenderEvent.event_id),
                order_by=(TenderEvent.ingested_at.desc(), TenderEvent.id.desc()),
            )
            .label("revision_rank"),
        )
    )
    if tenant_id is not None:
        latest_revision = latest_revision.where(TenderEvent.tenant_id == tenant_id)
    ranked_events = latest_revision.subquery()
    statement = (
        select(TenderEvent)
        .join(ranked_events, TenderEvent.id == ranked_events.c.event_row_id)
        .where(ranked_events.c.revision_rank == 1)
        .order_by(TenderEvent.ingested_at.desc(), TenderEvent.id.desc())
    )
    return statement


@traced_span("rpg_foresight.routing.run")
async def run_routing_and_delivery(
    db: AsyncSession,
    event_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Evaluate stored tender events and route only unsent or retryable deliveries."""
    rules_result = await db.execute(
        select(RoutingRule)
        .options(selectinload(RoutingRule.routes))
        .where(RoutingRule.enabled == True)  # noqa: E712
    )
    rules = rules_result.scalars().all()

    if not rules:
        log.info("routing_skipped_no_rules")
        _audit(db, "system", "routing", "routing_rules", None, "skipped", reason="no_routing_rules")
        await db.commit()
        return {
            "status": "skipped",
            "reason": "no_routing_rules",
            "events_evaluated": 0,
            "decisions_created": 0,
            "deliveries_created": 0,
        }

    events_statement = _latest_tender_events_statement()
    if event_ids is not None:
        events_statement = events_statement.where(TenderEvent.event_id.in_(event_ids))
    events_result = await db.execute(events_statement)
    events = events_result.scalars().all()
    recipients_result = await db.execute(select(RecipientAddress))
    recipients_by_tenant: dict[str, set[str]] = {}
    for recipient in recipients_result.scalars().all():
        recipients_by_tenant.setdefault(recipient.tenant_id, set()).add(recipient.email)

    decisions_result = await db.execute(select(RecipientDecision))
    decisions_by_event: dict[str, list[RecipientDecision]] = {}
    for decision in decisions_result.scalars().all():
        decisions_by_event.setdefault(decision.event_id, []).append(decision)

    deliveries_result = await db.execute(
        select(NotificationDelivery).order_by(NotificationDelivery.id.desc())
    )
    deliveries_by_key: dict[tuple[str, str, str], NotificationDelivery] = {}
    for delivery in deliveries_result.scalars().all():
        deliveries_by_key.setdefault(
            (delivery.event_id, delivery.recipient_user_id, delivery.channel),
            delivery,
        )

    decisions_created = 0
    deliveries_created = 0
    deliveries_sent = 0
    deliveries_retried = 0
    deliveries_failed = 0

    for event in events:
        matching_rules = _matching_rules_for_event(event, rules)
        if not matching_rules:
            _audit(db, event.tenant_id, "routing", "tender_event", event.event_id, "suppressed", reason="no_matching_rule")
            continue

        evaluated_recipients: set[tuple[str, str]] = set()
        known_decisions = {
            (
                item.subsidiary_entity_id,
                item.recipient_user_id,
                item.disposition,
                item.reason,
                item.policy_id,
            )
            for item in decisions_by_event.get(event.event_id, [])
        }
        for rule in matching_rules:
            saved_addresses = recipients_by_tenant.get(event.tenant_id, set())
            rule_emails = list(rule.selected_recipient_emails or [])
            if not rule_emails and rule.selected_recipient_email:
                rule_emails = [rule.selected_recipient_email]
            evaluation = _evaluate_event_for_rule(
                event,
                rule,
                [email for email in rule_emails if email in saved_addresses],
            )

            for decision in evaluation.recipient_decisions:
                candidate_key = (decision.recipient_user_id, rule.channel)
                if decision.disposition == "candidate" and candidate_key in evaluated_recipients:
                    continue
                if decision.disposition == "candidate":
                    evaluated_recipients.add(candidate_key)

                decision_key = (
                    decision.subsidiary_entity_id,
                    decision.recipient_user_id,
                    decision.disposition,
                    decision.reason,
                    decision.policy_id,
                )
                if decision_key not in known_decisions:
                    db.add(
                        RecipientDecision(
                            event_id=event.event_id,
                            tenant_id=event.tenant_id,
                            subsidiary_entity_id=decision.subsidiary_entity_id,
                            recipient_user_id=decision.recipient_user_id,
                            disposition=decision.disposition,
                            reason=decision.reason,
                            policy_id=decision.policy_id,
                            payload=decision.payload or {},
                        )
                    )
                    known_decisions.add(decision_key)
                    decisions_created += 1

                if decision.disposition == "candidate":
                    delivery_key = (event.event_id, decision.recipient_user_id, rule.channel)
                    existing_delivery = deliveries_by_key.get(delivery_key)
                    if existing_delivery and existing_delivery.status in {"sent", "delivered"}:
                        continue
                    was_retry = existing_delivery is not None
                    delivered = await _deliver(
                        db,
                        event,
                        decision,
                        rule.channel,
                        existing_delivery=existing_delivery,
                    )
                    if was_retry:
                        deliveries_retried += 1
                    else:
                        deliveries_created += 1
                    if delivered:
                        deliveries_sent += 1
                    else:
                        deliveries_failed += 1

            _audit(
                db,
                event.tenant_id,
                "routing",
                "tender_event",
                event.event_id,
                evaluation.status,
                reason=evaluation.reason,
                details={
                    "rule_id": rule.rule_id,
                    "decisions": len(evaluation.recipient_decisions),
                },
            )

    await db.commit()

    summary = {
        "status": "completed",
        "events_evaluated": len(events),
        "rules_applied": len(rules),
        "decisions_created": decisions_created,
        "deliveries_created": deliveries_created,
        "deliveries_sent": deliveries_sent,
        "deliveries_retried": deliveries_retried,
        "deliveries_failed": deliveries_failed,
    }
    log.info("routing_and_delivery.completed", **summary)
    return summary
