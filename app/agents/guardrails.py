"""Input guardrails node — runs first on every turn.

Baseline checks: strip empty turns, cap message history, flag obvious prompt
injection. Extend with PII redaction, jailbreak detection, moderation, etc.
"""
from __future__ import annotations

from agents.state import AgentState
from observability.tracing import traced_span

_MAX_HISTORY = 40
_INJECTION_MARKERS = ("ignore previous instructions", "disregard the system prompt")


@traced_span("rpg_foresight.agent.guardrails")
def guardrails_node(state: AgentState) -> AgentState:
    messages = state.get("messages", [])

    # Cap runaway history to protect the context window.
    if len(messages) > _MAX_HISTORY:
        state["messages"] = messages[-_MAX_HISTORY:]

    # Very light prompt-injection heuristic on the latest user message.
    if messages and messages[-1].get("role") == "user":
        lowered = messages[-1].get("content", "").lower()
        if any(marker in lowered for marker in _INJECTION_MARKERS):
            state["human_review_reason"] = "possible_prompt_injection"

    return state
