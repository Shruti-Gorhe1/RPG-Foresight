from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.routers import example
from db.base import Base, get_db_session


@pytest.mark.asyncio
async def test_playground_session_uses_database_without_redis(
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

    async def override_db() -> AsyncIterator[Any]:
        async with session_factory() as session:
            yield session
            await session.commit()

    class FakeGraph:
        async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
            state["current_step"] = "tender_operations_agent"
            state["step_status"] = "completed"
            state.setdefault("messages", []).append(
                {"role": "assistant", "agent": "tender_operations_agent", "content": "test reply"}
            )
            return state

    monkeypatch.setattr(example, "compiled_graph", FakeGraph())
    app = FastAPI()
    app.include_router(example.router, prefix="/api/v1/example")
    app.dependency_overrides[get_db_session] = override_db

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            started = await client.post("/api/v1/example/start", json={"message": "hello"})
            assert started.status_code == 200
            session_id = started.json()["session_id"]
            assert started.json()["messages"][-1]["content"] == "test reply"

            resumed = await client.post(
                "/api/v1/example/resume",
                json={"session_id": session_id, "message": "continue"},
            )
            assert resumed.status_code == 200
            assert resumed.json()["messages"][-1]["content"] == "test reply"

            fetched = await client.get(f"/api/v1/example/{session_id}")
            assert fetched.status_code == 200
            assert fetched.json()["session_id"] == session_id

            other_tenant_headers = {"Authorization": "Bearer dev:tenant-b"}
            hidden_session = await client.get(
                f"/api/v1/example/{session_id}",
                headers=other_tenant_headers,
            )
            assert hidden_session.status_code == 404

            hidden_resume = await client.post(
                "/api/v1/example/resume",
                json={"session_id": session_id, "message": "continue"},
                headers=other_tenant_headers,
            )
            assert hidden_resume.status_code == 404
    finally:
        await engine.dispose()
