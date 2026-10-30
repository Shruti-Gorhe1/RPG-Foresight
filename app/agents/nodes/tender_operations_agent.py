"""Tender Operations agent node for tenant-scoped tender assistance.

The node uses local or configured chat inference, invokes read-only domain
tools as needed, and returns its response to the supervisor.
"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.state import AgentState
from agents.tools.example_tool import create_agent_tools
from observability.tracing import traced_span
from shared.llm import get_llm
from shared.logger import get_logger
from shared.prompt_loader import get_system_prompt

log = get_logger("agents.tender_operations_agent")
_MAX_TOOL_ROUNDS = 3


@traced_span("rpg_foresight.agent.tender_operations")
async def tender_operations_agent_node(state: AgentState) -> AgentState:
    user_msg = ""
    for m in reversed(state.get("messages", [])):
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    system = get_system_prompt("tender_operations_agent") or "You are a helpful assistant."
    tenant_id = state.get("tenant_id", "")
    if not tenant_id:
        raise RuntimeError("The Tender Operations agent requires an authenticated tenant.")
    tools = create_agent_tools(tenant_id)
    tools_by_name = {tool.name: tool for tool in tools}
    model = get_llm(max_tokens=512).bind_tools(tools)
    conversation = [SystemMessage(content=system), HumanMessage(content=user_msg)]

    for tool_round in range(_MAX_TOOL_ROUNDS + 1):
        response = await model.ainvoke(conversation)
        conversation.append(response)
        if not response.tool_calls:
            break
        if tool_round == _MAX_TOOL_ROUNDS:
            raise RuntimeError(
                f"The tender operations agent exceeded its {_MAX_TOOL_ROUNDS}-round tool limit."
            )
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            if tool_name not in tools_by_name:
                raise RuntimeError(f"The model requested an unavailable tool: {tool_name}.")
            result = await tools_by_name[tool_name].ainvoke(tool_call["args"])
            content = result if isinstance(result, str) else json.dumps(result, default=str)
            conversation.append(
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call["id"],
                    name=tool_name,
                )
            )
    else:
        raise RuntimeError("The tender operations agent did not complete its model turn.")

    if not isinstance(response.content, str) or not response.content.strip():
        raise RuntimeError("The tender operations agent received an empty or non-text model response.")
    reply = response.content.strip()

    state.setdefault("collected", {})["tender_operations_result"] = reply
    state.setdefault("messages", []).append(
        {"role": "assistant", "agent": "tender_operations_agent", "content": reply}
    )
    state["current_step"] = "tender_operations_agent"
    state["step_status"] = "completed"
    log.info("tender_operations_agent.done", session_id=state.get("session_id"))
    return state
