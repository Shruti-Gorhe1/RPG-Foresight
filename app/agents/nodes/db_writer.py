"""DB writer node — persists normalized tender events to the database."""
from __future__ import annotations

from agents.state import AgentState
from agents.tools.sync_pipeline_tools import persist_tender_events
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("agents.db_writer")


@traced_span("rpg_foresight.agent.db_writer")
async def db_writer_node(state: AgentState) -> AgentState:
    """Write normalized connector results to the tender_events table."""
    collected = state.setdefault("collected", {})
    ingestion = collected.setdefault("ingestion", {})

    connector_results = ingestion.get("connector_results", {})
    result = await persist_tender_events(connector_results)

    ingestion["results_written"] = True
    ingestion["total_created"] = result["total_created"]
    ingestion["created_event_ids"] = result["created_event_ids"]
    ingestion["errors"] = [*ingestion.get("errors", []), *result["errors"]]
    state["step_status"] = "completed"

    log.info(
        "db_writer.completed",
        total_created=result["total_created"],
        errors=len(result["errors"]),
    )
    return state