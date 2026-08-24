"""Recovery specialist entry point and progress context acquisition."""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from app.agents.common.tool_executor import _invoke_tool
from app.agents.nutrition.constraints import _requires_weight_trend
from app.agents.prompts import RECOVERY_SYSTEM
from app.agents.router import is_progress_request
from app.agents.state import AgentState
from app.tools.registry import build_tools


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _required_recovery_context(
    state: AgentState,
    tools_by_name: dict[str, BaseTool],
) -> tuple[list[SystemMessage], dict[str, Any]]:
    """Fetch the weight trend before answering any request about progress."""
    if not is_progress_request(_latest_user_text(state)):
        return [], {}

    required_names = ["get_weight_trend"]
    if _requires_weight_trend(_latest_user_text(state)):
        required_names.insert(0, "get_my_profile")
    results: dict[str, Any] = {}
    context: list[SystemMessage] = []
    for index, name in enumerate(required_names, start=1):
        result = _invoke_tool(
            state,
            {"name": name, "args": {}, "id": f"required-{name}"},
            tools_by_name,
            tool_step=index,
        )
        results[name] = result
        context.append(
            SystemMessage(
                content=(
                    f"REQUIRED_SERVER_FACT {name}: "
                    f"{json.dumps(result, ensure_ascii=False, default=str)}. "
                    "This fact was fetched by the server before answering. Use it "
                    "explicitly and do not contradict it."
                    + (
                        " When describing the trend duration, use its exact dates or "
                        "days field; do not relabel or round it."
                        if name == "get_weight_trend"
                        else ""
                    )
                )
            )
        )
    return context, results


def recovery_node(state: AgentState) -> dict:
    from app.agents.specialists import _invoke_tool_agent

    return _invoke_tool_agent(
        state,
        RECOVERY_SYSTEM,
        build_tools(state["user_id"], domains=("profile", "recovery", "calendar")),
    )
