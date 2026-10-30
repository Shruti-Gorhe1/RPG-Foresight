from __future__ import annotations

from agents.pursuit.state import PursuitState
from agents.pursuit.telemetry import record_agent_execution, record_tool_execution
from agents.tools.pursuit_review_tools import review_tender_risks
from observability.tracing import traced_span


@traced_span("rpg_foresight.agent.risk")
async def risk_agent(state: PursuitState) -> PursuitState:
    tender = state["tender"]
    report = review_tender_risks(tender, state.get("document_analysis", {}))
    model_analysis = (
        f"Document checks flagged {len(report['risks'])} risk(s); "
        f"hard stop: {'yes' if report['hard_stop'] else 'no'}. "
        f"{report['limitations']}"
    )
    report["agent_analysis"] = model_analysis
    state["risk_review"] = report
    record_tool_execution(
        state,
        parent_agent="risk_agent",
        tool="review_tender_risks",
        summary=f"Assessed {len(report['risks'])} risk item(s); hard stop: {'yes' if report['hard_stop'] else 'no'}.",
    )
    record_agent_execution(
        state,
        name="risk_agent",
        summary=f"Flagged {len(report['risks'])} risk(s); human review is required. {model_analysis}",
        input_data={
            "event_id": tender["event_id"],
            "document_count": state.get("document_analysis", {}).get("documents_analyzed", 0),
        },
        output_data={
            "risk_count": len(report["risks"]),
            "hard_stop": report["hard_stop"],
            "analysis": model_analysis,
        },
    )
    return state
