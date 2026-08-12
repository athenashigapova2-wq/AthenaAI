"""Authenticated HTTP endpoint for one Athena agent turn."""

import logging
from time import perf_counter
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agents import graph as agent_graph
from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.services import agent_traces
from app.services import agent_conversations

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def _record_failed_run(run_id: str | None, user_id: str, error: Exception, started_at: float) -> None:
    """Record a failure when tracing is available without masking the original error."""
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


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    locale: Literal["ru", "en", "fr", "es", "zh"] = "ru"
    conversation_id: UUID | None = None


class AgentChatResponse(BaseModel):
    answer: str
    route: Literal["nutrition", "workout", "recovery", "general"]
    conversation_id: str


@router.post("/chat", response_model=AgentChatResponse)
def chat_with_agent(
    request: AgentChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentChatResponse:
    """Route a message through LangGraph using user_id only from the verified JWT."""
    started_at = perf_counter()
    try:
        conversation_id, history = agent_conversations.prepare_conversation(
            user.user_id,
            str(request.conversation_id) if request.conversation_id else None,
            request.message,
            request.locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Could not prepare conversation for user %s", user.user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase недоступен или backend/.env настроен неверно",
        ) from exc

    run_id: str | None = None
    try:
        run_id = agent_traces.create_agent_run(
            user.user_id,
            request.message,
            conversation_id=conversation_id,
        )
    except Exception:
        # Observability must not make the user-facing chat unavailable.
        logger.exception("Could not create agent trace for user %s", user.user_id)

    try:
        result = agent_graph.run_agent_turn_details(
            user_id=user.user_id,
            message=request.message,
            locale=request.locale,
            run_id=run_id,
            history=history,
        )
        agent_conversations.save_turn(conversation_id, request.message, result["answer"])
    except Exception as exc:
        logger.exception("Agent turn failed for user %s", user.user_id)
        _record_failed_run(run_id, user.user_id, exc, started_at)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Агент временно недоступен",
        ) from exc

    if run_id is not None:
        try:
            agent_traces.succeed_agent_run(
                run_id=run_id,
                user_id=user.user_id,
                route=result["route"],
                output_text=result["answer"],
                latency_ms=agent_traces.elapsed_ms(started_at),
                resolution_mode=result["resolution_mode"],
            )
        except Exception:
            logger.exception("Could not complete agent trace %s", run_id)
    return AgentChatResponse(**result, conversation_id=conversation_id)
