"""Run one agent turn independently from the HTTP and worker boundaries."""

import logging
from typing import Any
from time import perf_counter

from app.agents import graph as agent_graph
from app.services import agent_conversations, agent_memory, agent_traces

logger = logging.getLogger(__name__)


class ConversationNotFoundError(Exception):
    """The requested conversation does not exist for this user."""


def _record_failed_run(
    run_id: str | None,
    user_id: str,
    error: Exception,
    started_at: float,
) -> None:
    if run_id is None:
        return
    try:
        agent_traces.fail_agent_run(
            run_id=run_id,
            user_id=user_id,
            error=error,
            latency_ms=agent_traces.elapsed_ms(started_at),
        )
    except Exception:
        logger.exception("Could not persist failed agent run %s", run_id)


def run_agent_chat(
    *,
    user_id: str,
    message: str,
    locale: str,
    conversation_id: str | None,
    trace_id: str | None = None,
    job_id: str | None = None,
    queue_latency_ms: int = 0,
    experiment_id: str | None = None,
    variant_id: str | None = None,
) -> dict[str, Any]:
    """Execute and persist an agent turn. Safe to call from a Celery worker."""
    started_at = perf_counter()
    try:
        resolved_conversation_id, history = agent_conversations.prepare_conversation(
            user_id,
            conversation_id,
            message,
            locale,
        )
    except ValueError as exc:
        raise ConversationNotFoundError(str(exc)) from exc

    run_id: str | None = None
    memory_snapshot = agent_memory.load_agent_memory_best_effort(user_id)
    try:
        run_id = agent_traces.create_agent_run(
            user_id,
            message,
            conversation_id=resolved_conversation_id,
            run_id=trace_id,
            job_id=job_id,
            queue_latency_ms=queue_latency_ms,
            experiment_id=experiment_id,
            variant_id=variant_id,
        )
    except Exception:
        # Observability must not make the user-facing chat unavailable.
        logger.exception("Could not create agent trace for user %s", user_id)

    try:
        result = agent_graph.run_agent_turn_details(
            user_id=user_id,
            message=message,
            locale=locale,
            trace_id=run_id,
            history=history,
            memory_context=memory_snapshot.prompt(),
            experiment_id=experiment_id,
            variant_id=variant_id,
        )
        agent_conversations.save_turn(
            resolved_conversation_id,
            message,
            result["answer"],
        )
        agent_memory.update_agent_memory_best_effort(
            user_id=user_id,
            user_message=message,
            assistant_answer=result["answer"],
            previous=memory_snapshot,
            locale=locale,
            run_id=run_id,
        )
    except Exception as exc:
        logger.exception("Agent turn failed for user %s", user_id)
        _record_failed_run(run_id, user_id, exc, started_at)
        raise

    if run_id is not None:
        try:
            agent_traces.succeed_agent_run(
                run_id=run_id,
                user_id=user_id,
                route=result["route"],
                output_text=result["answer"],
                latency_ms=agent_traces.elapsed_ms(started_at),
                resolution_mode=result["resolution_mode"],
                routing_fallback_reason=result.get("routing_fallback_reason"),
            )
        except Exception:
            logger.exception("Could not complete agent trace %s", run_id)

    response: dict[str, Any] = {
        "answer": result["answer"],
        "route": result["route"],
        "conversation_id": resolved_conversation_id,
    }
    if result.get("calorie_decision") is not None:
        response["calorie_decision"] = result["calorie_decision"]
    return response
