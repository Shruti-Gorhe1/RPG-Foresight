"""Lexical retrieval for source-grounded questions about uploaded tenders."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "can",
    "do", "does", "for", "from", "how", "i", "in", "is", "it", "me",
    "of", "on", "or", "please", "tell", "that", "the", "this", "to",
    "what", "when", "where", "which", "who", "why", "with", "you",
}
_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 180
_TENDER_VALUE_QUESTION = re.compile(
    r"\b(?:tender|contract|project)\s+value\b|"
    r"\bvalue\s+of\s+(?:the\s+)?(?:tender|contract|project)\b|"
    r"\bestimated\s+(?:tender|project)\s+(?:cost|value|amount)\b|"
    r"\bbid\s+value\b",
    re.IGNORECASE,
)
_TENDER_COST_QUESTION = re.compile(
    r"\b(?:tender|contract|project)\s+cost\b|"
    r"\bcost\s+of\s+(?:the\s+)?(?:tender|contract|project|work)\b|"
    r"\bestimated\s+(?:tender|project)?\s*cost\b",
    re.IGNORECASE,
)
_TENDER_VALUE_LABEL = re.compile(
    r"\b(?:estimated\s+(?:tender|project)\s+value|"
    r"(?:tender|contract|project)\s+value|bid\s+value)\b",
    re.IGNORECASE,
)
_TENDER_COST_LABEL = re.compile(
    r"\b(?:estimated\s+(?:(?:tender|project)\s+)?cost|"
    r"(?:tender|contract|project)\s+cost|cost\s+of\s+(?:the\s+)?"
    r"(?:tender|contract|project|work))\b",
    re.IGNORECASE,
)
_TENDER_VALUE_COMPARISON = re.compile(
    r"\b(?:difference|differentiate|distinguish|compare|comparison)\b"
    r".{0,80}\b(?:tender|contract|project)\s+(?:value|cost)\b"
    r".{0,80}\b(?:tender|contract|project)\s+(?:value|cost)\b|"
    r"\b(?:tender|contract|project)\s+(?:value|cost)\b"
    r".{0,80}\b(?:difference|differentiate|distinguish|compare|comparison)\b"
    r".{0,80}\b(?:tender|contract|project)\s+(?:value|cost)\b",
    re.IGNORECASE,
)
_PREREQUISITE_QUESTION = re.compile(
    r"\b(?:pre[- ]?requisites?|pre[- ]?qualification|eligibility|"
    r"qualification criteria|qualifying requirements?|bidder requirements?)\b|"
    r"\bwhat (?:must|does|do|should) (?:a|the|an)?\s*(?:bidder|applicant|contractor)?"
    r".{0,35}\b(?:qualify|eligible|submit|meet)\b",
    re.IGNORECASE,
)
_SUBMISSION_QUESTION = re.compile(
    r"\b(?:documents?|paperwork|forms?|certificates?|what to submit|"
    r"submission requirements?)\b",
    re.IGNORECASE,
)
_PREREQUISITE_EVIDENCE_TERMS = re.compile(
    r"\b(?:eligib(?:le|ility)|qualif(?:y|ied|ication)|pre[- ]?qualif|"
    r"experience|turnover|financial capacity|net worth|solvency|"
    r"blacklist(?:ed|ing)?|debar(?:red|ment)?|consortium|joint venture|"
    r"technical capacity|similar.{0,40}\b(?:work|contract)|license|licence|registration|local supplier|"
    r"local content|class[- ]?[i1i]+ supplier)\b",
    re.IGNORECASE,
)
_RISK_QUESTION = re.compile(
    r"\b(?:key\s+risks?|risks?|risk\s+factors?|commercial\s+risks?|"
    r"potential\s+issues?|major\s+concerns?)\b",
    re.IGNORECASE,
)
_MISLEADING_VALUE_CONTEXT = re.compile(
    r"\b(?:class\s*[-–]?\s*[i1]+\s+local|local\s+supplier|local\s+content|"
    r"purchase\s+preference|preferred\s+over|qualification|pre[- ]qualification|"
    r"similar\s+work|security\s+deposit|earnest\s+money|bid\s+security|"
    r"\d+(?:\.\d+)?\s*%|percent(?:age)?|above|below|less\s+than|"
    r"more\s+than|greater\s+than|exceed(?:s|ing)?)\b",
    re.IGNORECASE,
)
_DIRECT_AMOUNT_AFTER_LABEL = re.compile(
    r"^\s*(?:\(\s*(?P<parent_currency>INR|Rs\.?|₹)\s*\)\s*)?"
    r"(?:(?:is|of(?:\s+the)?\s+work|put\s+to)\s*)?(?:[:=]\s*)?"
    r"(?:(?P<currency>INR|Rs\.?|₹)\s*)?"
    r"(?P<amount>(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?)"
    r"(?![\d,])",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.casefold())
        if token not in _STOP_WORDS
    ]


def _directly_labeled_tender_value(
    text: str,
    label: re.Match[str],
) -> tuple[re.Match[str], str] | None:
    line_start = text.rfind("\n", 0, label.start()) + 1
    line_end = text.find("\n", label.end())
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    label_start = label.start() - line_start
    label_end = label.end() - line_start
    following = line[label_end:]
    amount = _DIRECT_AMOUNT_AFTER_LABEL.match(following)
    excerpt = line
    if amount is None:
        value_lines = [line]
        for following_line in text[line_end + 1:].splitlines()[:2]:
            candidate = following_line.strip()
            if re.fullmatch(r"[\[(]?(?:INR|Rs\.?|₹)[\])]?", candidate, re.IGNORECASE):
                value_lines.append(following_line)
                continue
            if re.fullmatch(r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\s*/?-?", candidate):
                value_lines.append(following_line)
                break
            break
        if len(value_lines) > 1:
            following = " ".join(value_lines)[label_end:]
            amount = _DIRECT_AMOUNT_AFTER_LABEL.match(following)
            excerpt = " ".join(value_lines)
    if not amount or re.match(r"\s*(?:%|percent\b)", following[amount.end():], re.IGNORECASE):
        return None

    start = max(0, label_start - 100)
    context_end = min(len(line), label_end + amount.end() + 100)
    context = line[start:context_end]
    if _MISLEADING_VALUE_CONTEXT.search(context):
        return None
    return amount, excerpt


def _page_chunks(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for page in pages:
        text = str(page.get("text", "")).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + _CHUNK_SIZE, len(text))
            if end < len(text):
                boundary = max(
                    text.rfind("\n", start + _CHUNK_SIZE // 2, end),
                    text.rfind(" ", start + _CHUNK_SIZE // 2, end),
                )
                if boundary > start:
                    end = boundary
            content = text[start:end].strip()
            if content:
                chunks.append({
                    "document": str(page["filename"]),
                    "location": str(page["location"]),
                    "text": content,
                })
            if end >= len(text):
                break
            start = max(start + 1, end - _CHUNK_OVERLAP)
    return chunks


def answer_explicit_tender_value_question(
    question: str,
    source_pages: list[dict[str, Any]],
    extracted_financial_amounts: list[dict[str, Any]] | None = None,
    *,
    allow_estimated_cost_fallback: bool = True,
    return_none_if_not_found: bool = False,
) -> dict[str, Any] | None:
    """Answer tender cost/value questions from labeled extracted amounts."""
    if _TENDER_VALUE_COMPARISON.search(question):
        return None
    asks_tender_value = bool(_TENDER_VALUE_QUESTION.search(question))
    asks_tender_cost = bool(_TENDER_COST_QUESTION.search(question))
    if not asks_tender_value and not asks_tender_cost:
        return None

    supported_values: dict[tuple[str, str], dict[str, Any]] = {}
    accepted_cost_types = (
        {"estimated cost", "tender cost", "project cost"}
        if asks_tender_cost and not asks_tender_value
        else {"tender value"}
        if asks_tender_value and not asks_tender_cost
        else {"estimated cost", "tender cost", "project cost", "tender value"}
    )
    for item in extracted_financial_amounts or []:
        cost_type = str(item.get("cost_type", "")).strip().casefold()
        if cost_type not in accepted_cost_types or (
            cost_type == "tender value"
            and _MISLEADING_VALUE_CONTEXT.search(str(item.get("excerpt", "")))
        ):
            continue
        value = str(item.get("value", "")).strip()
        if not value:
            continue
        document = str(item.get("document", ""))
        location = str(item.get("location", ""))
        key = (cost_type, value.casefold())
        supported_values.setdefault(key, {
                "value": value,
                "excerpt": str(item.get("excerpt", "")),
                "cost_type": str(item.get("cost_type", "")),
                "references": [],
            })
        reference = {"document": document, "location": location, "excerpt": str(item.get("excerpt", ""))}
        if reference not in supported_values[key]["references"]:
            supported_values[key]["references"].append(reference)

    for page in source_pages:
        text = str(page.get("text", ""))
        label_patterns = (
            [(_TENDER_COST_LABEL, "Estimated cost")]
            if asks_tender_cost and not asks_tender_value
            else [(_TENDER_VALUE_LABEL, "Tender value")]
            if asks_tender_value and not asks_tender_cost
            else [
                (_TENDER_COST_LABEL, "Estimated cost"),
                (_TENDER_VALUE_LABEL, "Tender value"),
            ]
        )
        for label_pattern, cost_type in label_patterns:
            for label in label_pattern.finditer(text):
                direct_value = _directly_labeled_tender_value(text, label)
                if direct_value is None:
                    continue
                amount_match, excerpt = direct_value
                currency = (
                    amount_match.group("currency")
                    or amount_match.group("parent_currency")
                )
                value = " ".join(
                    part for part in (currency, amount_match.group("amount")) if part
                )
                document = str(page.get("filename", ""))
                location = str(page.get("location", ""))
                excerpt = " ".join(excerpt.split())
                key = (cost_type.casefold(), value.casefold())
                supported_values.setdefault(key, {
                        "value": value,
                        "cost_type": cost_type,
                        "references": [],
                    })
                reference = {"document": document, "location": location, "excerpt": excerpt}
                if reference not in supported_values[key]["references"]:
                    supported_values[key]["references"].append(reference)

    used_estimated_cost_fallback = False
    if (
        not supported_values
        and asks_tender_value
        and not asks_tender_cost
        and allow_estimated_cost_fallback
    ):
        for item in extracted_financial_amounts or []:
            if str(item.get("cost_type", "")).strip().casefold() != "estimated cost":
                continue
            excerpt = str(item.get("excerpt", ""))
            label = _TENDER_COST_LABEL.search(excerpt)
            direct_value = (
                _directly_labeled_tender_value(excerpt, label)
                if label is not None
                else None
            )
            if direct_value is None:
                continue
            amount_match, _ = direct_value
            extracted_number = re.sub(r"\D", "", amount_match.group("amount"))
            item_amount = re.search(r"\d[\d,]*(?:\.\d+)?", str(item.get("value", "")))
            if (
                item_amount is None
                or extracted_number != re.sub(r"\D", "", item_amount.group())
            ):
                continue
            value = str(item.get("value", "")).strip()
            document = str(item.get("document", ""))
            location = str(item.get("location", ""))
            key = ("estimated cost", value.casefold())
            supported_values.setdefault(key, {
                "value": value,
                "cost_type": "Estimated cost",
                "references": [],
            })
            reference = {
                "document": document,
                "location": location,
                "excerpt": excerpt,
            }
            if reference not in supported_values[key]["references"]:
                supported_values[key]["references"].append(reference)

        if not supported_values:
            for page in source_pages:
                text = str(page.get("text", ""))
                for label in _TENDER_COST_LABEL.finditer(text):
                    direct_value = _directly_labeled_tender_value(text, label)
                    if direct_value is None:
                        continue
                    amount_match, excerpt = direct_value
                    currency = (
                        amount_match.group("currency")
                        or amount_match.group("parent_currency")
                    )
                    value = " ".join(
                        part
                        for part in (currency, amount_match.group("amount"))
                        if part
                    )
                    key = ("estimated cost", value.casefold())
                    supported_values.setdefault(key, {
                        "value": value,
                        "cost_type": "Estimated cost",
                        "references": [],
                    })
                    reference = {
                        "document": str(page.get("filename", "")),
                        "location": str(page.get("location", "")),
                        "excerpt": " ".join(excerpt.split()),
                    }
                    if reference not in supported_values[key]["references"]:
                        supported_values[key]["references"].append(reference)
        used_estimated_cost_fallback = bool(supported_values)

    if not supported_values:
        if return_none_if_not_found:
            return None
        question_target = "tender cost" if asks_tender_cost and not asks_tender_value else "tender value"
        return {
            "answer": (
                f"I couldn't identify a directly labeled {question_target} in the "
                "extracted document text. I won't substitute a deposit, fee, "
                "qualification threshold, or percentage. Check the cited cost/"
                "value schedule in the original tender; a scanned or poorly "
                "extracted table may need OCR or review."
            ),
            "sources": [],
        }

    values = list(supported_values.values())
    if used_estimated_cost_fallback:
        answer_intro = (
            "The document does not separately label a tender value. It does state "
            "the following estimated cost, which is the closest explicitly stated "
            "cost/value figure I found: "
        )
    elif asks_tender_cost and not asks_tender_value:
        answer_intro = "The tender document labels the following as its estimated cost: "
    else:
        answer_intro = "The tender document explicitly states "
    answer = answer_intro + "; ".join(
        f"{item['value']} ({_format_reference_locations(item['references'])}"
        f"{', ' + item['cost_type'] if item.get('cost_type') else ''})"
        for item in values
    ) + "."
    return {
        "answer": answer,
        "sources": [
            reference
            for item in values
            for reference in item["references"]
        ],
    }


def _format_reference_locations(references: list[dict[str, str]]) -> str:
    return ", ".join(
        f"{reference['document']} · {reference['location']}"
        for reference in references
    )


def answer_prerequisite_question(
    question: str,
    document_analysis: dict[str, Any],
) -> dict[str, Any] | None:
    """Return extracted qualification and submission requirements as plain points."""
    if not _PREREQUISITE_QUESTION.search(question):
        return None

    criteria = document_analysis.get("prequalification_criteria", [])
    findings = document_analysis.get("findings", {})
    eligibility = findings.get("eligibility", []) if isinstance(findings, dict) else []
    submissions = (
        findings.get("submission_requirements", [])
        if isinstance(findings, dict)
        else []
    )

    def point_text(item: dict[str, Any]) -> str:
        text = str(item.get("summary") or item.get("excerpt", "")).strip()
        identifier = str(item.get("criterion_id", "")).strip()
        if identifier and not text.startswith(identifier):
            return f"{identifier}: {text}"
        return text

    def unique_points(items: list[Any]) -> list[str]:
        points: list[str] = []
        normalized_points: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = point_text(item)
            normalized = " ".join(text.casefold().split())
            normalized = re.sub(r"^\d+(?:\.\d+)*:\s*", "", normalized)
            normalized = re.sub(
                r"^(?:the\s+)?(?:applicant|bidder|contractor)\s+"
                r"(?:should|must|shall|has|have)\s+"
                r"(?:satisfactorily\s+)?",
                "",
                normalized,
            )
            if not normalized or any(
                normalized in existing_normalized
                or existing_normalized in normalized
                for existing_normalized in normalized_points
            ):
                continue
            points.append(text)
            normalized_points.append(normalized)
        return points

    qualification_points = unique_points([
        *(criteria if isinstance(criteria, list) else []),
        *(eligibility if isinstance(eligibility, list) else []),
    ])
    submission_points = unique_points(
        submissions if isinstance(submissions, list) else [],
    )

    if not qualification_points and not submission_points:
        return None

    answer_sections: list[str] = []
    if qualification_points:
        answer_sections.append(
            "Eligibility and qualification requirements:\n"
            + "\n".join(f"- {point}" for point in qualification_points)
        )
    if submission_points:
        answer_sections.append(
            "Required documents or submissions:\n"
            + "\n".join(f"- {point}" for point in submission_points)
        )
    return {"answer": "\n\n".join(answer_sections), "sources": []}


def collect_prerequisite_evidence(
    question: str,
    document_analysis: dict[str, Any],
) -> list[dict[str, str]] | None:
    """Select concise qualification evidence relevant to a bidder's prerequisites."""
    if not _PREREQUISITE_QUESTION.search(question):
        return None

    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    include_submissions = bool(_SUBMISSION_QUESTION.search(question))

    def add(category: str, text: str) -> None:
        normalized_text = " ".join(text.split()).strip()
        key = normalized_text.casefold()
        if not key or key in seen:
            return
        seen.add(key)
        evidence.append({"category": category, "text": normalized_text[:700]})

    criteria = document_analysis.get("prequalification_criteria", [])
    if isinstance(criteria, list):
        for item in criteria:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary", "")).strip()
            if item.get("summary_source") == "model" and summary:
                add("prequalification", summary)
                continue
            excerpt = str(item.get("excerpt", ""))
            for clause in re.split(r"(?<=[.!?])\s+|\s*[;|]\s*", excerpt):
                if _PREREQUISITE_EVIDENCE_TERMS.search(clause):
                    add("prequalification", clause)

    findings = document_analysis.get("findings", {})
    if isinstance(findings, dict):
        eligibility = findings.get("eligibility", [])
        if isinstance(eligibility, list):
            for item in eligibility:
                if isinstance(item, dict):
                    add("eligibility", str(item.get("excerpt", "")))

        if include_submissions:
            submissions = findings.get("submission_requirements", [])
            if isinstance(submissions, list):
                for item in submissions:
                    if isinstance(item, dict):
                        add("submission", str(item.get("excerpt", "")))

    return evidence[:24]


def collect_tender_risk_evidence(
    question: str,
    document_analysis: dict[str, Any],
) -> list[dict[str, str]] | None:
    """Collect risk-relevant clauses for a concise, source-grounded answer."""
    if not _RISK_QUESTION.search(question):
        return None

    findings = document_analysis.get("findings", {})
    if not isinstance(findings, dict):
        findings = {}

    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    for category in (
        "commercial_risks",
        "eligibility",
        "deadlines",
        "submission_requirements",
    ):
        items = findings.get(category, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if len(evidence) >= 20:
                break
            if not isinstance(item, dict):
                continue
            excerpt = " ".join(str(item.get("excerpt", "")).split()).strip()
            normalized = excerpt.casefold()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            evidence.append({
                "category": category,
                "text": excerpt[:800],
            })

    disqualifiers = document_analysis.get("explicit_disqualifier_evidence", [])
    if isinstance(disqualifiers, list):
        for item in disqualifiers:
            if len(evidence) >= 20:
                break
            if not isinstance(item, dict):
                continue
            excerpt = " ".join(str(item.get("excerpt", "")).split()).strip()
            normalized = excerpt.casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                evidence.append({
                    "category": "explicit_disqualification",
                    "text": excerpt[:800],
                })
    return evidence


def answer_tender_value_cost_comparison(
    question: str,
    source_pages: list[dict[str, Any]],
    extracted_financial_amounts: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Explain tender cost/value using separately sourced amounts when available."""
    if not _TENDER_VALUE_COMPARISON.search(question):
        return None

    costs = answer_explicit_tender_value_question(
        "What is the tender cost?",
        source_pages,
        extracted_financial_amounts,
    )
    values = answer_explicit_tender_value_question(
        "What is the tender value?",
        source_pages,
        extracted_financial_amounts,
        allow_estimated_cost_fallback=False,
    )
    cost_sources = costs["sources"] if costs else []
    value_sources = values["sources"] if values else []
    cost_text = (
        "In this document, the extracted estimated cost is "
        + costs["answer"].replace(
            "The tender document labels the following as its estimated cost: ",
            "",
        ).rstrip(".")
        + "."
        if costs and cost_sources
        else "No estimated-cost amount was confidently extracted from the uploaded text."
    )
    value_text = (
        "A separately labeled tender value is "
        + values["answer"].replace(
            "The tender document explicitly states ",
            "",
        ).rstrip(".")
        + "."
        if values and value_sources
        else "No separate, directly stated tender-value amount was confidently extracted from the uploaded text."
    )
    answer = (
        "Tender cost (often shown as the estimated cost) is the procuring authority's "
        "estimate for the work. Tender value refers to the monetary value of the "
        "procurement/contract; a document may use these terms for the same amount, "
        "but they should not be assumed identical when it does not say so. "
        f"{cost_text} {value_text}"
    )
    return {
        "answer": answer,
        "sources": [*cost_sources, *value_sources],
    }


def retrieve_tender_evidence(
    question: str,
    pages: list[dict[str, Any]],
    *,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Rank tender excerpts with BM25 and return only excerpts matching the query."""
    query_terms = _tokens(question)
    is_tender_cost_question = bool(_TENDER_COST_QUESTION.search(question))
    if is_tender_cost_question:
        query_terms.extend(
            ("estimated", "amount", "value", "price", "rates", "schedule", "quoted", "total")
        )
    if not query_terms:
        return []

    chunks = _page_chunks(pages)
    if not chunks:
        return []
    tokenized_chunks = [_tokens(chunk["text"]) for chunk in chunks]
    document_frequency: Counter[str] = Counter()
    for terms in tokenized_chunks:
        document_frequency.update(set(terms))

    average_length = sum(map(len, tokenized_chunks)) / len(tokenized_chunks) or 1
    query_counts = Counter(query_terms)
    ranked: list[tuple[float, int]] = []
    for index, terms in enumerate(tokenized_chunks):
        term_counts = Counter(terms)
        matched_terms = sum(1 for term in query_counts if term_counts[term])
        if is_tender_cost_question:
            required_matches = max(2, math.ceil(len(query_counts) * 0.25))
        else:
            required_matches = (
                len(query_counts)
                if len(query_counts) <= 2
                else max(2, math.ceil(len(query_counts) * 0.6))
            )
        if matched_terms < required_matches:
            continue
        length = len(terms)
        score = 0.0
        for term, query_frequency in query_counts.items():
            frequency = term_counts[term]
            if not frequency:
                continue
            inverse_document_frequency = math.log(
                1 + (len(chunks) - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * length / average_length
            )
            score += (
                inverse_document_frequency
                * frequency
                * 2.5
                / denominator
                * min(query_frequency, 2)
            )
        if score:
            ranked.append((score, index))

    ranked.sort(key=lambda result: result[0], reverse=True)
    results: list[dict[str, str]] = []
    for _, index in ranked[:limit]:
        chunk = chunks[index]
        results.append({
            "source_id": f"S{len(results) + 1}",
            **chunk,
        })
    return results
