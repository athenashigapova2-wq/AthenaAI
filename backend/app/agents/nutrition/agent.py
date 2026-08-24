"""Nutrition specialist entry point and mandatory context acquisition."""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from app.agents.common.tool_executor import _invoke_tool
from app.agents.prompts import NUTRITION_SYSTEM
from app.agents.state import AgentState
from app.config import settings
from app.tools.registry import build_tools

from .constraints import _requires_full_day_plan, _requires_weight_trend


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _required_nutrition_context(
    state: AgentState,
    tools_by_name: dict[str, BaseTool],
) -> tuple[list[SystemMessage], dict[str, Any], bool]:
    """Fetch facts that must be present before specific nutrition advice."""
    message = _latest_user_text(state)
    if settings.llm_provider == "mock" and not _requires_weight_trend(message):
        return [], {}, False
    needs_plan_validation = _requires_full_day_plan(message)
    required_names: list[str] = []
    if needs_plan_validation:
        required_names.extend(("get_my_profile", "get_daily_intake"))
    if _requires_weight_trend(message):
        required_names.extend(("get_my_profile", "get_weight_trend"))

    results: dict[str, Any] = {}
    context: list[SystemMessage] = []
    for index, name in enumerate(dict.fromkeys(required_names)):
        result = _invoke_tool(
            state,
            {"name": name, "args": {}, "id": f"required-{name}"},
            tools_by_name,
            tool_step=index + 1,
        )
        results[name] = result
        context.append(
            SystemMessage(
                content=(
                    f"REQUIRED_SERVER_FACT {name}: "
                    f"{json.dumps(result, ensure_ascii=False, default=str)}. "
                    "This fact was fetched by the server for this request. Use it explicitly "
                    "and do not contradict it. Do not call the same tool again."
                    + (
                        " When describing the weight-trend duration, use its exact dates or "
                        "days field; do not relabel or round it to a week or month."
                        if name == "get_weight_trend"
                        else ""
                    )
                )
            )
        )

    return context, results, needs_plan_validation


def nutrition_node(state: AgentState) -> dict:
    from app.agents.specialists import _invoke_tool_agent

    return _invoke_tool_agent(
        state,
        NUTRITION_SYSTEM,
        build_tools(state["user_id"], domains=("profile", "nutrition", "recovery")),
    )
