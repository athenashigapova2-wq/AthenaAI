"""Authenticated application endpoints for nutrition intelligence."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.supabase_jwt import AuthenticatedUser, get_current_user
from app.services.habit_analytics import HabitInsightResult, HabitInsightService
from app.services.meal_estimation import MealEstimate, MealEstimationService


router = APIRouter(prefix="/nutrition", tags=["nutrition"])
Locale = Literal["ru", "en", "fr", "es", "zh"]


class MealEstimateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    locale: Locale = "ru"


class MealEstimateNotMatched(BaseModel):
    matched: Literal[False] = False


class HabitInsightRequest(BaseModel):
    locale: Locale = "ru"


def get_meal_estimation_service() -> MealEstimationService:
    return MealEstimationService()


def get_habit_insight_service() -> HabitInsightService:
    return HabitInsightService()


@router.post("/meal-estimate", response_model=MealEstimate | MealEstimateNotMatched)
def estimate_meal(
    request: MealEstimateRequest,
    _user: AuthenticatedUser = Depends(get_current_user),
    service: MealEstimationService = Depends(get_meal_estimation_service),
) -> MealEstimate | MealEstimateNotMatched:
    """Estimate macros only after an LLM-assisted, database-backed match."""
    result = service.estimate(request.description, request.locale)
    return result or MealEstimateNotMatched()


@router.post("/habit-insight", response_model=HabitInsightResult)
def generate_habit_insight(
    request: HabitInsightRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: HabitInsightService = Depends(get_habit_insight_service),
) -> HabitInsightResult:
    """Calculate owner-scoped analytics, then generate and persist one insight."""
    return service.generate(user.user_id, request.locale)
