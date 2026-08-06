"""Specialist agents with their own tool sets and system prompts."""

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agents.prompts import GENERAL_SYSTEM, NUTRITION_SYSTEM, RECOVERY_SYSTEM, WORKOUT_SYSTEM
from app.agents.state import AgentState
from app.llm import get_llm
from app.tools.registry import build_tools

MAX_TOOL_STEPS = 6


def _invoke_tool_agent(state: AgentState, system_prompt: str, tools: list[BaseTool]) -> dict:
    tools_by_name = {tool.name: tool for tool in tools}
    llm = get_llm().bind_tools(tools, tool_choice="auto") if tools else get_llm()
    messages = [SystemMessage(content=system_prompt), *state["messages"]]

    for _ in range(MAX_TOOL_STEPS):
        ai_msg = llm.invoke(messages)
        messages.append(ai_msg)
        if not getattr(ai_msg, "tool_calls", None):
            return {"messages": [ai_msg]}

        for call in ai_msg.tool_calls:
            tool = tools_by_name.get(call["name"])
            result = {"status": "error", "message": f"Unknown tool: {call['name']}"}
            if tool is not None:
                result = tool.invoke(call["args"])
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    return {"messages": [AIMessage(content="Я остановилась, чтобы не зациклиться на инструментах. Попробуй уточнить запрос.")]}


def nutrition_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, NUTRITION_SYSTEM, build_tools(state["user_id"], domains=("profile", "nutrition")))


def workout_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, WORKOUT_SYSTEM, build_tools(state["user_id"], domains=("profile", "workout")))


def recovery_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, RECOVERY_SYSTEM, build_tools(state["user_id"], domains=("profile", "recovery", "calendar")))


def general_node(state: AgentState) -> dict:
    response = get_llm().invoke([SystemMessage(content=GENERAL_SYSTEM), *state["messages"]])
    return {"messages": [response]}
