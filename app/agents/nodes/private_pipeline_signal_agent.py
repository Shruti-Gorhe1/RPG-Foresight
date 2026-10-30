"""Deterministic specialist for evaluating authorized pipeline signal candidates."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import ValidationError

from agents.state import AgentState
from observability.tracing import traced_span
from services.private_pipeline_signals import PrivateSignalRequest, evaluate_private_signal
from shared.logger import get_logger

log = get_logger("agents.private_pipeline_signal")


@traced_span("rpg_foresight.agent.private_pipeline_signal")
def private_pipeline_signal_agent_node(state: AgentState) -> AgentState:
    """Evaluate a prepared event; this node never connects to a CRM or dispatches alerts."""
    collected = state.setdefault("collected", {})
    source = collected.get("private_pipeline_signal")
    if not isinstance(source, dict):
        state["step_status"] = "failed"
        collected["private_pipeline_signal_result"] = {
            "status": "failed",
            "reason": "private_pipeline_signal_input_missing",
            "dispatch_status": "not_implemented",
        }
        return state

    try:
        if hasattr(PrivateSignalRequest, "model_validate"):
            request = PrivateSignalRequest.model_validate(source)
        else:
            # Pydantic 1 compatibility for the template's unpinned dependency.
            request = PrivateSignalRequest.parse_obj(source)
    except ValidationError:
        collected["private_pipeline_signal_result"] = {
            "status": "failed",
            "reason": "private_pipeline_signal_input_invalid",
            "dispatch_status": "not_implemented",
        }
        state["current_step"] = "private_pipeline_signal_agent"
        state["step_status"] = "failed"
        state.setdefault("messages", []).append(
            {
                "role": "assistant",
                "agent": "private_pipeline_signal_agent",
                "content": "The pipeline event or routing policy was invalid; no alert was prepared or sent.",
            }
        )
        return state

    evaluation = evaluate_private_signal(request, evaluated_at=request.event.occurred_at + __import__('datetime').timedelta(minutes=1))
    collected["private_pipeline_signal_result"] = (
        evaluation.model_dump() if hasattr(evaluation, "model_dump") else evaluation.dict()
    )
    state["current_step"] = "private_pipeline_signal_agent"
    state["step_status"] = "completed"
    state.setdefault("messages", []).append(
        {
            "role": "assistant",
            "agent": "private_pipeline_signal_agent",
            "content": (
                f"Signal evaluation: {evaluation.status} ({evaluation.reason}); "
                f"{sum(d.disposition == 'candidate' for d in evaluation.recipient_decisions)} "
                "recipient candidate(s) prepared. No notification was sent."
            ),
        }
    )
    log.info(
        "private_pipeline_signal.evaluated",
        status=evaluation.status,
        candidate_count=sum(d.disposition == "candidate" for d in evaluation.recipient_decisions),
    )
    return state
