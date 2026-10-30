"""Operational tools used by the Sync Signals agent workflow."""
from __future__ import annotations

from typing import Any

from ingestion.connectors.base import ConnectorResult
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("agents.sync_pipeline_tools")


@traced_span("rpg_foresight.tool.load_existing_tender_revisions")
async def load_existing_tender_revisions() -> set[tuple[str, str]]:
    """Load stored event/revision keys so connector runs can avoid duplicates."""
    from sqlalchemy import select

    from db.base import AsyncSessionLocal
    from db.models import TenderEvent

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(TenderEvent.event_id, TenderEvent.source_revision)
        )
        revisions = {
            (event_id or "", source_revision or "")
            for event_id, source_revision in rows.all()
        }

    from opentelemetry import trace

    trace.get_current_span().set_attribute(
        "rpg_foresight.existing_revision_count",
        len(revisions),
    )
    return revisions


@traced_span("rpg_foresight.tool.run_enabled_connectors")
async def run_enabled_connectors(
    existing_revisions: set[tuple[str, str]],
) -> dict[str, ConnectorResult]:
    """Run each enabled connector and return its normalized, deduplicated batch."""
    from ingestion.connectors.registry import registry

    results = await registry.run_all(existing_revisions)
    from opentelemetry import trace

    span = trace.get_current_span()
    span.set_attribute("rpg_foresight.connector_count", len(results))
    span.set_attribute(
        "rpg_foresight.normalized_record_count",
        sum(len(result.records) for result in results.values()),
    )
    span.set_attribute(
        "rpg_foresight.connector_error_count",
        sum(len(result.errors) for result in results.values()),
    )
    return results


@traced_span("rpg_foresight.tool.persist_tender_events")
async def persist_tender_events(
    connector_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Persist connector batches and record the per-connector run outcomes."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from db.base import AsyncSessionLocal
    from db.models import ConnectorRun, TenderEvent, TenderOutcomeSnapshot
    from services.win_probability import apply_win_probability

    total_created = 0
    created_event_ids: list[str] = []
    errors: list[str] = []

    async with AsyncSessionLocal() as db:
        for connector_id, result in connector_results.items():
            records = result.get("records", [])
            connector_errors = result.get("errors", [])
            errors.extend(connector_errors)
            run = ConnectorRun(
                connector_id=connector_id,
                status="completed" if not connector_errors else "partial",
                records_fetched=len(records),
                records_normalized=len(records),
                records_created=0,
                errors=connector_errors,
            )
            db.add(run)
            await db.flush()

            for record in records:
                try:
                    is_demo = str(record.get("data_provenance", "")).startswith("Demo data:")
                    for snapshot in record.get("historical_outcomes", []):
                        outcome = str(snapshot.get("outcome", "")).strip().casefold()
                        if outcome not in {"won", "lost"}:
                            raise ValueError(
                                "Historical outcome snapshots must label each result as won or lost"
                            )
                        existing_snapshot = await db.execute(
                            select(TenderOutcomeSnapshot.id).where(
                                TenderOutcomeSnapshot.tenant_id == record.get("tenant_id", ""),
                                TenderOutcomeSnapshot.source_event_id
                                == snapshot["source_event_id"],
                                TenderOutcomeSnapshot.snapshot_key
                                == snapshot["snapshot_key"],
                            )
                        )
                        if existing_snapshot.scalar_one_or_none() is not None:
                            continue
                        observed_at = snapshot.get("observed_at")
                        if isinstance(observed_at, str):
                            observed_at = datetime.fromisoformat(
                                observed_at.replace("Z", "+00:00")
                            )
                        db.add(TenderOutcomeSnapshot(
                            tenant_id=record.get("tenant_id", ""),
                            source_event_id=snapshot["source_event_id"],
                            snapshot_key=snapshot["snapshot_key"],
                            stage=snapshot["stage"],
                            material_categories=snapshot.get("material_categories", []),
                            region=snapshot.get("region"),
                            tender_value=snapshot.get("tender_value"),
                            currency=snapshot.get("currency"),
                            outcome=outcome,
                            is_demo=is_demo,
                            observed_at=observed_at,
                            source_type=record.get("source_type", "crm"),
                        ))
                    await db.flush()

                    existing = await db.execute(
                        select(TenderEvent).where(
                            TenderEvent.event_id == record.get("event_id", ""),
                            TenderEvent.source_revision
                            == record.get("source_revision", ""),
                        )
                    )
                    if existing.first():
                        continue

                    occurred_at = record.get("occurred_at")
                    opening_at = record.get("opening_at")
                    closing_at = record.get("closing_at")
                    event = TenderEvent(
                        tenant_id=record.get("tenant_id", ""),
                        event_id=record.get("event_id", ""),
                        sender_entity_id=record.get("sender_entity_id", ""),
                        tender_ref=record.get("tender_ref", ""),
                        project_name=record.get("project_name", ""),
                        source_revision=record.get("source_revision", ""),
                        prior_stage=record.get("prior_stage"),
                        stage=record.get("stage", ""),
                        occurred_at=(
                            datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                            if occurred_at
                            else datetime.now(timezone.utc)
                        ),
                        material_categories=record.get("material_categories", []),
                        expected_need_window=record.get("expected_need_window"),
                        existing_win_probability_percent=None,
                        probability_updated_at=None,
                        source_type=record.get("source_type", "crm"),
                        data_provenance=record.get("data_provenance", ""),
                        ingested_at=datetime.now(timezone.utc),
                        material_requirements_raw=record.get(
                            "material_requirements_raw"
                        ),
                        tender_value=record.get("tender_value"),
                        currency=record.get("currency"),
                        opening_at=(
                            datetime.fromisoformat(opening_at.replace("Z", "+00:00"))
                            if opening_at
                            else None
                        ),
                        closing_at=(
                            datetime.fromisoformat(closing_at.replace("Z", "+00:00"))
                            if closing_at
                            else None
                        ),
                    )
                    db.add(event)
                    await db.flush()
                    total_created += 1
                    created_event_ids.append(event.event_id)
                    run.records_created += 1
                except Exception as exc:  # noqa: BLE001
                    log.exception(
                        "db_write_record_failed",
                        error=str(exc),
                    )
                    errors.append(f"write_error: {exc}")

            tenant_ids = {
                str(record.get("tenant_id", "")).strip()
                for record in records
                if str(record.get("tenant_id", "")).strip()
            }
            for tenant_id in tenant_ids:
                history_result = await db.execute(
                    select(TenderOutcomeSnapshot).where(
                        TenderOutcomeSnapshot.tenant_id == tenant_id
                    )
                )
                history = list(history_result.scalars().all())
                tender_result = await db.execute(
                    select(TenderEvent).where(TenderEvent.tenant_id == tenant_id)
                )
                for tender in tender_result.scalars().all():
                    apply_win_probability(tender, history)

        await db.commit()

    from opentelemetry import trace

    span = trace.get_current_span()
    span.set_attribute("rpg_foresight.records_created", total_created)
    span.set_attribute("rpg_foresight.record_error_count", len(errors))
    return {
        "total_created": total_created,
        "created_event_ids": created_event_ids,
        "errors": errors,
    }


@traced_span("rpg_foresight.tool.route_tender_signals")
async def route_tender_signals(event_ids: set[str]) -> dict[str, Any]:
    """Evaluate newly persisted events against routing rules and deliver alerts."""
    from opentelemetry import trace

    from db.base import AsyncSessionLocal
    from services.routing_service import run_routing_and_delivery

    async with AsyncSessionLocal() as db:
        summary = await run_routing_and_delivery(db, event_ids=event_ids)
    span = trace.get_current_span()
    for key in (
        "events_evaluated",
        "rules_applied",
        "decisions_created",
        "deliveries_created",
        "deliveries_sent",
        "deliveries_retried",
        "deliveries_failed",
    ):
        value = summary.get(key)
        if isinstance(value, (int, float, bool)):
            span.set_attribute(f"rpg_foresight.routing.{key}", value)
    span.set_attribute("rpg_foresight.routing.status", summary.get("status", "unknown"))
    return summary
