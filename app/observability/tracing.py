"""OpenTelemetry + Arize Phoenix tracing initialisation.

Cloud Phoenix (ACA-hosted):
- Collector endpoint via PHOENIX_COLLECTOR_ENDPOINT
  (e.g. https://zaf-phoenix.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io/v1/traces)
- Auth: Bearer token from ARIZE_PHOENIX_API_KEY

Arize AX also requires ARIZE_SPACE_ID when exporting to its collector.

Local fallback: http://<phoenix_host>:<phoenix_port>/v1/traces (no auth).

Uses the OTLP/HTTP exporter + openinference instrumentors so LangChain /
LangGraph / OpenAI calls appear as proper spans in Phoenix. All imports are
lazy so a missing observability package never blocks app startup.
"""
from __future__ import annotations

import logging
import inspect
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator, TypeVar, cast
from urllib.parse import urlsplit

import truststore

from shared.config import get_settings

truststore.inject_into_ssl()

log = logging.getLogger("tracing")

_INITIALISED = False
_Function = TypeVar("_Function", bound=Callable[..., Any])


def _is_local_collector(endpoint: str) -> bool:
    hostname = (urlsplit(endpoint).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _flush_pursuit_trace(span_name: str) -> None:
    if span_name != "rpg_foresight.pursuit.analyze":
        return
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        force_flush = getattr(provider, "force_flush", None)
        if not callable(force_flush):
            log.warning("Phoenix trace flush skipped: no configured TracerProvider")
            return
        flushed = force_flush(timeout_millis=5_000)
        if flushed is False:
            log.error("Phoenix trace flush timed out for pursuit assessment")
    except Exception:  # noqa: BLE001
        log.exception("Phoenix trace flush failed for pursuit assessment")


def traced_span(span_name: str) -> Callable[[_Function], _Function]:
    """Create a named span around a synchronous or asynchronous operation."""
    def decorate(function: _Function) -> _Function:
        def annotate_result(span: Any, result: Any) -> None:
            if ".tool." in span_name:
                span.set_attribute("tool.name", span_name.rsplit(".", 1)[-1])
                if isinstance(result, list):
                    span.set_attribute("rpg_foresight.result_count", len(result))
                elif isinstance(result, str):
                    span.set_attribute("rpg_foresight.tool.selected_action", result)
                elif isinstance(result, bool):
                    span.set_attribute("rpg_foresight.tool.success", result)
            result_status = getattr(result, "status", None)
            if isinstance(result, dict):
                for key in ("status", "step_status", "connectors_run", "total_created"):
                    value = result.get(key)
                    if isinstance(value, (str, int, float, bool)):
                        span.set_attribute(f"rpg_foresight.{key}", value)
                routing = result.get("routing")
                if isinstance(routing, dict):
                    for key in (
                        "events_evaluated",
                        "rules_applied",
                        "deliveries_created",
                        "deliveries_sent",
                        "deliveries_failed",
                    ):
                        value = routing.get(key)
                        if isinstance(value, (int, float, bool)):
                            span.set_attribute(f"rpg_foresight.routing.{key}", value)
                result_status = result.get("status", result.get("step_status", result_status))
            if isinstance(result_status, str):
                span.set_attribute("rpg_foresight.result", result_status)
                if result_status in {"failed", "error"}:
                    from opentelemetry.trace import Status, StatusCode

                    span.set_status(Status(StatusCode.ERROR))

        @contextmanager
        def start_span() -> Iterator[Any]:
            from opentelemetry import trace

            tracer = trace.get_tracer("rpg-foresight")
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("rpg_foresight.operation", span_name)
                span_kind = (
                    "TOOL" if ".tool." in span_name
                    else "LLM" if ".llm." in span_name
                    else "AGENT" if ".agent." in span_name
                    else "DECISION" if ".decision." in span_name
                    else "CHAIN"
                )
                span.set_attribute(
                    "openinference.span.kind",
                    span_kind,
                )
                if ".agent." in span_name:
                    span.set_attribute("agent.name", span_name.rsplit(".", 1)[-1])
                if ".llm." in span_name:
                    span.set_attribute("llm.system", "configured-chat-model")
                yield span

        if inspect.iscoroutinefunction(function):
            @wraps(function)
            async def wrapped_async(*args: Any, **kwargs: Any) -> Any:
                from opentelemetry.trace import Status, StatusCode

                try:
                    with start_span() as span:
                        try:
                            result = await function(*args, **kwargs)
                        except Exception as exc:
                            span.record_exception(exc)
                            span.set_status(Status(StatusCode.ERROR))
                            raise
                        annotate_result(span, result)
                        return result
                finally:
                    _flush_pursuit_trace(span_name)

            return cast(_Function, wrapped_async)

        @wraps(function)
        def wrapped_sync(*args: Any, **kwargs: Any) -> Any:
            from opentelemetry.trace import Status, StatusCode

            try:
                with start_span() as span:
                    try:
                        result = function(*args, **kwargs)
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR))
                        raise
                    annotate_result(span, result)
                    return result
            finally:
                _flush_pursuit_trace(span_name)

        return cast(_Function, wrapped_sync)

    return decorate


def init_tracing(service_name: str = "__APP_NAME__-backend") -> None:
    """Configure the OTel TracerProvider and instrument FastAPI + LangChain + OpenAI.

    ``service_name`` identifies which process emitted a span (the FastAPI API
    vs. the Temporal worker) — both write to the same Phoenix project, but this
    lets you tell the two execution paths apart in a trace.
    """
    global _INITIALISED
    if _INITIALISED:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        settings = get_settings()

        if settings.phoenix_collector_endpoint:
            endpoint = settings.phoenix_collector_endpoint.rstrip("/")
            if not endpoint.endswith("/v1/traces"):
                endpoint = f"{endpoint}/v1/traces"
        else:
            endpoint = f"http://{settings.phoenix_host}:{settings.phoenix_port}/v1/traces"

        headers = {}
        if not _is_local_collector(endpoint):
            if settings.arize_phoenix_api_key:
                headers["authorization"] = settings.arize_phoenix_api_key
                headers["api_key"] = settings.arize_phoenix_api_key
            if settings.arize_space_id:
                headers["arize-space-id"] = settings.arize_space_id
                headers["space_id"] = settings.arize_space_id
            if settings.arize_phoenix_api_key and settings.arize_space_id:
                headers["arize-interface"] = "otel"

        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "openinference.project.name": settings.phoenix_project_name,
                }
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
        )
        trace.set_tracer_provider(provider)

        # ── Instrumentors (each optional) ──────────────────────────────────────
        try:
            from openinference.instrumentation.langchain import LangChainInstrumentor

            LangChainInstrumentor().instrument(tracer_provider=provider)
            log.info("LangChain instrumented (openinference)")
        except Exception as exc:  # noqa: BLE001
            log.warning("langchain instrumentation skipped: %s", exc)

        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor

            OpenAIInstrumentor().instrument(tracer_provider=provider)
            log.info("OpenAI instrumented (openinference)")
        except Exception as exc:  # noqa: BLE001
            log.warning("openai instrumentation skipped: %s", exc)

        log.info("OTel TracerProvider initialised -> %s (project: %s)",
                 endpoint, settings.phoenix_project_name)
        _INITIALISED = True
    except Exception as exc:  # noqa: BLE001
        log.warning("init_tracing failed (continuing without tracing): %s", exc)


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI app instance (call after app creation)."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        log.info("FastAPI instrumented")
    except Exception as exc:  # noqa: BLE001
        log.warning("fastapi instrumentation skipped: %s", exc)
