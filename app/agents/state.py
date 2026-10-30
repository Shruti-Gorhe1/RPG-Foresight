"""AgentState — the shared contract across all LangGraph nodes.

This is the accelerator baseline: a session-scoped, message-driven state with a
supervisor routing field and a free-form ``collected`` bag for domain data.
Extend it with typed sub-dicts for your domain (see how digital-onboarding adds
CustomerProfile, KYCResult, etc.).
"""
from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict

StepStatus = Literal["pending", "in_progress", "completed", "failed", "escalated"]


class Message(TypedDict, total=False):
    role: Literal["user", "assistant", "system"]
    agent: str          # which node produced an assistant message
    content: str


class AgentState(TypedDict, total=False):
    # ── Identity ────────────────────────────────────────────────────────────────
    session_id: str
    tenant_id: str

    # ── Conversation ────────────────────────────────────────────────────────────
    messages: list[Message]

    # ── Supervisor routing ──────────────────────────────────────────────────────
    next_agent: str          # set by the supervisor; read by next_agent()
    turn_count: int          # per-turn step limiter guard

    # ── Progress ────────────────────────────────────────────────────────────────
    current_step: str
    step_status: StepStatus

    # ── Domain data ─────────────────────────────────────────────────────────────
    collected: dict[str, Any]

    # ── Human-in-the-loop ───────────────────────────────────────────────────────
    human_review_reason: str
