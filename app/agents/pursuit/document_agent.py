from __future__ import annotations

import re
from typing import Any

from agents.pursuit.model import parse_model_json, reason_with_live_model
from agents.pursuit.state import PursuitState
from agents.pursuit.telemetry import record_agent_execution, record_tool_execution
from observability.tracing import traced_span
from services.pursuit_documents import extract_document_pages, find_document_evidence

MAX_REVIEW_EVIDENCE_ITEMS = 4
MAX_PREQUAL_SUMMARY_INPUT_CHARS = 10_000
DOCUMENT_REVIEW_TIMEOUT_SECONDS = 30
_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand", "lakh", "lakhs", "crore", "crores", "million", "billion",
}
_NUMBER_TOKEN = re.compile(r"\b(?:\d[\d,./-]*\d|\d|[a-z]+)\b", re.IGNORECASE)


def _summary_numbers_are_grounded(summary: str, source: str) -> bool:
    source_tokens = {
        token.casefold()
        for token in _NUMBER_TOKEN.findall(source)
        if token.isdigit() or token.casefold() in _NUMBER_WORDS
    }
    summary_tokens = {
        token.casefold()
        for token in _NUMBER_TOKEN.findall(summary)
        if token.isdigit() or token.casefold() in _NUMBER_WORDS
    }
    return summary_tokens.issubset(source_tokens)


def _summary_preserves_source_numbers(summary: str, source: str) -> bool:
    source_tokens = {
        token.casefold()
        for token in _NUMBER_TOKEN.findall(source)
        if token.isdigit() or token.casefold() in _NUMBER_WORDS
    }
    summary_tokens = {
        token.casefold()
        for token in _NUMBER_TOKEN.findall(summary)
        if token.isdigit() or token.casefold() in _NUMBER_WORDS
    }
    return source_tokens.issubset(summary_tokens)


def _build_document_evidence(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    evidence_keys: dict[tuple[str, str, str, str], str] = {}
    category_counts: dict[str, int] = {}

    def add_evidence(category: str, item: dict[str, str]) -> None:
        source_text = item.get("excerpt", item.get("value", "")).strip()
        key = (category, item["document"], item["location"], source_text)
        detected_value = item.get("value")
        if key in evidence_keys:
            evidence_id = evidence_keys[key]
            if detected_value:
                values = evidence[evidence_id].setdefault("detected_values", [])
                if detected_value not in values:
                    values.append(detected_value)
            return
        category_counts[category] = category_counts.get(category, 0) + 1
        evidence_id = f"{category.upper()}-{category_counts[category]:02d}"
        evidence_keys[key] = evidence_id
        evidence[evidence_id] = {
            "category": category,
            "document": item["document"],
            "location": item["location"],
            "text": source_text,
        }
        if detected_value:
            evidence[evidence_id]["detected_values"] = [detected_value]

    source_categories = {
        "economics": report["findings"].get("tender_economics", []),
        "eligibility": report["findings"].get("eligibility", []),
        "submissions": report["findings"].get("submission_requirements", []),
        "deadlines": report["findings"].get("deadlines", []),
        "commercial_terms": report["findings"].get("commercial_risks", []),
    }
    for category, items in source_categories.items():
        for item in items:
            add_evidence(category, item)
    for category, key in (
        ("economics", "extracted_financial_amounts"),
        ("economics", "extracted_tender_values"),
        ("deadlines", "extracted_deadlines"),
    ):
        for item in report.get(key, []):
            add_evidence(category, item)
    return evidence


def _select_review_evidence(
    evidence: dict[str, dict[str, Any]],
    limit: int = MAX_REVIEW_EVIDENCE_ITEMS,
) -> dict[str, dict[str, Any]]:
    categories: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for evidence_id, item in evidence.items():
        categories.setdefault(item["category"], []).append((evidence_id, item))

    priority = ("economics", "eligibility", "submissions", "deadlines", "commercial_terms")
    ordered_categories = [
        category for category in priority if category in categories
    ] + [
        category for category in categories if category not in priority
    ]
    for category in ordered_categories:
        categories[category].sort(
            key=lambda entry: not bool(entry[1].get("detected_values"))
        )

    selected: dict[str, dict[str, Any]] = {}
    while len(selected) < limit:
        added_item = False
        for category in ordered_categories:
            if categories[category]:
                evidence_id, item = categories[category].pop(0)
                selected[evidence_id] = item
                added_item = True
                if len(selected) == limit:
                    break
        if not added_item:
            break
    return selected


def _validated_document_summaries(
    result: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summaries: dict[str, Any] = {"economics": [], "guidelines": [], "actions": []}
    seen_ids: set[str] = set()
    if not isinstance(result.get("summaries"), list):
        raise RuntimeError("Configured model returned an invalid document summary list")
    for item in result["summaries"]:
        if not isinstance(item, dict):
            raise RuntimeError("Configured model returned an invalid document summary")
        if not isinstance(item.get("evidence_id"), str):
            raise RuntimeError("Configured model returned a summary without an evidence ID")
        evidence_id = item["evidence_id"]
        if evidence_id in seen_ids:
            raise RuntimeError("Configured model summarized document evidence more than once")
        if evidence_id not in evidence:
            raise RuntimeError("Configured model cited unknown document evidence")
        category = evidence[evidence_id]["category"]
        if category not in {"economics", "eligibility", "submissions", "deadlines", "commercial_terms"}:
            raise RuntimeError("Configured model cited unsupported document evidence")
        raw_summary = item.get("summary")
        if (
            isinstance(raw_summary, str)
            and raw_summary.strip()
            and not _summary_numbers_are_grounded(raw_summary, evidence[evidence_id]["text"])
        ):
            continue
        summary = _validate_summary_item(item, category, evidence)
        if category == "economics":
            summaries["economics"].append(summary)
        else:
            summary["category"] = category
            summaries["guidelines"].append(summary)
            raw_description = item.get("description")
            source_text = evidence[evidence_id]["text"]
            summaries["actions"].append({
                "task": summary["summary"],
                "description": _action_description(raw_description, source_text),
                "evidence_ids": [evidence_id],
            })
        seen_ids.add(evidence_id)
    if not isinstance(result["analysis"], str) or not result["analysis"].strip():
        raise RuntimeError("Configured model returned an empty document analysis")
    summaries["analysis"] = result["analysis"].strip()
    summaries["missing_evidence_ids"] = [
        evidence_id for evidence_id in evidence if evidence_id not in seen_ids
    ]
    return summaries


def _action_description(description: Any, source_text: str) -> str:
    if (
        isinstance(description, str)
        and description.strip()
        and len(description) <= 1200
        and _summary_numbers_are_grounded(description, source_text)
    ):
        return description.strip()
    return (
        "The excerpt does not specify the complete procedure. Check the cited "
        "section in the full tender and verify any referenced forms, submission "
        "method, and deadline before proceeding."
    )


def _validate_summary_item(
    item: dict[str, Any],
    expected_category: str,
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summary = item.get("summary")
    evidence_id = item.get("evidence_id")
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or len(summary) > 500
        or not isinstance(evidence_id, str)
        or evidence_id not in evidence
        or evidence[evidence_id]["category"] != expected_category
    ):
        raise RuntimeError("Configured model returned an unsupported document summary")
    detected_values = evidence[evidence_id].get("detected_values", [])
    for value in detected_values:
        if value not in summary:
            summary = f"{summary.rstrip('. ')}; amount: {value}."
    return {
        "category": expected_category,
        "summary": summary.strip(),
        "references": [{
            "document": evidence[evidence_id]["document"],
            "location": evidence[evidence_id]["location"],
            "excerpt": evidence[evidence_id]["text"],
        }],
        "evidence_ids": [evidence_id],
    }


def _prequalification_summary_inputs(
    criteria: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], set[str]]:
    requested: list[dict[str, str]] = []
    requested_keys: set[str] = set()
    total_chars = 0
    for index, criterion in enumerate(criteria, start=1):
        excerpt = criterion["excerpt"]
        if total_chars + len(excerpt) > MAX_PREQUAL_SUMMARY_INPUT_CHARS:
            continue
        criterion_key = f"criterion-{index}"
        requested.append({
            "criterion_key": criterion_key,
            "criterion_id": criterion["criterion_id"],
            "excerpt": excerpt,
        })
        requested_keys.add(criterion_key)
        total_chars += len(excerpt)
    return requested, requested_keys


def _apply_prequalification_summaries(
    criteria: list[dict[str, Any]],
    requested_criteria: list[dict[str, str]],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    requested_by_key = {
        item["criterion_key"]: item["excerpt"]
        for item in requested_criteria
    }
    summaries_by_key: dict[str, str] = {}
    returned = result.get("prequalification_summaries", [])
    if isinstance(returned, list):
        for item in returned:
            if not isinstance(item, dict):
                continue
            criterion_key = item.get("criterion_key")
            summary = item.get("summary")
            source = requested_by_key.get(criterion_key)
            if (
                source is None
                or criterion_key in summaries_by_key
                or not isinstance(summary, str)
                or not summary.strip()
                or len(summary) > 700
                or not _summary_numbers_are_grounded(summary, source)
                or not _summary_preserves_source_numbers(summary, source)
            ):
                continue
            summaries_by_key[criterion_key] = summary.strip()

    requested_key_by_criterion_index = {
        int(item["criterion_key"].removeprefix("criterion-")): item["criterion_key"]
        for item in requested_criteria
    }
    enriched: list[dict[str, Any]] = []
    for index, criterion in enumerate(criteria, start=1):
        criterion_key = requested_key_by_criterion_index.get(index)
        summary = summaries_by_key.get(criterion_key or "")
        enriched.append({
            **criterion,
            "summary": summary or criterion["excerpt"],
            "summary_source": "model" if summary else "document_excerpt",
        })
    return enriched


def _source_grounded_document_summaries(
    evidence: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> dict[str, Any]:
    summaries: dict[str, Any] = {
        "economics": [],
        "guidelines": [],
        "actions": [],
        "analysis": (
            f"Extracted {report['documents_analyzed']} document(s) and found "
            f"{len(evidence)} cited evidence item(s). The displayed findings use "
            "text and values taken directly from the uploaded documents."
        ),
        "missing_evidence_ids": [],
    }
    for evidence_id, item in evidence.items():
        category = item["category"]
        source_text = item["text"].strip()
        reference = {
            "document": item["document"],
            "location": item["location"],
            "excerpt": source_text,
        }
        summary = {
            "category": category,
            "summary": source_text[:450],
            "references": [reference],
            "evidence_ids": [evidence_id],
        }
        detected_values = item.get("detected_values", [])
        if detected_values:
            summary["summary"] = (
                f"{summary['summary'].rstrip('. ')}; "
                f"amount: {', '.join(detected_values)}."
            )
        if category == "economics":
            summaries["economics"].append(summary)
            continue

        summary["category"] = category
        summaries["guidelines"].append(summary)
        task_excerpt = source_text[:190].rstrip()
        if len(source_text) > len(task_excerpt):
            task_excerpt = f"{task_excerpt.rstrip(' .')}..."
        summaries["actions"].append({
            "task": f"Review the cited tender requirement: {task_excerpt}",
            "description": (
                "The tender states: "
                f"{source_text[:1000]} "
                "Follow the full cited section for any procedure not included in this excerpt."
            ),
            "evidence_ids": [evidence_id],
        })
    if not evidence:
        summaries["analysis"] = (
            "The uploaded text was checked, but no matching financial, eligibility, "
            "submission, deadline, or commercial clauses were extracted. Review the "
            "source document directly; no findings were generated."
        )
    return summaries


@traced_span("rpg_foresight.agent.document")
async def document_agent(state: PursuitState) -> PursuitState:
    pages = list(state.get("document_pages", []))
    documents = state.get("uploaded_documents", [])
    document_pages: dict[str, int] = {}
    for document in documents:
        extracted = extract_document_pages(document["filename"], document["content"])
        pages.extend(extracted)
        document_pages[document["filename"]] = len(extracted)
        record_tool_execution(
            state,
            parent_agent="document_agent",
            tool="extract_document_text",
            summary=f"Read {len(extracted)} searchable location(s) from {document['filename']}.",
        )
    state["document_pages"] = pages
    report = find_document_evidence(pages)
    state["document_analysis"] = report
    finding_count = sum(len(items) for items in report["findings"].values())
    record_tool_execution(
        state,
        parent_agent="document_agent",
        tool="extract_document_evidence",
        summary=f"Reviewed {report['text_locations_reviewed']} location(s); cited {finding_count} clauses.",
    )
    candidate_evidence = _build_document_evidence(report)
    evidence = _select_review_evidence(candidate_evidence)
    omitted_evidence_count = len(candidate_evidence) - len(evidence)
    evidence_by_category: dict[str, list[dict[str, Any]]] = {}
    for evidence_id, item in evidence.items():
        evidence_by_category.setdefault(item["category"], []).append({
            "evidence_id": evidence_id,
            "text": item["text"],
            "detected_values": item.get("detected_values", []),
        })
    requested_criteria, requested_criterion_keys = _prequalification_summary_inputs(
        report["prequalification_criteria"],
    )
    summaries: dict[str, Any]
    model_failure: str | None = None
    if evidence or requested_criteria:
        max_model_tokens = min(
            2048,
            768 + len(requested_criteria) * 96,
        )
        try:
            model_response = await reason_with_live_model(
                "document_agent",
                "DOCUMENT_REVIEW_JSON. Return JSON only in this shape: "
                '{"analysis":"short overall summary","summaries":[{"evidence_id":"ID from input","summary":"concise meaning or actionable requirement","description":"source-grounded instructions for carrying out this requirement"}],"prequalification_summaries":[{"criterion_key":"key from input","summary":"concise pointwise requirement"}]}. '
                "Return one summaries item for every supplied evidence ID, in the same order, with no extras. "
                "Also return one prequalification_summaries item for each supplied criterion key. "
                "Preserve each criterion's alternatives, thresholds, time periods, and document requirements; "
                "copy every numeric value exactly as written. If a criterion cannot be summarized without "
                "omitting a condition, return its exact excerpt as the summary. "
                "For economics, state what the financial term means and retain its amount. "
                "For all other categories, write the requirement as one short, actionable task. "
                "For each non-economics summary, add a description explaining how to complete the task. "
                "Use only that item's paired evidence text for the description: include a form, "
                "submission method, recipient, deadline, or sequence only when the text states it. "
                "If the excerpt does not explain the procedure, say so and direct the reader to "
                "check the cited section in the full tender; do not guess. "
                "Do not combine clauses, invent facts, or omit material conditions. "
                "Do not include references or page numbers.",
                {
                    "evidence_by_category": evidence_by_category,
                    "prequalification_criteria": requested_criteria,
                },
                max_tokens=max_model_tokens,
                timeout_seconds=DOCUMENT_REVIEW_TIMEOUT_SECONDS,
            )
            structured = parse_model_json(
                model_response,
                {"analysis", "summaries"},
            )
            report["prequalification_criteria"] = _apply_prequalification_summaries(
                report["prequalification_criteria"],
                requested_criteria,
                structured,
            )
            summaries = _validated_document_summaries(structured, evidence)
        except (RuntimeError, ValueError) as exc:
            model_failure = (
                "the configured model request timed out"
                if "exceeded" in str(exc).casefold()
                else "the configured model request failed or returned unusable output"
            )
            summaries = _source_grounded_document_summaries(evidence, report)
            report["prequalification_criteria"] = _apply_prequalification_summaries(
                report["prequalification_criteria"],
                [],
                {},
            )
    else:
        summaries = _source_grounded_document_summaries(evidence, report)
        report["prequalification_criteria"] = _apply_prequalification_summaries(
            report["prequalification_criteria"],
            [],
            {},
        )

    source_excerpt_summaries = sum(
        item["summary_source"] == "document_excerpt"
        for item in report["prequalification_criteria"]
    )
    unrequested_criterion_count = (
        len(report["prequalification_criteria"]) - len(requested_criterion_keys)
    )
    if source_excerpt_summaries and not model_failure:
        invalid_model_summary_count = source_excerpt_summaries - unrequested_criterion_count
        if invalid_model_summary_count:
            report["limitations"].append(
                f"The document-review response did not provide a valid source-grounded "
                f"summary for {invalid_model_summary_count} pre-qualification "
                "criterion/criteria; exact extracted criterion text is shown instead."
            )
    if unrequested_criterion_count:
        report["limitations"].append(
            f"{unrequested_criterion_count} additional pre-qualification "
            "criterion/criteria exceeded the summary request size limit; their "
            "exact extracted text and citations are still shown."
        )
    if model_failure:
        report["limitations"].append(
            "The configured model did not complete document review "
            f"({model_failure}); cited source excerpts and extracted values are "
            "shown without model-generated summaries."
        )
        record_tool_execution(
            state,
            parent_agent="document_agent",
            tool="document_review_model_fallback",
            summary=(
                "The configured model did not complete; returned source-grounded "
                "document excerpts instead."
            ),
        )
    missing_summary_count = len(summaries.pop("missing_evidence_ids"))
    source_fallback_count = 0
    summarized_ids = {
        item["evidence_ids"][0]
        for category in ("economics", "guidelines")
        for item in summaries[category]
    }
    for evidence_id, item in evidence.items():
        if evidence_id in summarized_ids:
            continue
        fallback = _validate_summary_item(
            {"evidence_id": evidence_id, "summary": item["text"]},
            item["category"],
            evidence,
        )
        if item["category"] == "economics":
            summaries["economics"].append(fallback)
        else:
            fallback["category"] = item["category"]
            summaries["guidelines"].append(fallback)
            summaries["actions"].append({
                "task": fallback["summary"],
                "description": _action_description(None, item["text"]),
                "evidence_ids": [evidence_id],
            })
        source_fallback_count += 1
    if omitted_evidence_count or missing_summary_count:
        report["limitations"].append(
            "For faster review, model summaries cover at most "
            f"{MAX_REVIEW_EVIDENCE_ITEMS} priority evidence items. "
            f"Source-grounded clause text was used for {source_fallback_count} item(s) the model omitted; "
            f"{omitted_evidence_count} lower-priority item(s) were not summarized."
        )
    report["economics_summaries"] = summaries["economics"]
    report["processing_guidelines"] = summaries["guidelines"]
    report["suggested_actions"] = summaries["actions"]
    report["agent_analysis"] = summaries["analysis"]
    report["evidence_items"] = evidence
    record_agent_execution(
        state,
        name="document_agent",
        summary=f"Read {report['documents_analyzed']} document(s), cited {finding_count} excerpts. {summaries['analysis']}",
        input_data={
            "documents": document_pages,
            "text_locations_reviewed": report["text_locations_reviewed"],
            "evidence_summarized": len(evidence) - missing_summary_count,
            "evidence_omitted": omitted_evidence_count + missing_summary_count,
            "source_fallback_count": source_fallback_count,
        },
        output_data={
            "finding_count": finding_count,
            "financial_amount_count": len(report["extracted_financial_amounts"]),
            "deadline_count": len(report["extracted_deadlines"]),
            "timeline_count": len(report["extracted_timeline"]),
            "prequalification_criterion_count": len(report["prequalification_criteria"]),
            "analysis": summaries["analysis"],
            "economics_summary_count": len(summaries["economics"]),
            "guideline_count": len(summaries["guidelines"]),
            "source_fallback_count": source_fallback_count,
        },
    )
    return state
