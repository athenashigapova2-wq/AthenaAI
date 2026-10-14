from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.agents.nutrition_validation import NutritionNumbers
from app.nutrition_policy import (
    NutritionPolicyError,
    calculate_macro_calories,
    validate_nutrition_values,
)
from app.services.ai_tasks import MacroBlock
from app.services.habit_analytics import DailyMacroAverage
from app.services.meal_estimation import FoodCandidate
from app.tools.nutrition import log_meal
from app.tools.registry import build_tools
from pydantic import ValidationError
from simulation.longitudinal import MemorySupabase, apply_event


@pytest.mark.parametrize(
    "field",
    ("calories", "protein_g", "carbs_g", "fat_g"),
)
def test_shared_policy_rejects_each_negative_nutrition_value(field: str) -> None:
    values = {"calories": 500, "protein_g": 30, "carbs_g": 50, "fat_g": 20}
    values[field] = -1

    with pytest.raises(NutritionPolicyError, match="non-negative"):
        validate_nutrition_values(**values)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_shared_policy_rejects_nonfinite_values(invalid: float) -> None:
    with pytest.raises(NutritionPolicyError, match="finite"):
        validate_nutrition_values(
            calories=invalid,
            protein_g=10,
            carbs_g=10,
            fat_g=10,
        )


def test_shared_macro_calculation_uses_449_formula() -> None:
    assert calculate_macro_calories(20, 30, 10) == 290


def test_internal_value_object_rejects_negative_macros() -> None:
    with pytest.raises(NutritionPolicyError):
        NutritionNumbers(calories=100, protein_g=-1, carbs_g=10, fat_g=5)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            MacroBlock,
            {"calories": 100, "protein": -1, "carbs": 10, "fat": 5},
        ),
        (
            DailyMacroAverage,
            {"calories": 100, "protein_g": -1, "carbs_g": 10, "fat_g": 5},
        ),
        (
            FoodCandidate,
            {
                "food_name": "test",
                "calories_per_100g": 100,
                "protein_g": -1,
                "carbs_g": 10,
                "fat_g": 5,
            },
        ),
    ],
)
def test_service_schemas_share_nonnegative_policy(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_log_meal_rejects_invalid_values_before_database_access() -> None:
    with patch("app.tools.nutrition.get_supabase") as get_supabase:
        result = log_meal("user-1", "bad meal", 100, -1, 10, 5)

    assert result["status"] == "error"
    get_supabase.assert_not_called()


def test_tool_schema_rejects_negative_macros_before_tool_execution() -> None:
    tool = next(item for item in build_tools("user-1", ("nutrition",)) if item.name == "log_meal")

    with pytest.raises(ValidationError):
        tool.args_schema.model_validate(
            {
                "name": "bad meal",
                "calories": 100,
                "protein_g": -1,
                "carbs_g": 10,
                "fat_g": 5,
            }
        )


def test_longitudinal_meal_events_use_shared_policy() -> None:
    store = MemorySupabase({"user_id": "user-1"})
    event = SimpleNamespace(
        event_type="meal",
        payload={
            "name": "bad meal",
            "calories": 100,
            "protein_g": -1,
            "carbs_g": 10,
            "fat_g": 5,
        },
    )

    with pytest.raises(NutritionPolicyError):
        apply_event(store, "user-1", datetime(2026, 1, 1), event)

    assert store.tables["meal_logs"] == []
