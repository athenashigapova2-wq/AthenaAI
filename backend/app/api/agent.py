"""Authenticated HTTP endpoint for one Athena agent turn."""

from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.agents import graph as agent_graph
from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.services import agent_traces

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    locale: Literal["ru", "en", "fr", "es", "zh"] = "ru"


class AgentChatResponse(BaseModel):
    answer: str
    route: Literal["nutrition", "workout", "recovery", "general"]


@router.post("/chat", response_model=AgentChatResponse)
def chat_with_agent(
    request: AgentChatRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentChatResponse:
    """Route a message through LangGraph using user_id only from the verified JWT."""
    started_at = perf_counter()
    run_id = agent_traces.create_agent_run(user.user_id, request.message)
    try:
        result = agent_graph.run_agent_turn_details(
            user_id=user.user_id,
            message=request.message,
            locale=request.locale,
        )
    except Exception as exc:
        agent_traces.fail_agent_run(
            run_id=run_id,
            user_id=user.user_id,
            error=exc,
            latency_ms=agent_traces.elapsed_ms(started_at),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Агент временно недоступен",
        ) from exc

    agent_traces.succeed_agent_run(
        run_id=run_id,
        user_id=user.user_id,
        route=result["route"],
        output_text=result["answer"],
        latency_ms=agent_traces.elapsed_ms(started_at),
    )
    return AgentChatResponse(**result)
