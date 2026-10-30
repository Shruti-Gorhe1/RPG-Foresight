from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from db.base import Base
from db.models import Session as AgentSession
from workflows import activities


@pytest.mark.asyncio
async def test_temporal_session_persistence_uses_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(activities, "AsyncSessionLocal", session_factory)
    try:
        await activities.persist_session_to_db(
            "S-LOCAL",
            {"current_step": "review", "step_status": "in_progress", "messages": []},
        )
        await activities.persist_session_to_db(
            "S-LOCAL",
            {"current_step": "complete", "step_status": "completed", "messages": ["done"]},
        )

        async with session_factory() as session:
            record = await session.get(AgentSession, "S-LOCAL")
            assert record is not None
            assert record.current_step == "complete"
            assert record.status == "completed"
            assert record.state["messages"] == ["done"]
    finally:
        await engine.dispose()
