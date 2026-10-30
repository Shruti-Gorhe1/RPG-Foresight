from __future__ import annotations

from typing import Any, Literal, TypedDict


class PursuitState(TypedDict, total=False):
    tender: dict[str, Any]
    active_rules: list[dict[str, Any]]
    document_pages: list[dict[str, Any]]
    uploaded_documents: list[dict[str, Any]]
    agent_trace: list[dict[str, str]]
    tool_trace: list[dict[str, str]]
    workflow: list[str]
    qualification: dict[str, Any]
    document_analysis: dict[str, Any]
    risk_review: dict[str, Any]
    action_plan: dict[str, Any]
    recommendation: Literal["bid", "no_bid", "review"]
