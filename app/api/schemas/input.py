"""Request schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    message: str = Field(default="", description="Opening user message")
    context: dict[str, Any] | None = Field(default=None, description="Seed data for the session")


class ResumeRequest(BaseModel):
    session_id: str
    message: str
