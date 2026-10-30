from __future__ import annotations

from agents.pursuit.state import PursuitState
from agents.pursuit.telemetry import record_agent_execution
from observability.tracing import traced_span


@traced_span("rpg_foresight.agent.pursuit_supervisor")
def pursuit_supervisor_agent(state: PursuitState) -> PursuitState:
    """Validate the live review input and initialize the specialist workflow."""
    tender = state.get("tender")
    if not isinstance(tender, dict) or not tender.get("event_id"):
        raise ValueError("Pursuit review requires a persisted tender record")

    document_count = len(state.get("uploaded_documents", []))
    state["workflow"] = [
        "qualification_agent",
        "document_agent",
        "risk_agent",
        "action_planner_agent",
    ]
    record_agent_execution(
        state,
        name="pursuit_supervisor",
        summary=f"Validated tender {tender.get('tender_id') or tender['event_id']} and started all four specialist reviews.",
        input_data={
            "event_id": tender["event_id"],
            "stage": tender.get("stage"),
            "document_count": document_count,
            "active_rule_count": len(state.get("active_rules", [])),
        },
        output_data={"workflow": state["workflow"]},
    )
    return state
