"""Shared state for Athena's LangGraph agent workflow."""

from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

AgentName = Literal["nutrition", "workout", "recovery", "general"]
ResolutionMode = Literal["zero_llm", "small_llm", "main_llm", "fallback"]


class AgentState(TypedDict):
    """Conversation state passed between router and specialist agents."""

    user_id: str
    trace_id: str | None
    locale: str
    messages: Annotated[list[BaseMessage], add_messages]
    route: AgentName
    resolution_mode: ResolutionMode
    rag_enabled: bool
    rag_context: str
    retrieved_chunks: list[dict[str, object]]
    memory_context: str
    calorie_decision: NotRequired[dict[str, object] | None]
    routing_fallback_reason: NotRequired[str | None]
