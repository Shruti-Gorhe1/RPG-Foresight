from __future__ import annotations

from agents.pursuit.state import PursuitState
from agents.pursuit.telemetry import record_agent_execution, record_tool_execution
from agents.tools.pursuit_review_tools import match_tender_to_rules
from observability.tracing import traced_span


_CLOSED_STAGES = {"closed", "cancelled", "lost", "no bid", "no-bid", "awarded"}


@traced_span("rpg_foresight.agent.qualification")
async def qualification_agent(state: PursuitState) -> PursuitState:
    tender = state["tender"]
    rules = state.get("active_rules", [])
    probability = tender.get("existing_win_probability_percent")
    rule_result = match_tender_to_rules(tender, rules)
    active_rule_matches = rule_result["matching_rule_ids"]

    missing_fields = [
        field
        for field in ("stage", "material_categories", "region", "tender_value", "closing_at")
        if not tender.get(field)
    ]
    score = 0
    if probability is not None:
        score += 30 if probability >= 70 else 20 if probability >= 50 else 8
    if active_rule_matches:
        score += 30
    elif rules:
        score += 5
    if tender.get("material_categories"):
        score += 15
    if tender.get("region"):
        score += 10
    if tender.get("tender_value") is not None:
        score += 10
    if tender.get("closing_at"):
        score += 5

    findings = []
    if active_rule_matches:
        findings.append(f"Matches active routing rule(s): {', '.join(active_rule_matches)}.")
    elif rules:
        findings.append("Does not match the current active routing rule criteria.")
    else:
        findings.append("No enabled routing rules are configured for this tenant.")
    if probability is None:
        findings.append("No win-probability estimate is available.")
    else:
        findings.append(f"Calculated win-probability estimate is {probability:g}%.")
    if missing_fields:
        findings.append(f"Missing tender information: {', '.join(missing_fields)}.")

    fit_score = min(score, 100)
    stage_closed = str(tender.get("stage") or "").strip().casefold() in _CLOSED_STAGES
    record_tool_execution(
        state,
        parent_agent="qualification_agent",
        tool="match_tender_to_rules",
        summary=f"Checked {rule_result['rules_checked']} active rule(s); {len(active_rule_matches)} matched.",
    )
    model_analysis = (
        f"Calculated fit score {fit_score}/100 from tender metadata and "
        f"{rule_result['rules_checked']} active rule(s); "
        f"{len(active_rule_matches)} rule(s) matched."
    )
    if missing_fields:
        model_analysis += f" Missing fields: {', '.join(missing_fields)}."
    state["qualification"] = {
        "agent": "qualification_agent",
        "fit_score": fit_score,
        "active_rule_matches": active_rule_matches,
        "stage_is_closed": stage_closed,
        "missing_fields": missing_fields,
        "findings": findings,
        "agent_analysis": model_analysis,
        "method": "Deterministic scoring from current tenant rules and recorded tender metadata.",
    }
    record_agent_execution(
        state,
        name="qualification_agent",
        summary=f"Fit score {fit_score}/100; {len(active_rule_matches)} rule match(es). {model_analysis}",
        input_data={
            "event_id": tender["event_id"],
            "rule_count": rule_result["rules_checked"],
            "missing_fields": missing_fields,
        },
        output_data={
            "fit_score": fit_score,
            "active_rule_matches": active_rule_matches,
            "analysis": model_analysis,
        },
    )
    return state
