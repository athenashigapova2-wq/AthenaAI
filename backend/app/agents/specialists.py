"""Specialist agents with their own tool sets and system prompts."""

from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agents.prompts import (
    GENERAL_SYSTEM,
    NUTRITION_SYSTEM,
    RECOVERY_SYSTEM,
    WORKOUT_SYSTEM,
    localized_system_prompt,
)
from app.agents.state import AgentState
from app.llm import get_llm
from app.services import agent_traces
from app.tools.registry import build_tools

MAX_TOOL_STEPS = 6


def _invoke_tool(
    state: AgentState,
    call: dict[str, Any],
    tools_by_name: dict[str, BaseTool],
) -> Any:
    """Invoke one tool and trace it when this graph turn has a run id."""
    tool = tools_by_name.get(call["name"])
    run_id = state.get("run_id")
    if tool is None:
        error = ValueError(f"Unknown tool: {call['name']}")
        if run_id is not None:
            tool_call_id = agent_traces.create_tool_call(
                run_id=run_id,
                tool_name=call["name"],
                tool_args=call["args"],
            )
            agent_traces.fail_tool_call(
                tool_call_id=tool_call_id,
                run_id=run_id,
                error=error,
                latency_ms=0,
            )
        return {"status": "error", "message": str(error)}

    if run_id is None:
        return tool.invoke(call["args"])

    tool_call_id = agent_traces.create_tool_call(
        run_id=run_id,
        tool_name=call["name"],
        tool_args=call["args"],
    )
    started_at = perf_counter()
    try:
        result = tool.invoke(call["args"])
    except Exception as exc:
        agent_traces.fail_tool_call(
            tool_call_id=tool_call_id,
            run_id=run_id,
            error=exc,
            latency_ms=agent_traces.elapsed_ms(started_at),
        )
        raise

    agent_traces.succeed_tool_call(
        tool_call_id=tool_call_id,
        run_id=run_id,
        tool_result=result,
        latency_ms=agent_traces.elapsed_ms(started_at),
    )
    return result


def _invoke_tool_agent(state: AgentState, system_prompt: str, tools: list[BaseTool]) -> dict:
    tools_by_name = {tool.name: tool for tool in tools}
    llm = get_llm().bind_tools(tools, tool_choice="auto") if tools else get_llm()
    localized_prompt = localized_system_prompt(system_prompt, state["locale"])
    messages = [SystemMessage(content=localized_prompt), *state["messages"]]

    for _ in range(MAX_TOOL_STEPS):
        ai_msg = llm.invoke(messages)
        messages.append(ai_msg)
        if not getattr(ai_msg, "tool_calls", None):
            return {"messages": [ai_msg]}

        for call in ai_msg.tool_calls:
            result = _invoke_tool(state, call, tools_by_name)
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    return {"messages": [AIMessage(content="Я остановилась, чтобы не зациклиться на инструментах. Попробуй уточнить запрос.")]}


def nutrition_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, NUTRITION_SYSTEM, build_tools(state["user_id"], domains=("profile", "nutrition")))


def workout_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, WORKOUT_SYSTEM, build_tools(state["user_id"], domains=("profile", "workout")))


def recovery_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, RECOVERY_SYSTEM, build_tools(state["user_id"], domains=("profile", "recovery", "calendar")))


def general_node(state: AgentState) -> dict:
    prompt = localized_system_prompt(GENERAL_SYSTEM, state["locale"])
    response = get_llm().invoke([SystemMessage(content=prompt), *state["messages"]])
    return {"messages": [response]}
