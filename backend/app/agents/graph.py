"""LangGraph assembly for Athena's Router + specialist agent architecture."""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agents.router import router_node
from app.agents.specialists import general_node, nutrition_node, recovery_node, workout_node
from app.agents.state import AgentState


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


def run_agent_turn(user_id: str, message: str, locale: str = "ru") -> str:
    """Convenience entry point for scripts and the future FastAPI route."""
    app = build_agent_graph()
    result = app.invoke({
        "user_id": user_id,
        "locale": locale,
        "messages": [HumanMessage(content=message)],
        "route": "general",
    })
    return str(result["messages"][-1].content)
