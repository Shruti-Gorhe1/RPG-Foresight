"""Response schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SessionResponse(BaseModel):
    session_id: str
    current_step: str
    step_status: str
    messages: list[dict[str, Any]]
    collected: dict[str, Any]

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "SessionResponse":
        return cls(
            session_id=state.get("session_id", ""),
            current_step=state.get("current_step", ""),
            step_status=state.get("step_status", ""),
            messages=state.get("messages", []),
            collected=state.get("collected", {}),
        )
