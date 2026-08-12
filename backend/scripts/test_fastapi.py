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
from app.auth.supabase_jwt import decode_access_token  # noqa: E402
from app.config import settings  # noqa: E402

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

    with patch.object(settings, "supabase_jwt_secret", ""):
        try:
            decode_access_token("token")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 503
            assert "SUPABASE_JWT_SECRET" in str(getattr(exc, "detail", ""))
        else:
            raise AssertionError("Missing JWT configuration must return HTTP 503")

    missing_token = client.post("/api/v1/agent/chat", json={"message": "Привет"})
    assert missing_token.status_code == 401

    with patch(
        "app.api.agent.agent_conversations.prepare_conversation",
        side_effect=RuntimeError("database unavailable"),
    ):
        setup_failure = client.post(
            "/api/v1/agent/chat",
            headers={"Authorization": f"Bearer {make_token()}"},
            json={"message": "Привет"},
        )
    assert setup_failure.status_code == 503
    assert setup_failure.json() == {
        "detail": "Supabase недоступен или backend/.env настроен неверно"
    }

    with (
        patch("app.api.agent.agent_graph.run_agent_turn_details") as run_turn,
        patch("app.api.agent.agent_traces.create_agent_run", return_value="run-id"),
        patch("app.api.agent.agent_traces.succeed_agent_run") as succeed_run,
        patch(
            "app.api.agent.agent_conversations.prepare_conversation",
            return_value=("conversation-id", []),
        ),
        patch("app.api.agent.agent_conversations.save_turn") as save_turn,
    ):
        run_turn.return_value = {
            "answer": "Добавила завтрак",
            "route": "nutrition",
            "resolution_mode": "main_llm",
        }
        response = client.post(
            "/api/v1/agent/chat",
            headers={"Authorization": f"Bearer {make_token()}"},
            json={"message": "Запиши завтрак", "locale": "ru"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "answer": "Добавила завтрак",
        "route": "nutrition",
        "conversation_id": "conversation-id",
    }
    run_turn.assert_called_once_with(
        user_id="test-user-id",
        message="Запиши завтрак",
        locale="ru",
        run_id="run-id",
        history=[],
    )
    save_turn.assert_called_once_with("conversation-id", "Запиши завтрак", "Добавила завтрак")
    succeed_run.assert_called_once()
    assert succeed_run.call_args.kwargs["run_id"] == "run-id"
    assert succeed_run.call_args.kwargs["user_id"] == "test-user-id"
    assert succeed_run.call_args.kwargs["route"] == "nutrition"
    assert succeed_run.call_args.kwargs["resolution_mode"] == "main_llm"

    with (
        patch(
            "app.api.agent.agent_graph.run_agent_turn_details",
            side_effect=RuntimeError("LLM unavailable"),
        ),
        patch(
            "app.api.agent.agent_traces.create_agent_run",
            return_value="failed-run-id",
        ),
        patch("app.api.agent.agent_traces.fail_agent_run") as fail_run,
        patch(
            "app.api.agent.agent_conversations.prepare_conversation",
            return_value=("conversation-id", []),
        ),
        patch("app.api.agent.agent_conversations.save_turn"),
    ):
        failed_response = client.post(
            "/api/v1/agent/chat",
            headers={"Authorization": f"Bearer {make_token()}"},
            json={"message": "Привет"},
        )

    assert failed_response.status_code == 503
    assert failed_response.json() == {"detail": "Агент временно недоступен"}
    fail_run.assert_called_once()
    assert fail_run.call_args.kwargs["run_id"] == "failed-run-id"
    assert fail_run.call_args.kwargs["user_id"] == "test-user-id"

    with (
        patch("app.api.agent.agent_graph.run_agent_turn_details") as untraced_turn,
        patch(
            "app.api.agent.agent_traces.create_agent_run",
            side_effect=RuntimeError("trace tables missing"),
        ),
        patch("app.api.agent.agent_traces.succeed_agent_run") as untraced_success,
        patch(
            "app.api.agent.agent_conversations.prepare_conversation",
            return_value=("conversation-id", []),
        ),
        patch("app.api.agent.agent_conversations.save_turn"),
    ):
        untraced_turn.return_value = {
            "answer": "Привет!",
            "route": "general",
            "resolution_mode": "main_llm",
        }
        untraced_response = client.post(
            "/api/v1/agent/chat",
            headers={"Authorization": f"Bearer {make_token()}"},
            json={"message": "Привет"},
        )
    assert untraced_response.status_code == 200, untraced_response.text
    assert untraced_response.json()["answer"] == "Привет!"
    untraced_success.assert_not_called()
    print("FastAPI checks passed")


if __name__ == "__main__":
    main()
