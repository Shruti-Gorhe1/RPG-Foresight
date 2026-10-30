from __future__ import annotations

import json
from typing import Any


def _json_text(value: Any, limit: int = 12_000) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)[:limit]


def record_agent_execution(
    state: dict[str, Any],
    *,
    name: str,
    summary: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
) -> None:
    from opentelemetry import trace

    span = trace.get_current_span()
    context = span.get_span_context()
    span.set_attribute("agent.name", name)
    span.set_attribute("input.value", _json_text(input_data))
    span.set_attribute("output.value", _json_text(output_data))
    state.setdefault("agent_trace", []).append({
        "agent": name,
        "summary": summary,
        "trace_id": f"{context.trace_id:032x}" if context.is_valid else "",
        "span_id": f"{context.span_id:016x}" if context.is_valid else "",
    })


def record_tool_execution(
    state: dict[str, Any],
    *,
    parent_agent: str,
    tool: str,
    summary: str,
) -> None:
    state.setdefault("tool_trace", []).append({
        "parent_agent": parent_agent,
        "tool": tool,
        "summary": summary,
    })
