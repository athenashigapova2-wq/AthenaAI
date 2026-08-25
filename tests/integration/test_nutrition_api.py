from fastapi.testclient import TestClient

from app.api.nutrition import (
    get_habit_insight_service,
    get_meal_estimation_service,
)
from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.main import app
from app.services.habit_analytics import HabitInsightResult
from app.services.meal_estimation import MealEstimate


class FakeMealService:
    def estimate(self, description, locale):
        assert description == "180 г куриной грудки"
        assert locale == "ru"
        return MealEstimate(
            name="Куриная грудка",
            matched_food="chicken breast raw",
            quantity_g=180,
            calories=216,
            protein_g=41.4,
            carbs_g=0,
            fat_g=4.5,
        )


class FakeHabitService:
    def __init__(self):
        self.user_id = None

    def generate(self, user_id, locale):
        self.user_id = user_id
        assert locale == "ru"
        return HabitInsightResult(insufficient_data=True)


def test_authenticated_meal_estimation_contract() -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("owner-1")
    app.dependency_overrides[get_meal_estimation_service] = FakeMealService
    try:
        response = TestClient(app).post(
            "/api/v1/nutrition/meal-estimate",
            json={"description": "180 г куриной грудки", "locale": "ru"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["matched_food"] == "chicken breast raw"
    assert response.json()["calories"] == 216


def test_habit_insight_uses_authenticated_user_id() -> None:
    service = FakeHabitService()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser("owner-2")
    app.dependency_overrides[get_habit_insight_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/nutrition/habit-insight",
            json={"locale": "ru"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "insufficient_data": True,
        "analytics": None,
        "suggestion": None,
    }
    assert service.user_id == "owner-2"
