from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import observability.tracing as tracing
from agents.graph import compiled_graph
from agents.nodes import tender_operations_agent
from agents.state import AgentState


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:6006/v1/traces",
        "http://127.0.0.1:6006/v1/traces",
        "http://[::1]:6006/v1/traces",
    ],
)
def test_local_phoenix_collector_is_detected(endpoint: str) -> None:
    assert tracing._is_local_collector(endpoint)


def test_remote_phoenix_collector_is_not_local() -> None:
    assert not tracing._is_local_collector("https://phoenix.example.com/v1/traces")


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    yield exporter
    provider.shutdown()


def test_traced_span_records_sync_result(span_exporter: InMemorySpanExporter) -> None:
    @tracing.traced_span("test.sync_agent")
    def run_agent() -> dict[str, object]:
        return {"step_status": "completed", "total_created": 3}

    assert run_agent()["step_status"] == "completed"
    span = span_exporter.get_finished_spans()[0]
    assert span.name == "test.sync_agent"
    assert span.attributes["rpg_foresight.step_status"] == "completed"
    assert span.attributes["rpg_foresight.total_created"] == 3


@pytest.mark.asyncio
async def test_traced_span_records_async_errors(span_exporter: InMemorySpanExporter) -> None:
    @tracing.traced_span("test.async_agent")
    async def run_agent() -> None:
        raise RuntimeError("expected test failure")

    with pytest.raises(RuntimeError, match="expected test failure"):
        await run_agent()

    span = span_exporter.get_finished_spans()[0]
    assert span.name == "test.async_agent"
    assert span.status.status_code == StatusCode.ERROR
    assert any(event.name == "exception" for event in span.events)


@pytest.mark.asyncio
async def test_tender_operations_agent_calls_configured_model(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tender_operations_agent, "get_system_prompt", lambda _: "Answer helpfully.")
    monkeypatch.setattr(
        tender_operations_agent,
        "get_llm",
        lambda **_: SimpleNamespace(
            bind_tools=lambda tools: SimpleNamespace(
                ainvoke=lambda messages: _async_response("A real model response")
            )
        ),
    )
    state: AgentState = {
        "session_id": "test-session",
        "tenant_id": "test-tenant",
        "messages": [{"role": "user", "content": "Hello"}],
        "collected": {},
        "current_step": "start",
        "step_status": "in_progress",
        "turn_count": 0,
    }

    result = await tender_operations_agent.tender_operations_agent_node(state)

    assert result["messages"][-1]["content"] == "A real model response"
    assert span_exporter.get_finished_spans()[0].name == "rpg_foresight.agent.tender_operations"


@pytest.mark.asyncio
async def test_tender_operations_agent_requires_authenticated_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tender_operations_agent, "get_system_prompt", lambda _: "Answer helpfully.")
    state: AgentState = {
        "session_id": "test-session",
        "messages": [{"role": "user", "content": "Hello"}],
        "collected": {},
        "current_step": "start",
        "step_status": "in_progress",
        "turn_count": 0,
    }

    with pytest.raises(RuntimeError, match="authenticated tenant"):
        await tender_operations_agent.tender_operations_agent_node(state)


@pytest.mark.asyncio
async def test_langgraph_run_records_each_agent_span(
    span_exporter: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tender_operations_agent, "get_system_prompt", lambda _: "Answer helpfully.")
    monkeypatch.setattr(
        tender_operations_agent,
        "get_llm",
        lambda **_: SimpleNamespace(
            bind_tools=lambda tools: SimpleNamespace(
                ainvoke=lambda messages: _async_response("A real model response")
            )
        ),
    )
    result = await compiled_graph.ainvoke(
        {
            "session_id": "test-session",
            "tenant_id": "test-tenant",
            "messages": [{"role": "user", "content": "Hello"}],
            "collected": {},
            "current_step": "start",
            "step_status": "in_progress",
            "turn_count": 0,
        }
    )

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    assert result["messages"][-1]["content"] == "A real model response"
    assert {
        "rpg_foresight.agent.guardrails",
        "rpg_foresight.agent.supervisor",
        "rpg_foresight.agent.tender_operations",
    }.issubset(span_names)


async def _async_response(content: str) -> AIMessage:
    return AIMessage(content=content)
