"""Temporal activities — the side-effecting steps a workflow orchestrates.

Activities run in the worker process (workers/worker.py). Keep them
idempotent where possible; Temporal may retry them. The LangGraph turn runs
inside ``run_agent_turn`` so every turn is traced and durable.
"""
from __future__ import annotations

from typing import Any

from temporalio import activity

from agents.graph import compiled_graph
from db.base import AsyncSessionLocal
from db.models import Session as AgentSession
from shared.logger import get_logger

log = get_logger("workflows.activities")


@activity.defn
async def run_agent_turn(state: dict[str, Any]) -> dict[str, Any]:
    """Execute one turn of the LangGraph supervisor loop and return new state."""
    result = await compiled_graph.ainvoke(state)
    return dict(result)


@activity.defn
async def persist_session_to_db(session_id: str, state: dict[str, Any]) -> None:
    """Persist the durable agent session in PostgreSQL."""
    async with AsyncSessionLocal.begin() as db:
        record = await db.get(AgentSession, session_id)
        if record is None:
            record = AgentSession(session_id=session_id)
            db.add(record)
        record.state = state
        record.status = state.get("step_status", "active")
        record.current_step = state.get("current_step", "start")
    log.info("persist_session_to_db", session_id=session_id, step=state.get("current_step"))


@activity.defn
async def send_status_notification(session_id: str, status: str) -> None:
    """Notify the customer of a status change (email/SMS). Stubbed by default."""
    log.info("send_status_notification", session_id=session_id, status=status)
