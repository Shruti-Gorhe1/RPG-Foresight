"""Routing specialist for newly persisted tender events."""
from __future__ import annotations

from agents.state import AgentState
from agents.tools.sync_pipeline_tools import route_tender_signals
from observability.tracing import traced_span


@traced_span("rpg_foresight.agent.route_signals")
async def route_signals_agent_node(state: AgentState) -> AgentState:
    """Evaluate new tender events against routing rules and dispatch matches."""
    ingestion = state.setdefault("collected", {}).setdefault("ingestion", {})
    event_ids = set(ingestion.get("created_event_ids", []))
    routing = await route_tender_signals(event_ids)

    ingestion["routing"] = routing
    ingestion["signals_routed"] = True
    ingestion["all_done"] = True
    state["current_step"] = "route_signals"

    if routing.get("status") not in {"completed", "skipped"}:
        state["step_status"] = "failed"
    else:
        state["step_status"] = "completed"
    return state
