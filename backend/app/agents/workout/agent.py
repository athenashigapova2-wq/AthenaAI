"""Workout specialist entry point."""

from app.agents.prompts import WORKOUT_SYSTEM
from app.agents.state import AgentState
from app.tools.registry import build_tools


def workout_node(state: AgentState) -> dict:
    from app.agents.specialists import _invoke_tool_agent

    return _invoke_tool_agent(
        state,
        WORKOUT_SYSTEM,
        build_tools(state["user_id"], domains=("profile", "workout")),
    )
