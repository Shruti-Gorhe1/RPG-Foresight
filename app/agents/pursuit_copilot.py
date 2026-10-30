"""LangGraph workflow for the live, model-backed pursuit specialists."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.pursuit.action_planner_agent import action_planner_agent
from agents.pursuit.document_agent import document_agent
from agents.pursuit.qualification_agent import qualification_agent
from agents.pursuit.risk_agent import risk_agent
from agents.pursuit.state import PursuitState
from agents.pursuit.supervisor import pursuit_supervisor_agent


def build_pursuit_graph():
    graph = StateGraph(PursuitState)
    graph.add_node("pursuit_supervisor", pursuit_supervisor_agent)
    graph.add_node("qualification_agent", qualification_agent)
    graph.add_node("document_agent", document_agent)
    graph.add_node("risk_agent", risk_agent)
    graph.add_node("action_planner_agent", action_planner_agent)
    graph.set_entry_point("pursuit_supervisor")
    graph.add_edge("pursuit_supervisor", "qualification_agent")
    graph.add_edge("qualification_agent", "document_agent")
    graph.add_edge("document_agent", "risk_agent")
    graph.add_edge("risk_agent", "action_planner_agent")
    graph.add_edge("action_planner_agent", END)
    return graph.compile()


pursuit_graph = build_pursuit_graph()
