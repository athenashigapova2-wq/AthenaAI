"""LangGraph retrieval node placed between routing and specialist execution."""

from __future__ import annotations

import logging
from time import perf_counter

from app.agents.state import AgentName, AgentState
from app.rag.contracts import KnowledgeDomain
from app.rag.retriever import format_retrieval_context, retrieve_knowledge
from app.services import agent_traces

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
    trace_id = state.get("trace_id")
    if not state.get("rag_enabled", True):
        agent_traces.record_rag_metrics(
            run_id=trace_id,
            attempted=False,
            retrieved_chunk_count=0,
            retrieval_latency_ms=0,
            top_similarity=None,
            context_chars=0,
        )
        return {"retrieved_chunks": [], "rag_context": ""}
    started_at = perf_counter()
    try:
        chunks = retrieve_knowledge(
            _last_user_text(state),
            domains=_ROUTE_DOMAINS[state.get("route", "general")],
        )
    except Exception:
        logger.exception("Knowledge retrieval failed; continuing without RAG context")
        agent_traces.record_rag_metrics(
            run_id=trace_id,
            attempted=True,
            retrieved_chunk_count=0,
            retrieval_latency_ms=agent_traces.elapsed_ms(started_at),
            top_similarity=None,
            context_chars=0,
        )
        return {"retrieved_chunks": [], "rag_context": ""}
    context = format_retrieval_context(chunks)
    agent_traces.record_rag_metrics(
        run_id=trace_id,
        attempted=True,
        retrieved_chunk_count=len(chunks),
        retrieval_latency_ms=agent_traces.elapsed_ms(started_at),
        top_similarity=max((chunk.similarity for chunk in chunks), default=None),
        context_chars=len(context),
    )
    return {
        "retrieved_chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        "rag_context": context,
    }
