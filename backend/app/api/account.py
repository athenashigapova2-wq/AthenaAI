"""Authenticated privacy boundary for permanent account deletion."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.services import account_deletion

router = APIRouter(prefix="/account", tags=["account"])
MAX_AUTH_AGE_SECONDS = 10 * 60


class AccountDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE"]
    email: str = Field(min_length=3, max_length=320)


class AccountDeletionResponse(BaseModel):
    status: Literal["deleted"]
    storage_objects_deleted: int = Field(ge=0)
    runtime_records_scrubbed: int = Field(ge=0)


@router.delete("", response_model=AccountDeletionResponse)
def delete_account(
    request: AccountDeletionRequest,
    user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
) -> AccountDeletionResponse:
    """Permanently delete the caller's Auth identity and owned data."""
    if not user.email or not hmac.compare_digest(
        request.email.strip().casefold(),
        user.email.strip().casefold(),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account confirmation does not match the authenticated user",
        )
    if not _has_recent_authentication(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recent authentication is required; refresh the session and try again",
        )
    try:
        result = account_deletion.delete_account(user.user_id)
    except account_deletion.AccountDeletionDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account deletion is temporarily unavailable; no Auth account was removed",
        ) from exc
    except account_deletion.AccountDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Supabase could not delete the account; please retry",
        ) from exc
    return AccountDeletionResponse(
        status="deleted",
        storage_objects_deleted=result.storage_objects_deleted,
        runtime_records_scrubbed=result.runtime_records_scrubbed,
    )


def _has_recent_authentication(user: AuthenticatedUser) -> bool:
    if user.issued_at is None:
        return False
    age = datetime.now(UTC).timestamp() - user.issued_at
    return -60 <= age <= MAX_AUTH_AGE_SECONDS
