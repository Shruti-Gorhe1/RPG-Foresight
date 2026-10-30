"""Ingestion supervisor node — decides which connectors to run.

Part of the agentic ingestion pipeline. This supervisor runs on a schedule
(or via API trigger) and orchestrates connector execution through the
specialist nodes below.
"""
from __future__ import annotations

from agents.state import AgentState
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("agents.ingestion_supervisor")


@traced_span("rpg_foresight.agent.ingestion_supervisor")
def ingestion_supervisor_node(state: AgentState) -> AgentState:
    """Decide which connectors to run and set up the ingestion turn."""
    collected = state.setdefault("collected", {})
    ingestion = collected.setdefault("ingestion", {
        "connectors_to_run": [],
        "results": {},
        "total_fetched": 0,
        "total_created": 0,
        "errors": [],
        "steps": 0,
    })
    if ingestion.get("all_done"):
        return state

    state["current_step"] = "ingestion_supervisor"
    state["step_status"] = "in_progress"

    ingestion["steps"] = ingestion.get("steps", 0) + 1

    log.info("ingestion_supervisor.started", turn=state.get("turn_count", 0) + 1, step=ingestion["steps"])
    return state


@traced_span("rpg_foresight.tool.select_ingestion_specialist")
def next_ingestion_agent(state: AgentState) -> str:
    """Conditional router for the ingestion subgraph."""
    collected = state.get("collected", {})
    ingestion = collected.get("ingestion", {}) if isinstance(collected, dict) else {}

    if state.get("step_status") == "failed":
        return "ingestion_error_handler"

    # Turn budget guard: max 10 steps per ingestion turn (doc Section 7).
    if ingestion.get("steps", 0) >= 10:
        return "respond_and_wait"

    if ingestion.get("all_done"):
        return "respond_and_wait"

    # Determine next step
    if not ingestion.get("connectors_identified"):
        return "identify_connectors"
    if ingestion.get("connectors_identified") and not ingestion.get("connectors_run"):
        return "run_connectors"
    if ingestion.get("connectors_run") and not ingestion.get("results_written"):
        return "write_results"
    if ingestion.get("results_written") and not ingestion.get("signals_routed"):
        return "route_signals"

    return "respond_and_wait"