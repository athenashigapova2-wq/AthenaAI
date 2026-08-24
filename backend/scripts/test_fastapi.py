"""Offline checks for the FastAPI boundary; no Redis, Supabase, or LLM calls."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientConnectionError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEST_JWT_SECRET = "offline-test-secret-at-least-32-bytes"
os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET

from app.auth.supabase_jwt import decode_access_token  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.agent_jobs import QueueUnavailableError  # noqa: E402

client = TestClient(app)
JOB_ID = "11111111-1111-4111-8111-111111111111"


def make_token(user_id: str = "test-user-id") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "iss": f"{settings.supabase_url.rstrip('/')}/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def check_jwt_boundary() -> None:
    with (
        patch.object(settings, "supabase_jwt_secret", ""),
        patch("app.auth.supabase_jwt.jwt.get_unverified_header", return_value={"alg": "HS256"}),
    ):
        try:
            decode_access_token("token")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 503
            assert "SUPABASE_JWT_SECRET" in str(getattr(exc, "detail", ""))
        else:
            raise AssertionError("Missing JWT configuration must return HTTP 503")

    with (
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
        patch("app.auth.supabase_jwt.jwt.get_unverified_header", return_value={"alg": "ES256"}),
        patch("app.auth.supabase_jwt._jwks_client") as jwks_client,
        patch(
            "app.auth.supabase_jwt.jwt.decode",
            return_value={"sub": "jwks-user", "email": "user@example.com"},
        ) as jwks_decode,
    ):
        jwks_client.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(
            key="public-key"
        )
        jwks_user = decode_access_token("asymmetric-token")
    assert jwks_user.user_id == "jwks-user"
    assert jwks_decode.call_args.kwargs["algorithms"] == ["ES256"]
    assert jwks_decode.call_args.kwargs["issuer"].endswith("/auth/v1")

    with (
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
        patch("app.auth.supabase_jwt.jwt.get_unverified_header", return_value={"alg": "ES256"}),
        patch("app.auth.supabase_jwt._jwks_client") as unavailable_jwks,
        patch("app.auth.supabase_jwt.logger.warning"),
    ):
        unavailable_jwks.return_value.get_signing_key_from_jwt.side_effect = (
            PyJWKClientConnectionError("offline")
        )
        try:
            decode_access_token("asymmetric-token")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 503
            assert "SUPABASE_URL" in str(getattr(exc, "detail", ""))
        else:
            raise AssertionError("JWKS network failure must return HTTP 503")


def check_job_api() -> None:
    missing_token = client.post("/api/v1/agent/chat", json={"message": "Hello"})
    assert missing_token.status_code == 401

    with patch("app.api.agent.agent_jobs.enqueue_agent_job", return_value=JOB_ID) as enqueue:
        response = client.post(
            "/api/v1/agent/chat",
            headers=auth_headers(),
            json={"message": "Hello", "locale": "en"},
        )
    assert response.status_code == 202, response.text
    assert response.json() == {
        "job_id": JOB_ID,
        "status": "queued",
        "status_url": f"http://testserver/api/v1/agent/chat/jobs/{JOB_ID}",
    }
    enqueue.assert_called_once_with(
        user_id="test-user-id",
        message="Hello",
        locale="en",
        conversation_id=None,
    )

    with patch(
        "app.api.agent.agent_jobs.enqueue_agent_job",
        side_effect=QueueUnavailableError("offline"),
    ):
        unavailable = client.post(
            "/api/v1/agent/chat",
            headers=auth_headers(),
            json={"message": "Hello"},
        )
    assert unavailable.status_code == 503

    completed_job = {
        "job_id": JOB_ID,
        "status": "succeeded",
        "answer": "Hello!",
        "route": "general",
        "conversation_id": "conversation-id",
    }
    with patch("app.api.agent.agent_jobs.get_agent_job", return_value=completed_job):
        completed = client.get(
            f"/api/v1/agent/chat/jobs/{JOB_ID}",
            headers=auth_headers(),
        )
    assert completed.status_code == 200
    assert completed.json()["answer"] == "Hello!"

    stream_job = {
        **completed_job,
        "stage": "completed",
    }
    redis = MagicMock()
    redis.pubsub.return_value = MagicMock()
    with (
        patch("app.api.agent.agent_jobs.get_agent_job", return_value=stream_job),
        patch("app.api.agent.agent_jobs.redis_client", return_value=redis),
    ):
        events = client.get(
            f"/api/v1/agent/chat/jobs/{JOB_ID}/events",
            headers=auth_headers(),
        )
    assert events.status_code == 200
    assert "event: completed" in events.text
    assert '"answer": "Hello!"' in events.text

    with patch("app.api.agent.agent_jobs.get_agent_job", return_value=None):
        hidden_foreign_job = client.get(
            f"/api/v1/agent/chat/jobs/{JOB_ID}",
            headers=auth_headers(),
        )
    assert hidden_foreign_job.status_code == 404

    cancelled_job = {
        "job_id": JOB_ID,
        "status": "cancelled",
        "stage": "cancelled",
    }
    with patch(
        "app.api.agent.agent_jobs.cancel_agent_job",
        return_value=cancelled_job,
    ) as cancel:
        cancelled = client.post(
            f"/api/v1/agent/chat/jobs/{JOB_ID}/cancel",
            headers=auth_headers(),
        )
    assert cancelled.status_code == 200
    assert cancelled.json() == cancelled_job
    cancel.assert_called_once_with(JOB_ID, "test-user-id")

    with patch("app.api.agent.agent_jobs.cancel_agent_job", return_value=None):
        hidden_cancel = client.post(
            f"/api/v1/agent/chat/jobs/{JOB_ID}/cancel",
            headers=auth_headers(),
        )
    assert hidden_cancel.status_code == 404


def check_readiness_respects_llm_provider() -> None:
    with (
        patch.object(settings, "llm_provider", "mock"),
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
        patch.object(settings, "supabase_service_role_key", "service-role"),
        patch.object(settings, "gigachat_auth_key", ""),
        patch("app.main.redis_is_ready", return_value=True),
    ):
        mock_ready = client.get("/health/ready")
    assert mock_ready.json() == {
        "status": "ready",
        "missing": [],
        "redis": "ready",
    }

    with (
        patch.object(settings, "llm_provider", "gigachat"),
        patch.object(settings, "supabase_url", "https://project.supabase.co"),
        patch.object(settings, "supabase_service_role_key", "service-role"),
        patch.object(settings, "gigachat_auth_key", ""),
        patch("app.main.redis_is_ready", return_value=True),
    ):
        gigachat_not_ready = client.get("/health/ready")
    assert gigachat_not_ready.json()["status"] == "not_ready"
    assert gigachat_not_ready.json()["missing"] == ["GIGACHAT_AUTH_KEY"]


def main() -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    check_readiness_respects_llm_provider()
    check_jwt_boundary()
    check_job_api()
    print("FastAPI checks passed")


if __name__ == "__main__":
    main()
