"""Supervisor node — decides which specialist agent runs next.

The accelerator uses a supervisor-loop: every specialist node returns to the
supervisor, which picks the next node (or a terminal node) until the turn is
done. This baseline uses a simple rule; swap in an LLM router for real apps
(see ``get_system_prompt("supervisor")``).
"""
from __future__ import annotations

from agents.nodes.ingestion_supervisor import next_ingestion_agent
from agents.state import AgentState
from observability.tracing import traced_span

# Per-turn step budget — prevents infinite supervisor loops.
# The ingestion pipeline allows up to 10 steps per turn (doc Section 7).
_MAX_STEPS_PER_TURN = 12


@traced_span("rpg_foresight.agent.supervisor")
def supervisor_node(state: AgentState) -> AgentState:
    """Increment the turn budget and record intent. Real apps call the LLM here."""
    state["turn_count"] = state.get("turn_count", 0) + 1
    state.setdefault("current_step", "supervisor")

    # If an ingestion turn was requested, initialise its context once.
    collected = state.setdefault("collected", {})
    if state.get("start_ingestion") and "ingestion" not in collected:
        collected["ingestion"] = {
            "connectors_to_run": [],
            "results": {},
            "total_fetched": 0,
            "total_created": 0,
            "errors": [],
        }
        state.pop("start_ingestion", None)
    return state


def next_agent(state: AgentState) -> str:
    """Conditional-edge router. Returns the name of the next node."""
    # Escalation short-circuits everything.
    if state.get("human_review_reason"):
        return "human_review"

    # Stop after the step budget to hand control back to the user.
    if state.get("turn_count", 0) >= _MAX_STEPS_PER_TURN:
        return "respond_and_wait"

    collected = state.get("collected", {}) or {}
    ingestion = collected.get("ingestion")
    if isinstance(ingestion, dict):
        # An ingestion turn is in progress — hand off to the ingestion router.
        if ingestion.get("all_done"):
            return "respond_and_wait"
        return "ingestion_supervisor"

    # Run the tender operations agent once, then respond.
    if state.get("step_status") in ("completed", "failed"):
        return "respond_and_wait"

    if (
        isinstance(collected, dict)
        and "private_pipeline_signal" in collected
        and "private_pipeline_signal_result" not in collected
    ):
        return "private_pipeline_signal_agent"

    return "tender_operations_agent"
