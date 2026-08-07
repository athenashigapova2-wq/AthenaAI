"""LangGraph assembly for Athena's Router + specialist agent architecture."""

from typing import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agents.router import router_node
from app.agents.specialists import general_node, nutrition_node, recovery_node, workout_node
from app.agents.state import AgentName, AgentState


class AgentTurnResult(TypedDict):
    """Public result returned to delivery layers such as FastAPI."""

    answer: str
    route: AgentName


def _select_route(state: AgentState) -> str:
    return state.get("route", "general")


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("nutrition", nutrition_node)
    graph.add_node("workout", workout_node)
    graph.add_node("recovery", recovery_node)
    graph.add_node("general", general_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        _select_route,
        {"nutrition": "nutrition", "workout": "workout", "recovery": "recovery", "general": "general"},
    )
    for node in ("nutrition", "workout", "recovery", "general"):
        graph.add_edge(node, END)
    return graph.compile()


def run_agent_turn_details(user_id: str, message: str, locale: str = "ru") -> AgentTurnResult:
    """Run one graph turn and return the answer plus the selected specialist."""
    app = build_agent_graph()
    result = app.invoke({
        "user_id": user_id,
        "locale": locale,
        "messages": [HumanMessage(content=message)],
        "route": "general",
    })
    return {
        "answer": str(result["messages"][-1].content),
        "route": result.get("route", "general"),
    }


def run_agent_turn(user_id: str, message: str, locale: str = "ru") -> str:
    """Backward-compatible text-only entry point for existing scripts."""
    return run_agent_turn_details(user_id, message, locale)["answer"]
