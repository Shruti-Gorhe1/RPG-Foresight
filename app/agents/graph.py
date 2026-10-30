"""LangGraph supervisor graph — accelerator baseline.

Flow: guardrails -> supervisor -> (conditional) specialist -> supervisor -> ...
until a terminal node (respond_and_wait / human_review complete / error).

Add a specialist by: (1) writing a node in agents/nodes/, (2) registering it
below with add_node, (3) adding it to the supervisor's next_agent() router and
the conditional-edge map, and (4) looping it back to the supervisor.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.guardrails import guardrails_node
from agents.human_in_loop import human_review_node
from agents.nodes.connector_runner import connector_runner_node
from agents.nodes.db_writer import db_writer_node
from agents.nodes.tender_operations_agent import tender_operations_agent_node
from agents.nodes.identify_connectors import identify_connectors_node
from agents.nodes.ingestion_error_handler import ingestion_error_handler_node
from agents.nodes.ingestion_supervisor import ingestion_supervisor_node, next_ingestion_agent
from agents.nodes.private_pipeline_signal_agent import private_pipeline_signal_agent_node
from agents.nodes.route_signals_agent import route_signals_agent_node
from agents.nodes.supervisor import next_agent, supervisor_node
from agents.state import AgentState


def _respond_and_wait_node(state: AgentState) -> AgentState:
    """Terminal: the turn is done — return control to the user."""
    return state


def _error_node(state: AgentState) -> AgentState:
    state["step_status"] = "failed"
    return state


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    g.add_node("guardrails", guardrails_node)
    g.add_node("supervisor", supervisor_node)
    g.add_node("tender_operations_agent", tender_operations_agent_node)
    g.add_node("private_pipeline_signal_agent", private_pipeline_signal_agent_node)
    g.add_node("human_review", human_review_node)
    g.add_node("respond_and_wait", _respond_and_wait_node)
    g.add_node("error_handler", _error_node)

    # ── Ingestion pipeline nodes (Section 4 of the workflow doc) ──────────────
    g.add_node("ingestion_supervisor", ingestion_supervisor_node)
    g.add_node("identify_connectors", identify_connectors_node)
    g.add_node("run_connectors", connector_runner_node)
    g.add_node("write_results", db_writer_node)
    g.add_node("route_signals", route_signals_agent_node)
    g.add_node("ingestion_error_handler", ingestion_error_handler_node)

    # ── Entry ─────────────────────────────────────────────────────────────────
    g.set_entry_point("guardrails")
    g.add_edge("guardrails", "supervisor")

    # ── Supervisor conditional routing ────────────────────────────────────────
    g.add_conditional_edges(
        "supervisor",
        next_agent,
        {
            "tender_operations_agent": "tender_operations_agent",
            "private_pipeline_signal_agent": "private_pipeline_signal_agent",
            "human_review": "human_review",
            "ingestion_supervisor": "ingestion_supervisor",
            "respond_and_wait": "respond_and_wait",
            "error_handler": "error_handler",
        },
    )

    # ── Ingestion supervisor conditional routing ──────────────────────────────
    g.add_conditional_edges(
        "ingestion_supervisor",
        next_ingestion_agent,
        {
            "identify_connectors": "identify_connectors",
            "run_connectors": "run_connectors",
            "write_results": "write_results",
            "route_signals": "route_signals",
            "ingestion_error_handler": "ingestion_error_handler",
            "respond_and_wait": "respond_and_wait",
        },
    )

    # ── Specialists loop back to their supervisor ─────────────────────────────
    for node in ("tender_operations_agent", "private_pipeline_signal_agent", "error_handler"):
        g.add_edge(node, "supervisor")
    for node in (
        "identify_connectors",
        "run_connectors",
        "write_results",
        "route_signals",
        "ingestion_error_handler",
    ):
        g.add_edge(node, "ingestion_supervisor")

    # ── Terminal nodes ────────────────────────────────────────────────────────
    g.add_edge("human_review", END)
    g.add_edge("respond_and_wait", END)
    return g


compiled_graph = build_graph().compile()
