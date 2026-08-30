from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.main import app
from app.services.account_deletion import (
    AccountDeletionDependencyError,
    AccountDeletionError,
    AccountDeletionResult,
)
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration
client = TestClient(app)
USER_ID = "11111111-1111-4111-8111-111111111111"
EMAIL = "owner@example.com"


def _user(*, age_seconds: int = 0) -> AuthenticatedUser:
    return AuthenticatedUser(
        USER_ID,
        EMAIL,
        issued_at=round(datetime.now(UTC).timestamp()) - age_seconds,
    )


def test_confirmed_recent_user_can_delete_entire_account() -> None:
    app.dependency_overrides[get_current_user] = _user
    try:
        with patch(
            "app.api.account.account_deletion.delete_account",
            return_value=AccountDeletionResult(2, 4),
        ) as delete:
            response = client.request(
                "DELETE",
                "/api/v1/account",
                json={"confirmation": "DELETE", "email": EMAIL},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "deleted",
        "storage_objects_deleted": 2,
        "runtime_records_scrubbed": 4,
    }
    delete.assert_called_once_with(USER_ID)


def test_account_deletion_requires_recent_authentication() -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(age_seconds=601)
    try:
        with patch("app.api.account.account_deletion.delete_account") as delete:
            response = client.request(
                "DELETE",
                "/api/v1/account",
                json={"confirmation": "DELETE", "email": EMAIL},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    delete.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    (
        {"confirmation": "delete", "email": EMAIL},
        {"confirmation": "DELETE", "email": "someone-else@example.com"},
    ),
)
def test_account_deletion_rejects_invalid_confirmation(payload: dict[str, str]) -> None:
    app.dependency_overrides[get_current_user] = _user
    try:
        with patch("app.api.account.account_deletion.delete_account") as delete:
            response = client.request("DELETE", "/api/v1/account", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code in {403, 422}
    delete.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    (
        (AccountDeletionDependencyError("storage"), 503),
        (AccountDeletionError("auth"), 502),
    ),
)
def test_account_deletion_reports_retryable_backend_failures(
    failure: Exception,
    expected_status: int,
) -> None:
    app.dependency_overrides[get_current_user] = _user
    try:
        with patch(
            "app.api.account.account_deletion.delete_account",
            side_effect=failure,
        ):
            response = client.request(
                "DELETE",
                "/api/v1/account",
                json={"confirmation": "DELETE", "email": EMAIL},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
