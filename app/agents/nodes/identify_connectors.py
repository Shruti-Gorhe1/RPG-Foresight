"""Identify connectors node — discovers enabled connectors and existing event IDs."""
from __future__ import annotations

from agents.state import AgentState
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("agents.identify_connectors")


@traced_span("rpg_foresight.agent.identify_connectors")
async def identify_connectors_node(state: AgentState) -> AgentState:
    """Fetch existing event IDs from DB and identify connectors to run."""
    from ingestion.connectors.registry import registry
    from agents.tools.sync_pipeline_tools import load_existing_tender_revisions

    collected = state.setdefault("collected", {})
    ingestion = collected.setdefault("ingestion", {})

    try:
        existing_ids = await load_existing_tender_revisions()
    except Exception as exc:  # noqa: BLE001
        log.exception("db_query_existing_ids_failed", error=str(exc))
        ingestion["db_error"] = str(exc)
        ingestion["errors"] = [*ingestion.get("errors", []), f"db_error: {exc}"]
        state["step_status"] = "failed"
        return state

    ingestion["existing_event_ids"] = existing_ids
    ingestion["connectors_identified"] = True

    enabled_connectors = registry.enabled()
    ingestion["connector_count"] = len(enabled_connectors)
    ingestion["connector_ids"] = [c.connector_id for c in enabled_connectors]

    log.info(
        "identify_connectors.completed",
        existing_events=len(existing_ids),
        enabled_connectors=len(enabled_connectors),
    )

    state["step_status"] = "completed"
    return state