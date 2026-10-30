"""Deterministic review tools called by the pursuit specialist agents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from observability.tracing import traced_span


def _set_tool_metrics(**attributes: int | str | bool) -> None:
    from opentelemetry import trace

    span = trace.get_current_span()
    for key, value in attributes.items():
        span.set_attribute(f"rpg_foresight.{key}", value)


@traced_span("rpg_foresight.tool.match_tender_to_rules")
def match_tender_to_rules(
    tender: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare tender metadata against each enabled routing rule."""
    materials = {str(item).strip().casefold() for item in tender.get("material_categories", [])}
    stage = str(tender.get("stage") or "").strip().casefold()
    probability = tender.get("existing_win_probability_percent")
    region = str(tender.get("region") or "").strip().casefold()
    matches: list[str] = []

    for rule in rules:
        stages = {str(value).strip().casefold() for value in rule.get("trigger_stages", [])}
        route_materials = {
            str(material).strip().casefold()
            for route in rule.get("routes", [])
            for material in route.get("material_categories", [])
        }
        regions = {str(value).strip().casefold() for value in rule.get("regions", [])}
        if stage not in stages:
            continue
        if route_materials and not materials.intersection(route_materials):
            continue
        if regions and region not in regions:
            continue
        threshold = rule.get("min_win_probability_percent")
        if threshold is not None and (probability is None or probability < threshold):
            continue
        minimum = rule.get("minimum_tender_value")
        if minimum is not None and (
            tender.get("tender_value") is None or tender["tender_value"] < minimum
        ):
            continue
        maximum = rule.get("maximum_tender_value")
        if maximum is not None and (
            tender.get("tender_value") is None or tender["tender_value"] > maximum
        ):
            continue
        if rule.get("tender_currency") and str(tender.get("currency") or "").casefold() != str(
            rule["tender_currency"]
        ).casefold():
            continue
        matches.append(str(rule["rule_id"]))

    _set_tool_metrics(
        rules_checked=len(rules),
        matching_rule_count=len(matches),
    )
    return {"matching_rule_ids": matches, "rules_checked": len(rules)}


@traced_span("rpg_foresight.tool.review_tender_risks")
def review_tender_risks(
    tender: dict[str, Any],
    analysis: dict[str, Any],
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Assess deadline and cited document risks using explicit rule checks."""
    now = evaluated_at or datetime.now(timezone.utc)
    risks: list[dict[str, Any]] = []
    closing_at = tender.get("closing_at")
    parsed_close: datetime | None = None

    if closing_at:
        try:
            parsed_close = datetime.fromisoformat(str(closing_at).replace("Z", "+00:00"))
            parsed_close = (
                parsed_close.replace(tzinfo=timezone.utc)
                if parsed_close.tzinfo is None
                else parsed_close.astimezone(timezone.utc)
            )
        except ValueError:
            risks.append({
                "level": "medium",
                "risk": "Closing date could not be interpreted; verify it manually.",
            })
    else:
        risks.append({
            "level": "medium",
            "risk": "No closing date is recorded; deadline risk cannot be assessed.",
        })

    if parsed_close is not None:
        days_left = (parsed_close - now).total_seconds() / 86_400
        if days_left < 0:
            risks.append({"level": "critical", "risk": "Recorded tender closing date has passed."})
        elif days_left <= 7:
            risks.append({
                "level": "high",
                "risk": f"Tender closes in {max(0, int(days_left))} day(s); confirm submission readiness immediately.",
            })
    if tender.get("existing_win_probability_percent") is None:
        risks.append({
            "level": "medium",
            "risk": "Win probability is missing; confidence in prioritization is limited.",
        })
    if not analysis.get("documents_analyzed"):
        risks.append({
            "level": "medium",
            "risk": "No tender documents were analyzed; eligibility and compliance remain unverified.",
        })

    def add_document_risk(
        level: str,
        message: str,
        evidence: dict[str, Any],
    ) -> None:
        reference = {
            "document": evidence["document"],
            "location": evidence["location"],
            "excerpt": evidence["excerpt"],
        }
        existing_risk = next(
            (
                item for item in risks
                if item["level"] == level and item["risk"] == message
            ),
            None,
        )
        if existing_risk is None:
            risks.append({
                "level": level,
                "risk": message,
                "references": [reference],
            })
            return
        references = existing_risk["references"]
        if reference not in references:
            references.append(reference)

    disqualifier_evidence = analysis.get("explicit_disqualifier_evidence", [])
    for evidence in disqualifier_evidence:
        add_document_risk(
            "critical",
            "Possible exclusion or disqualification clause needs human legal review.",
            evidence,
        )

    exclusion_keys = {
        (
            item.get("document"),
            item.get("location"),
            item.get("excerpt", "").casefold(),
        )
        for item in disqualifier_evidence
    }
    for evidence in analysis.get("findings", {}).get("commercial_risks", []):
        key = (
            evidence.get("document"),
            evidence.get("location"),
            evidence.get("excerpt", "").casefold(),
        )
        if key in exclusion_keys:
            continue
        add_document_risk(
            "medium",
            "Commercial clauses require review for delivery, liability, or payment impact.",
            evidence,
        )

    hard_stop = (
        parsed_close is not None and parsed_close < now
    ) or bool(disqualifier_evidence)
    _set_tool_metrics(
        risk_count=len(risks),
        hard_stop=hard_stop,
    )
    return {
        "risks": risks,
        "hard_stop": hard_stop,
        "limitations": "Text and date heuristics only; not a legal, financial, or bid eligibility opinion.",
    }


@traced_span("rpg_foresight.tool.prepare_pursuit_action_plan")
def prepare_pursuit_action_plan(
    tender: dict[str, Any],
    qualification: dict[str, Any],
    risk_review: dict[str, Any],
    document_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Calculate the provisional recommendation; the action agent writes next steps."""
    high_risks = [
        item for item in risk_review["risks"]
        if item["level"] in {"high", "critical"}
    ]
    score = qualification["fit_score"]
    if risk_review["hard_stop"]:
        recommendation = "no_bid"
    elif score >= 70 and not high_risks and not qualification["missing_fields"]:
        recommendation = "bid"
    else:
        recommendation = "review"

    evidence_count = len(document_analysis.get("evidence_items", {}))
    _set_tool_metrics(
        recommendation=recommendation,
        document_evidence_count=evidence_count,
        has_recorded_deadline=bool(tender.get("closing_at")),
    )
    return {
        "recommendation": recommendation,
        "rationale": "",
        "next_steps": [],
        "requires_human_approval": True,
        "external_actions_taken": [],
    }
