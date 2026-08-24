"""LangGraph assembly for Athena's Router + specialist agent architecture."""

from functools import lru_cache
from typing import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.agents.router import router_node
from app.agents.retrieval import retriever_node
from app.agents.nutrition.agent import nutrition_node
from app.agents.recovery.agent import recovery_node
from app.agents.specialists import general_node
from app.agents.workout.agent import workout_node
from app.agents.state import AgentName, AgentState, ResolutionMode
from app.config import settings


class AgentTurnResult(TypedDict):
    """Public result returned to delivery layers such as FastAPI."""

    answer: str
    route: AgentName
    resolution_mode: ResolutionMode
    calorie_decision: dict[str, object] | None
    routing_fallback_reason: str | None


def _select_route(state: AgentState) -> str:
    return state.get("route", "general")


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("nutrition", nutrition_node)
    graph.add_node("workout", workout_node)
    graph.add_node("recovery", recovery_node)
    graph.add_node("general", general_node)

    graph.add_edge(START, "router")
    graph.add_edge("router", "retriever")
    graph.add_conditional_edges(
        "retriever",
        _select_route,
        {"nutrition": "nutrition", "workout": "workout", "recovery": "recovery", "general": "general"},
    )
    for node in ("nutrition", "workout", "recovery", "general"):
        graph.add_edge(node, END)
    return graph.compile()


@lru_cache(maxsize=1)
def get_agent_graph():
    """Return the process-wide compiled graph shared by all agent turns."""
    return build_agent_graph()


def run_agent_turn_details(
    user_id: str,
    message: str,
    locale: str = "ru",
    run_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> AgentTurnResult:
    """Run one graph turn and return the answer plus the selected specialist."""
    app = get_agent_graph()
    prior_messages: list[BaseMessage] = []
    for item in history or []:
        message_class = AIMessage if item.get("role") == "assistant" else HumanMessage
        prior_messages.append(message_class(content=item.get("content", "")))
    initial_state: AgentState = {
        "user_id": user_id,
        "run_id": run_id,
        "locale": locale,
        "messages": [*prior_messages, HumanMessage(content=message)],
        "route": "general",
        "resolution_mode": "main_llm",
        "rag_enabled": settings.rag_enabled,
        "rag_context": "",
        "retrieved_chunks": [],
        "routing_fallback_reason": None,
    }
    result = app.invoke(initial_state)
    return {
        "answer": str(result["messages"][-1].content),
        "route": result.get("route", "general"),
        "resolution_mode": result.get("resolution_mode", "main_llm"),
        "calorie_decision": result.get("calorie_decision"),
        "routing_fallback_reason": result.get("routing_fallback_reason"),
    }


def run_agent_turn(user_id: str, message: str, locale: str = "ru") -> str:
    """Backward-compatible text-only entry point for existing scripts."""
    return run_agent_turn_details(user_id, message, locale)["answer"]
