"""Orchestration shared by the specialist agents.

Domain policy belongs in the route packages. This module coordinates model calls,
tool loops, tracing, and the general fallback agent.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from app.ai_execution import ai_execution_service
from app.agents.common.response_pipeline import _finalize_answer, _weight_trend_evidence
from app.agents.common.tool_executor import _invoke_tool
from app.agents.nutrition.agent import _required_nutrition_context, nutrition_node
from app.agents.nutrition.calorie_policy import _calorie_decision_tool
from app.agents.nutrition.constraints import _requires_weight_trend
from app.agents.nutrition.planner import _plan_submission_tool
from app.agents.nutrition_validation import (
    targets_from_profile_result,
    validation_failure_message,
)
from app.agents.prompts import GENERAL_SYSTEM, localized_system_prompt
from app.agents.recovery.agent import _required_recovery_context, recovery_node
from app.agents.state import AgentState
from app.agents.workout.agent import workout_node

MAX_TOOL_STEPS = 6
MAX_PLAN_SUBMISSIONS = 8


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _rag_messages(state: AgentState) -> list[SystemMessage]:
    context = state.get("rag_context", "")
    return [SystemMessage(content=context)] if context else []


def _memory_messages(state: AgentState) -> list[SystemMessage]:
    context = state.get("memory_context", "")
    return [SystemMessage(content=context)] if context else []


def _invoke_tool_agent(
    state: AgentState,
    system_prompt: str,
    tools: list[BaseTool],
) -> dict:
    """Run the shared bounded tool loop for one specialist route."""
    tools_by_name = {tool.name: tool for tool in tools}
    prepared = ai_execution_service.prepare(
        node_name=state["route"],
        purpose="tool_planning_or_answer",
        default_tier="main",
    )
    base_llm = prepared.model
    localized_prompt = localized_system_prompt(system_prompt, state["locale"])
    required_context: list[SystemMessage] = []
    required_results: dict[str, object] = {}
    needs_plan_validation = False
    needs_calorie_decision = _requires_weight_trend(_latest_user_text(state))

    if state["route"] == "nutrition":
        required_context, required_results, needs_plan_validation = (
            _required_nutrition_context(state, tools_by_name)
        )
    elif state["route"] == "recovery":
        required_context, required_results = _required_recovery_context(
            state,
            tools_by_name,
        )

    calorie_tool: StructuredTool | None = None
    submission_tool: StructuredTool | None = None
    if needs_calorie_decision and not needs_plan_validation:
        calorie_tool = _calorie_decision_tool(
            required_results.get("get_my_profile"),
            required_results.get("get_weight_trend"),
            state["locale"],
        )
        tools_by_name[calorie_tool.name] = calorie_tool
        llm = base_llm.bind_tools([calorie_tool], tool_choice=calorie_tool.name)
    elif needs_plan_validation:
        profile_result = required_results.get("get_my_profile")
        submission_tool = _plan_submission_tool(
            targets_from_profile_result(profile_result),
            state["locale"],
            profile_result,
        )
        tools_by_name[submission_tool.name] = submission_tool
        llm = base_llm.bind_tools(
            [submission_tool],
            tool_choice=submission_tool.name,
        )
    else:
        remaining_tools = [
            tool for tool in tools if tool.name not in required_results
        ]
        llm = (
            base_llm.bind_tools(remaining_tools, tool_choice="auto")
            if remaining_tools
            else base_llm
        )

    system_parts = [localized_prompt]
    system_parts.extend(str(message.content) for message in required_context)
    if submission_tool is not None:
        system_parts.append(submission_tool.description)
    if calorie_tool is not None:
        system_parts.append(calorie_tool.description)
    system_parts.extend(str(message.content) for message in _rag_messages(state))
    system_parts.extend(str(message.content) for message in _memory_messages(state))
    messages = [
        SystemMessage(content="\n\n".join(system_parts)),
        *state["messages"],
    ]

    max_steps = MAX_PLAN_SUBMISSIONS if needs_plan_validation else MAX_TOOL_STEPS
    for tool_step in range(1, max_steps + 1):
        ai_msg = ai_execution_service.invoke_prepared(
            prepared,
            messages=messages,
            run_id=state.get("trace_id"),
            model=llm,
        )
        messages.append(ai_msg)
        if not getattr(ai_msg, "tool_calls", None):
            if needs_plan_validation or calorie_tool is not None:
                return {
                    "messages": [
                        AIMessage(content=validation_failure_message(state["locale"]))
                    ],
                    "resolution_mode": "fallback",
                }
            evidence = _weight_trend_evidence(
                required_results.get("get_weight_trend"),
                state["locale"],
            )
            finalized = _finalize_answer(
                ai_msg.content,
                state["locale"],
                required_results.get("get_weight_trend"),
            )
            if evidence:
                finalized = f"{evidence}\n\n{finalized}".strip()
            return {
                "messages": [AIMessage(content=finalized)],
                "resolution_mode": "main_llm",
            }

        for call in ai_msg.tool_calls:
            result = _invoke_tool(state, call, tools_by_name, tool_step=tool_step)
            if (
                call["name"] == "submit_daily_nutrition_plan"
                and isinstance(result, dict)
                and result.get("status") == "ok"
            ):
                return {
                    "messages": [
                        AIMessage(
                            content=_finalize_answer(result["answer"], state["locale"])
                        )
                    ],
                    "resolution_mode": "main_llm",
                }
            if (
                call["name"] == "submit_calorie_decision"
                and isinstance(result, dict)
                and result.get("status") == "ok"
            ):
                evidence = _weight_trend_evidence(
                    required_results.get("get_weight_trend"),
                    state["locale"],
                )
                answer = _finalize_answer(result["answer"], state["locale"])
                if evidence:
                    answer = f"{evidence}\n\n{answer}".strip()
                return {
                    "messages": [AIMessage(content=answer)],
                    "resolution_mode": "main_llm",
                    "calorie_decision": result["calorie_decision"],
                }
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=call["id"],
                )
            )

    return {
        "messages": [
            AIMessage(
                content=(
                    "Я остановилась, чтобы не зациклиться на инструментах. "
                    "Попробуйте уточнить запрос."
                )
            )
        ],
        "resolution_mode": "fallback",
    }


def general_node(state: AgentState) -> dict:
    prompt = localized_system_prompt(GENERAL_SYSTEM, state["locale"])
    response = ai_execution_service.invoke(
        messages=[
            SystemMessage(content=prompt),
            *_memory_messages(state),
            *_rag_messages(state),
            *state["messages"],
        ],
        node_name="general",
        purpose="answer",
        run_id=state.get("trace_id"),
        default_tier="main",
    )
    return {
        "messages": [
            AIMessage(content=_finalize_answer(response.content, state["locale"]))
        ],
        "resolution_mode": "main_llm",
    }


__all__ = [
    "general_node",
    "nutrition_node",
    "recovery_node",
    "workout_node",
]

