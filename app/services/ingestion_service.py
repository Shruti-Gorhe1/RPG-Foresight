"""Ingestion service — orchestrates the agentic ingestion pipeline.

Can be triggered via API endpoint or background worker. Uses the LangGraph
supervisor pattern nodes directly for deterministic, observable execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.graph import compiled_graph
from agents.state import AgentState
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("services.ingestion")


@traced_span("rpg_foresight.agent.sync_signal_supervisor")
async def _run_sync_signal_graph(state: AgentState) -> AgentState:
    """Run the full Sync Signals supervisor/specialist graph."""
    return await compiled_graph.ainvoke(state)


@traced_span("rpg_foresight.ingestion.run")
async def run_ingestion_pipeline() -> dict[str, Any]:
    """Run Sync Signals through the supervisor-led agent graph.

    The supervisor coordinates connector discovery, source ingestion, database
    persistence, and routing as separate specialist-agent handoffs.
    """
    state: AgentState = {
        "session_id": f"ingestion-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "messages": [],
        "current_step": "start",
        "step_status": "in_progress",
        "turn_count": 0,
        "collected": {"ingestion": {}},
    }

    state = await _run_sync_signal_graph(state)

    collected = state.get("collected", {})
    ingestion = collected.get("ingestion", {})
    routing_summary = ingestion.get("routing", {})
    summary = {
        "status": state.get("step_status", "unknown"),
        "steps": ingestion.get("steps", 0),
        "connectors_run": ingestion.get("connector_count", 0),
        "connector_ids": ingestion.get("connector_ids", []),
        "total_fetched": ingestion.get("total_fetched", 0),
        "total_normalized": ingestion.get("total_normalized", 0),
        "total_created": ingestion.get("total_created", 0),
        "errors": ingestion.get("errors", []),
        "connector_results": ingestion.get("connector_results", {}),
        "routing": routing_summary,
    }

    log.info("ingestion_pipeline.completed", **summary)

    if routing_summary.get("status") not in {"completed", "skipped"}:
        summary["status"] = "failed"
        reason = routing_summary.get("error") or routing_summary.get("reason") or "unknown"
        summary["errors"].append(f"routing_{routing_summary['status']}: {reason}")
    elif routing_summary.get("deliveries_failed", 0):
        summary["status"] = "failed"
        summary["errors"].append(
            f"{routing_summary['deliveries_failed']} notification delivery attempt(s) failed"
        )

    return summary