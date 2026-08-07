"""Offline checks for the FastAPI boundary; no Supabase or LLM calls."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_JWT_SECRET", "offline-test-secret-at-least-32-bytes")

from app.main import app  # noqa: E402

client = TestClient(app)


def make_token(user_id: str = "test-user-id") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )


def main() -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}

    missing_token = client.post("/api/v1/agent/chat", json={"message": "Привет"})
    assert missing_token.status_code == 401

    with patch("app.api.agent.agent_graph.run_agent_turn_details") as run_turn:
        run_turn.return_value = {"answer": "Добавила завтрак", "route": "nutrition"}
        response = client.post(
            "/api/v1/agent/chat",
            headers={"Authorization": f"Bearer {make_token()}"},
            json={"message": "Запиши завтрак", "locale": "ru"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {"answer": "Добавила завтрак", "route": "nutrition"}
    run_turn.assert_called_once_with(
        user_id="test-user-id",
        message="Запиши завтрак",
        locale="ru",
    )
    print("FastAPI checks passed")


if __name__ == "__main__":
    main()
