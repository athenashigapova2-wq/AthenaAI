"""Production-like HTTP -> Redis -> Celery -> SSE golden path.

The test is an explicit CI contour. It uses the real application boundaries and
Redis Lua updates, while Celery executes eagerly and the external LLM is replaced
by Athena's deterministic infrastructure-test response.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from app.config import settings
from app.main import app
from app.services import agent_jobs
from app.workers.celery_app import celery_app
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_PRODUCTION_LIKE_E2E") != "1",
        reason="production-like golden path requires explicit opt-in and Redis",
    ),
]

JWT_SECRET = "ci-only-golden-path-secret-with-at-least-32-bytes"
SUPABASE_URL = "https://golden-path.supabase.test"
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"


def _access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token(user_id)}"}


def test_authenticated_chat_completes_through_real_job_lifecycle() -> None:
    redis = agent_jobs.redis_client()
    assert redis.ping()
    previous_always_eager = celery_app.conf.task_always_eager
    previous_eager_propagates = celery_app.conf.task_eager_propagates
    job_id: str | None = None

    try:
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        with (
            patch.object(settings, "supabase_jwt_secret", JWT_SECRET),
            patch.object(settings, "supabase_url", SUPABASE_URL),
            patch.object(settings, "llm_provider", "mock"),
            patch.object(settings, "agent_infrastructure_test_mode", True),
            TestClient(app) as client,
        ):
            accepted = client.post(
                "/api/v1/agent/chat",
                headers=_headers(USER_ID),
                json={"message": "Give me a concise progress update", "locale": "en"},
            )
            assert accepted.status_code == 202
            accepted_body = accepted.json()
            job_id = accepted_body["job_id"]
            assert accepted_body["status"] == "queued"
            assert accepted.headers["X-Trace-ID"] == accepted_body["trace_id"]

            completed = client.get(
                f"/api/v1/agent/chat/jobs/{job_id}",
                headers=_headers(USER_ID),
            )
            assert completed.status_code == 200
            completed_body = completed.json()
            assert completed_body["status"] == "succeeded"
            assert completed_body["stage"] == "completed"
            assert completed_body["trace_id"] == accepted_body["trace_id"]
            assert completed_body["route"] == "general"
            assert completed_body["answer"] == (
                "[INFRASTRUCTURE_TEST] FastAPI/Redis/Celery task completed."
            )

            events = client.get(
                f"/api/v1/agent/chat/jobs/{job_id}/events",
                headers=_headers(USER_ID),
            )
            assert events.status_code == 200
            assert "event: completed" in events.text
            assert '"status": "succeeded"' in events.text

            foreign_read = client.get(
                f"/api/v1/agent/chat/jobs/{job_id}",
                headers=_headers(OTHER_USER_ID),
            )
            assert foreign_read.status_code == 404
    finally:
        celery_app.conf.task_always_eager = previous_always_eager
        celery_app.conf.task_eager_propagates = previous_eager_propagates
        if job_id is not None:
            redis.delete(agent_jobs._job_key(job_id))
