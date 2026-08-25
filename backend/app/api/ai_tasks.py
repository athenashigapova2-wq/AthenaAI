"""Authenticated HTTP boundary for narrow server-owned AI tasks."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.services.ai_tasks import AITaskService, UnsupportedAITaskError


router = APIRouter(prefix="/ai/tasks", tags=["ai-tasks"])


class AITaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any] = Field(default_factory=dict)


def get_ai_task_service() -> AITaskService:
    return AITaskService()


@router.post("/{use_case}")
def execute_ai_task(
    use_case: str,
    request: AITaskRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AITaskService = Depends(get_ai_task_service),
) -> dict[str, Any]:
    """Execute an allowlisted task; prompts and schemas are never client-owned."""
    try:
        result = service.execute(use_case, request.input, user_id=user.user_id)
    except UnsupportedAITaskError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_url=False),
        ) from exc
    return result.model_dump(mode="json")
