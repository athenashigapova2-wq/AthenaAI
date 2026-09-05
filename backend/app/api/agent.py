"""Authenticated HTTP and SSE boundary for Redis-backed Athena agent jobs."""

import asyncio
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.evaluation.experiments import assign_active_experiment
from app.services import agent_jobs, agent_traces
from app.services import write_confirmations

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4_000)
    locale: Literal["ru", "en", "fr", "es", "zh"] = "ru"
    conversation_id: UUID | None = None


class AgentChatAccepted(BaseModel):
    job_id: str
    trace_id: str
    experiment_id: str | None = None
    variant_id: str | None = None
    status: Literal["queued"]
    status_url: str


class CalorieEvidencePeriod(BaseModel):
    start: str | None = None
    end: str | None = None


class CalorieDecisionResponse(BaseModel):
    action: Literal["keep", "increase", "decrease"]
    current_calories: float
    proposed_calories: float
    minimum_calories: float
    change_kcal: float
    weight_records: int = Field(ge=0)
    evidence_period: CalorieEvidencePeriod
    rationale: str


class PendingWriteActionResponse(BaseModel):
    action_id: UUID
    confirmation_token: str
    tool_name: Literal["log_meal", "log_workout"]
    preview: dict[str, object]
    expires_at: str


class AgentJobResponse(BaseModel):
    job_id: str
    trace_id: str
    experiment_id: str | None = None
    variant_id: str | None = None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: (
        Literal["queued", "running", "tool_call", "generating", "completed", "failed", "cancelled"]
        | None
    ) = None
    answer: str | None = None
    route: Literal["nutrition", "workout", "recovery", "general"] | None = None
    conversation_id: str | None = None
    error: str | None = None
    calorie_decision: CalorieDecisionResponse | None = None
    pending_write_action: PendingWriteActionResponse | None = None


class WriteActionConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_token: str = Field(min_length=20, max_length=200)


class WriteActionConfirmationResponse(BaseModel):
    status: Literal["confirmed"]
    action_id: UUID
    tool_name: Literal["log_meal", "log_workout"]
    tool_result: dict[str, object]
    idempotency_key: str
    idempotent_replay: bool
    conversation_id: str | None = None


class WriteActionRejectedResponse(BaseModel):
    status: Literal["rejected"]
    action_id: UUID


class AgentJobCancelled(BaseModel):
    job_id: str
    trace_id: str
    experiment_id: str | None = None
    variant_id: str | None = None
    status: Literal["cancelled", "succeeded", "failed"]
    stage: str | None = None


class TraceDeletionResponse(BaseModel):
    status: Literal["deleted"]
    runs_deleted: int = Field(ge=0)


@router.post(
    "/chat",
    response_model=AgentChatAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def chat_with_agent(
    request: AgentChatRequest,
    http_request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentChatAccepted:
    """Validate the caller and enqueue a long-running agent turn."""
    assignment = assign_active_experiment(user.user_id)
    try:
        trace_id = str(uuid4())
        job_id = agent_jobs.enqueue_agent_job(
            user_id=user.user_id,
            message=request.message,
            locale=request.locale,
            conversation_id=str(request.conversation_id) if request.conversation_id else None,
            trace_id=trace_id,
            experiment_id=assignment.experiment_id if assignment else None,
            variant_id=assignment.variant_id if assignment else None,
        )
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis или очередь workers недоступны",
        ) from exc

    status_url = str(http_request.url_for("get_agent_job", job_id=job_id))
    response.headers["X-Trace-ID"] = trace_id
    return AgentChatAccepted(
        job_id=job_id,
        trace_id=trace_id,
        experiment_id=assignment.experiment_id if assignment else None,
        variant_id=assignment.variant_id if assignment else None,
        status="queued",
        status_url=status_url,
    )


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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/chat/jobs/{job_id}/events")
async def stream_agent_job(
    job_id: UUID,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream owner-scoped job progress from Redis Pub/Sub."""
    job_id_text = str(job_id)
    try:
        job = agent_jobs.get_agent_job(job_id_text, user.user_id)
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Redis недоступен") from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    async def events():
        client = agent_jobs.redis_client()
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        await asyncio.to_thread(pubsub.subscribe, agent_jobs.job_event_channel(job_id_text))
        try:
            current = agent_jobs.get_agent_job(job_id_text, user.user_id)
            if current is None:
                yield _sse("failed", {"job_id": job_id_text, "error": "Задание не найдено"})
                return
            initial_event = {
                "succeeded": "completed",
                "failed": "failed",
                "cancelled": "cancelled",
            }.get(current["status"], current.get("stage") or current["status"])
            yield _sse(initial_event, current)
            if current["status"] in agent_jobs.TERMINAL_STATUSES:
                return

            while not await request.is_disconnected():
                message = await asyncio.to_thread(pubsub.get_message, True, 1.0)
                if message and message.get("type") == "message":
                    envelope = json.loads(message["data"])
                    yield _sse(envelope["event"], envelope["data"])
                    if envelope["data"].get("status") in agent_jobs.TERMINAL_STATUSES:
                        return
                else:
                    yield ": keep-alive\n\n"
        finally:
            await asyncio.to_thread(pubsub.close)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/jobs/{job_id}/cancel", response_model=AgentJobCancelled)
def cancel_agent_job(
    job_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
) -> AgentJobCancelled:
    """Cancel queued work or request cooperative cancellation of running work."""
    try:
        job = agent_jobs.cancel_agent_job(str(job_id), user.user_id)
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Redis недоступен") from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return AgentJobCancelled(**job)


@router.post(
    "/write-actions/{action_id}/confirm",
    response_model=WriteActionConfirmationResponse,
)
def confirm_agent_write_action(
    action_id: UUID,
    request: WriteActionConfirmationRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> WriteActionConfirmationResponse:
    """Execute one owner-scoped pending write exactly once per idempotency key."""
    try:
        result = write_confirmations.confirm_write_action(
            action_id=str(action_id),
            user_id=user.user_id,
            confirmation_token=request.confirmation_token,
            idempotency_key=idempotency_key,
        )
    except write_confirmations.WriteActionInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except write_confirmations.WriteActionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Redis недоступен") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    return WriteActionConfirmationResponse(**result)


@router.post(
    "/write-actions/{action_id}/reject",
    response_model=WriteActionRejectedResponse,
)
def reject_agent_write_action(
    action_id: UUID,
    request: WriteActionConfirmationRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> WriteActionRejectedResponse:
    """Reject a pending action without executing its tool."""
    try:
        result = write_confirmations.reject_write_action(
            action_id=str(action_id),
            user_id=user.user_id,
            confirmation_token=request.confirmation_token,
        )
    except write_confirmations.WriteActionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except agent_jobs.QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Redis недоступен") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Операция не найдена")
    return WriteActionRejectedResponse(**result)


@router.get("/privacy/traces/export")
def export_agent_traces(
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Export only trace rows owned by the authenticated user."""
    return agent_traces.export_user_traces(user.user_id)


@router.delete("/privacy/traces", response_model=TraceDeletionResponse)
def delete_agent_traces(
    user: AuthenticatedUser = Depends(get_current_user),
) -> TraceDeletionResponse:
    """Delete the authenticated user's runs and all cascading child traces."""
    deleted = agent_traces.delete_user_traces(user.user_id)
    return TraceDeletionResponse(status="deleted", runs_deleted=deleted)
