"""Example session router — start / resume / fetch an agent session.

Runs the LangGraph turn inline and persists state to PostgreSQL, so the app works
end-to-end without a Temporal worker. To make runs durable, swap the inline
``compiled_graph.ainvoke`` for a Temporal workflow start (see the commented
block) and let workers/worker.py execute the turn.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import compiled_graph
from api.auth import CurrentUser, get_current_user
from api.schemas.input import ResumeRequest, StartRequest
from api.schemas.output import SessionResponse
from db.base import get_db_session
from db.models import Session as AgentSession
from observability.tracing import traced_span
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.example")


async def _load(db: AsyncSession, session_id: str) -> dict:
    record = await db.get(AgentSession, session_id)
    if record is None:
        raise HTTPException(404, f"session {session_id} not found")
    return record.state


async def _save(db: AsyncSession, session_id: str, state: dict) -> None:
    record = await db.get(AgentSession, session_id)
    if record is None:
        record = AgentSession(
            session_id=session_id,
            state=state,
            status=state.get("step_status", "active"),
            current_step=state.get("current_step", "start"),
        )
        db.add(record)
    else:
        record.state = state
        record.status = state.get("step_status", "active")
        record.current_step = state.get("current_step", "start")


@router.post("/start", response_model=SessionResponse)
@traced_span("rpg_foresight.agent_graph.start")
async def start(
    req: StartRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> SessionResponse:
    session_id = f"S-{uuid.uuid4().hex[:8].upper()}"
    state: dict = {
        "session_id": session_id,
        "tenant_id": current_user.tenant_id,
        "messages": [{"role": "user", "content": req.message}] if req.message else [],
        "collected": req.context or {},
        "current_step": "start",
        "step_status": "in_progress",
        "turn_count": 0,
    }

    # ── Durable alternative (Temporal) ──────────────────────────────────────────
    # from temporalio.client import Client
    # from workflows.example_workflow import ExampleWorkflow
    # from shared.config import get_settings
    # s = get_settings()
    # client = await Client.connect(s.temporal_host, namespace=s.temporal_namespace)
    # state = await client.execute_workflow(
    #     ExampleWorkflow.run, state,
    #     id=f"example-{session_id}", task_queue=s.temporal_task_queue_agents,
    # )
    try:
        state = dict(await compiled_graph.ainvoke(state))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await _save(db, session_id, state)
    return SessionResponse.from_state(state)


@router.post("/resume", response_model=SessionResponse)
@traced_span("rpg_foresight.agent_graph.resume")
async def resume(
    req: ResumeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> SessionResponse:
    state = await _load(db, req.session_id)
    if state.get("tenant_id") != current_user.tenant_id:
        raise HTTPException(404, f"session {req.session_id} not found")
    state.setdefault("messages", []).append({"role": "user", "content": req.message})
    state["step_status"] = "in_progress"
    state["turn_count"] = 0
    try:
        state = dict(await compiled_graph.ainvoke(state))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await _save(db, req.session_id, state)
    return SessionResponse.from_state(state)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> SessionResponse:
    state = await _load(db, session_id)
    if state.get("tenant_id") != current_user.tenant_id:
        raise HTTPException(404, f"session {session_id} not found")
    return SessionResponse.from_state(state)
