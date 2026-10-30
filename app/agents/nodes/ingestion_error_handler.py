"""Ingestion error handler node."""
from __future__ import annotations

from agents.state import AgentState
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("agents.ingestion_error_handler")


@traced_span("rpg_foresight.agent.ingestion_error_handler")
def ingestion_error_handler_node(state: AgentState) -> AgentState:
    """Handle ingestion errors gracefully — record and continue."""
    collected = state.setdefault("collected", {})
    ingestion = collected.setdefault("ingestion", {})

    errors = ingestion.get("errors", [])
    log.warning("ingestion_error_handler", errors=errors)

    state["step_status"] = "failed" if errors else "completed"
    ingestion["all_done"] = True
    return state