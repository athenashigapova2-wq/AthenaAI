"""Authenticated HTTP boundary for Redis-backed Athena agent jobs."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.services import agent_jobs

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    locale: Literal["ru", "en", "fr", "es", "zh"] = "ru"
    conversation_id: UUID | None = None


class AgentChatAccepted(BaseModel):
    job_id: str
    status: Literal["queued"]
    status_url: str


class AgentJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    answer: str | None = None
    route: Literal["nutrition", "workout", "recovery", "general"] | None = None
    conversation_id: str | None = None
    error: str | None = None


@router.post(
    "/chat",
    response_model=AgentChatAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def chat_with_agent(
    request: AgentChatRequest,
    http_request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentChatAccepted:
    """Validate the caller and enqueue a long-running agent turn."""
    try:
        job_id = agent_jobs.enqueue_agent_job(
            user_id=user.user_id,
            message=request.message,
            locale=request.locale,
            conversation_id=str(request.conversation_id) if request.conversation_id else None,
        )
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis или очередь workers недоступны",
        ) from exc

    status_url = str(http_request.url_for("get_agent_job", job_id=job_id))
    return AgentChatAccepted(job_id=job_id, status="queued", status_url=status_url)


@router.get("/chat/jobs/{job_id}", response_model=AgentJobResponse)
def get_agent_job(
    job_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentJobResponse:
    """Return only the authenticated user's job status and completed result."""
    try:
        job = agent_jobs.get_agent_job(str(job_id), user.user_id)
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis недоступен",
        ) from exc
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задание не найдено")
    return AgentJobResponse(**job)
