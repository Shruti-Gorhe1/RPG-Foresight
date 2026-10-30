"""Connector runner node — executes all registered connectors."""
from __future__ import annotations

from agents.state import AgentState
from observability.tracing import traced_span
from shared.logger import get_logger

log = get_logger("agents.connector_runner")


@traced_span("rpg_foresight.agent.connector_runner")
async def connector_runner_node(state: AgentState) -> AgentState:
    """Run all enabled connectors and collect raw + normalized results."""
    from agents.tools.sync_pipeline_tools import run_enabled_connectors

    collected = state.setdefault("collected", {})
    ingestion = collected.setdefault("ingestion", {})

    # Get existing event IDs for deduplication
    existing_ids = ingestion.get("existing_event_ids", set())
    if not isinstance(existing_ids, set):
        existing_ids = set()

    # Identify connectors to run (enabled ones).
    connectors = [
        connector_id
        for connector_id in ingestion.get("connector_ids", [])
    ]
    if not connectors:
        log.warning("no_connectors_enabled")
        ingestion["connectors_identified"] = True
        ingestion["connectors_run"] = True
        ingestion["connector_results"] = {}
        ingestion["total_fetched"] = 0
        ingestion["total_normalized"] = 0
        state["step_status"] = "completed"
        return state

    ingestion["connectors_identified"] = True
    ingestion["connectors_list"] = connectors

    results = await run_enabled_connectors(existing_ids)

    # Store results
    run_results = {}
    total_fetched = 0
    total_normalized = 0
    all_errors = []

    for conn_id, result in results.items():
        run_results[conn_id] = {
            "source_name": result.source_name,
            "records": result.records,
            "errors": result.errors,
            "count": len(result.records),
        }
        total_fetched += len(result.records)
        total_normalized += len(result.records)
        all_errors.extend(result.errors)

    ingestion["connectors_run"] = True
    ingestion["connector_results"] = run_results
    ingestion["total_fetched"] = total_fetched
    ingestion["total_normalized"] = total_normalized
    ingestion["errors"] = all_errors

    log.info(
        "connector_runner.completed",
        connectors=len(connectors),
        total_fetched=total_fetched,
        total_normalized=total_normalized,
    )

    state["step_status"] = "completed"
    return state