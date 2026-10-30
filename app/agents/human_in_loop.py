"""Human-in-the-loop node — pauses the graph for manual review."""
from __future__ import annotations

from agents.state import AgentState
from observability.tracing import traced_span


@traced_span("rpg_foresight.agent.human_review")
def human_review_node(state: AgentState) -> AgentState:
    """Mark the session as escalated so it surfaces in the review queue."""
    state["current_step"] = "human_review"
    state["step_status"] = "escalated"
    reason = state.get("human_review_reason", "manual_review_requested")
    state.setdefault("messages", []).append(
        {
            "role": "assistant",
            "agent": "human_review",
            "content": (
                "This case has been routed to a specialist for review "
                f"(reason: {reason}). You'll be notified once a decision is made."
            ),
        }
    )
    return state
