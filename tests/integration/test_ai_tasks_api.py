from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.ai_tasks import get_ai_task_service
from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.main import app


class FakeResult(BaseModel):
    text: str


class FakeAITaskService:
    def execute(self, use_case, raw_input, *, user_id):
        assert use_case == "daily_tip"
        assert raw_input == {"language": "ru"}
        assert user_id == "owner-1"
        return FakeResult(text="Добавьте источник белка.")


def test_ai_task_is_authenticated_and_server_dispatched() -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("owner-1")
    app.dependency_overrides[get_ai_task_service] = FakeAITaskService
    try:
        response = TestClient(app).post(
            "/api/v1/ai/tasks/daily_tip",
            json={"input": {"language": "ru"}},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {"text": "Добавьте источник белка."}


def test_ai_task_rejects_anonymous_requests() -> None:
    response = TestClient(app).post(
        "/api/v1/ai/tasks/daily_tip",
        json={"input": {}},
    )
    assert response.status_code == 401
