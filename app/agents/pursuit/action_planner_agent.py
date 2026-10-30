from __future__ import annotations

from typing import Any

from agents.pursuit.state import PursuitState
from agents.pursuit.telemetry import record_agent_execution, record_tool_execution
from agents.tools.pursuit_review_tools import prepare_pursuit_action_plan
from observability.tracing import traced_span


def _validated_action_plan(
    result: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    allowed_evidence_ids: set[str],
) -> tuple[str, str, list[dict[str, Any]]]:
    analysis = result.get("analysis")
    rationale = result.get("rationale")
    raw_steps = result.get("next_steps")
    if (
        not isinstance(analysis, str) or not analysis.strip()
        or not isinstance(rationale, str) or not rationale.strip()
        or not isinstance(raw_steps, list)
        or len(raw_steps) > 8
    ):
        raise RuntimeError("Configured model returned an invalid action plan")

    next_steps = []
    for step in raw_steps:
        if not isinstance(step, dict):
            raise RuntimeError("Configured model returned an invalid next step")
        task = step.get("task")
        evidence_ids = step.get("evidence_ids")
        description = step.get("description")
        if (
            not isinstance(task, str) or not task.strip() or len(task) > 240
            or (
                description is not None
                and (
                    not isinstance(description, str)
                    or not description.strip()
                    or len(description) > 1200
                )
            )
            or not isinstance(evidence_ids, list)
            or not evidence_ids
            or not all(
                isinstance(item, str)
                and item in evidence
                and item in allowed_evidence_ids
                for item in evidence_ids
            )
        ):
            raise RuntimeError("Configured model returned an unsupported next step")
        next_steps.append({
            "task": task.strip(),
            "description": (description or (
                "The excerpt does not specify the complete procedure. Check the cited "
                "section in the full tender and verify any referenced forms, submission "
                "method, and deadline before proceeding."
            )).strip(),
            "evidence_ids": evidence_ids,
            "references": [
                {
                    "document": evidence[evidence_id]["document"],
                    "location": evidence[evidence_id]["location"],
                }
                for evidence_id in evidence_ids
            ],
        })
    return analysis.strip(), rationale.strip(), next_steps


@traced_span("rpg_foresight.agent.action_planner")
async def action_planner_agent(state: PursuitState) -> PursuitState:
    tender = state["tender"]
    plan = prepare_pursuit_action_plan(
        tender,
        state["qualification"],
        state["risk_review"],
        state["document_analysis"],
    )
    evidence = state["document_analysis"].get("evidence_items", {})
    guidelines = state["document_analysis"].get("processing_guidelines", [])
    actionable_requirements = [
        {
            "category": item["category"],
            "summary": item["summary"],
            "evidence_ids": item["evidence_ids"],
        }
        for item in guidelines
    ]
    allowed_evidence_ids = {
        evidence_id
        for item in actionable_requirements
        for evidence_id in item["evidence_ids"]
    }
    document_analysis = state["document_analysis"]
    risk_review = state["risk_review"]
    if risk_review["hard_stop"]:
        rationale = "A hard-stop risk was identified in the tender document."
    elif any(item["level"] in {"high", "critical"} for item in risk_review["risks"]):
        rationale = "High or critical tender risks require human review."
    elif state["qualification"]["missing_fields"]:
        rationale = "Tender metadata is incomplete and requires human review."
    else:
        rationale = (
            f"Qualification fit is {state['qualification']['fit_score']}/100; "
            "human approval is required before any bid decision."
        )
    structured = {
        "analysis": document_analysis.get("agent_analysis", ""),
        "rationale": rationale,
        "next_steps": document_analysis.get("suggested_actions", []),
    }
    model_analysis, rationale, next_steps = _validated_action_plan(
        structured,
        evidence,
        allowed_evidence_ids,
    )
    if allowed_evidence_ids and not next_steps:
        raise RuntimeError("Configured model omitted actions for the tender guidelines")
    cited_evidence_ids = {
        evidence_id
        for step in next_steps
        for evidence_id in step["evidence_ids"]
    }
    if allowed_evidence_ids - cited_evidence_ids:
        raise RuntimeError("Configured model omitted one or more tender guideline actions")
    plan["rationale"] = rationale
    plan["next_steps"] = next_steps
    plan["agent_analysis"] = model_analysis
    state["action_plan"] = plan
    state["recommendation"] = plan["recommendation"]
    record_tool_execution(
        state,
        parent_agent="action_planner_agent",
        tool="prepare_pursuit_action_plan",
        summary=f"Prepared {plan['recommendation']} recommendation and validated {len(plan['next_steps'])} document-grounded action(s).",
    )
    record_agent_execution(
        state,
        name="action_planner_agent",
        summary=f"Prepared a provisional {plan['recommendation'].replace('_', ' ')} recommendation and {len(plan['next_steps'])} next steps. {model_analysis}",
        input_data={
            "event_id": tender["event_id"],
            "recommendation": plan["recommendation"],
            "step_count": len(plan["next_steps"]),
        },
        output_data={
            "recommendation": plan["recommendation"],
            "next_steps": plan["next_steps"],
            "analysis": model_analysis,
        },
    )
    return state
