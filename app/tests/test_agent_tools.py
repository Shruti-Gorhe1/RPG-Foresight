from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agents.nodes import tender_operations_agent
from agents.state import AgentState
from agents.tools import example_tool
from db.base import Base
from db.models import TenderEvent


@pytest.mark.asyncio
async def test_agent_invokes_tenant_scoped_tool_and_traces_child_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            db.add_all(
                [
                    TenderEvent(
                        tenant_id="tenant-a",
                        event_id="event-a",
                        sender_entity_id="sender-a",
                        tender_ref="T-A",
                        project_name="Bridge upgrade",
                        source_revision="1",
                        stage="planning",
                        occurred_at=datetime.now(timezone.utc),
                        material_categories=["steel"],
                        source_type="manual",
                        data_provenance="test",
                    ),
                    TenderEvent(
                        tenant_id="tenant-b",
                        event_id="event-b",
                        sender_entity_id="sender-b",
                        tender_ref="T-B",
                        project_name="Bridge upgrade confidential",
                        source_revision="1",
                        stage="planning",
                        occurred_at=datetime.now(timezone.utc),
                        material_categories=["steel"],
                        source_type="manual",
                        data_provenance="test",
                    ),
                ]
            )
            await db.commit()
        monkeypatch.setattr(example_tool, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(tender_operations_agent, "get_system_prompt", lambda _: "Use tools when needed.")

        class FakeModel:
            def __init__(self) -> None:
                self.turns = 0
                self.bound_tools: list[Any] = []
                self.tool_result: str | None = None

            def bind_tools(self, tools: list[Any]) -> FakeModel:
                self.bound_tools = tools
                return self

            async def ainvoke(self, messages: list[Any]) -> AIMessage:
                self.turns += 1
                if self.turns == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_tenders",
                                "args": {"query": "Bridge"},
                                "id": "test-call-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                tool_message = next(message for message in messages if isinstance(message, ToolMessage))
                self.tool_result = str(tool_message.content)
                return AIMessage(content="I found the Bridge upgrade tender.")

        model = FakeModel()
        monkeypatch.setattr(tender_operations_agent, "get_llm", lambda **_: model)
        state: AgentState = {
            "session_id": "test-session",
            "tenant_id": "tenant-a",
            "messages": [{"role": "user", "content": "Find the Bridge tender"}],
            "collected": {},
            "current_step": "start",
            "step_status": "in_progress",
            "turn_count": 0,
        }

        result = await tender_operations_agent.tender_operations_agent_node(state)

        assert {agent_tool.name for agent_tool in model.bound_tools} == {
            "search_tenders",
            "list_enabled_connectors",
            "list_routing_rules",
        }
        assert model.turns == 2
        assert model.tool_result is not None
        assert "Bridge upgrade" in model.tool_result
        assert "confidential" not in model.tool_result
        assert result["messages"][-1]["content"] == "I found the Bridge upgrade tender."

        spans = exporter.get_finished_spans()
        agent_span = next(
            span for span in spans
            if span.name == "rpg_foresight.agent.tender_operations"
        )
        tool_span = next(span for span in spans if span.name == "rpg_foresight.tool.search_tenders")
        assert tool_span.context.trace_id == agent_span.context.trace_id
        assert tool_span.parent.span_id == agent_span.context.span_id
        assert tool_span.attributes["openinference.span.kind"] == "TOOL"
        assert tool_span.attributes["tool.name"] == "search_tenders"
        assert tool_span.attributes["rpg_foresight.result_count"] == 1
    finally:
        await engine.dispose()
        provider.shutdown()
