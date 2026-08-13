"""LangGraph retrieval node placed between routing and specialist execution."""

from __future__ import annotations

import logging

from app.agents.state import AgentName, AgentState
from app.rag.contracts import KnowledgeDomain
from app.rag.retriever import format_retrieval_context, retrieve_knowledge

logger = logging.getLogger(__name__)

_ROUTE_DOMAINS: dict[AgentName, tuple[KnowledgeDomain, ...]] = {
    "nutrition": ("nutrition", "safety"),
    "workout": ("workout", "recovery", "safety"),
    "recovery": ("recovery", "safety"),
    "general": ("nutrition", "workout", "recovery", "safety", "product"),
}


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if getattr(message, "type", None) == "human":
            return str(message.content)
    return ""


def retriever_node(state: AgentState) -> dict:
    """Retrieve evidence without making chat availability depend on the RAG store."""
    if not state.get("rag_enabled", True):
        return {"retrieved_chunks": [], "rag_context": ""}
    try:
        chunks = retrieve_knowledge(
            _last_user_text(state),
            domains=_ROUTE_DOMAINS[state.get("route", "general")],
        )
    except Exception:
        logger.exception("Knowledge retrieval failed; continuing without RAG context")
        return {"retrieved_chunks": [], "rag_context": ""}
    return {
        "retrieved_chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        "rag_context": format_retrieval_context(chunks),
    }
