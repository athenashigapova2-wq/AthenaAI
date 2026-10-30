from unittest.mock import patch

from app.services.ai_tasks import AITaskService, MealRecommendationsInput
from app.services.meal_recommendation_fallback import (
    build_fallback_recommendations,
    recommendation_policy_issues,
)


def _context(**overrides):
    context = {
        "remaining": {"calories": 1800, "protein": 120, "carbs": 200, "fat": 60},
        "goal": "maintain",
        "budget": "medium",
        "cooking_skill": "basic",
        "dietary_pattern": "omnivore",
        "dietary_restrictions": [],
        "allergies": [],
        "favorite_foods": [],
        "disliked_foods": [],
        "meals_eaten": [],
        "language": "ru",
    }
    context.update(overrides)
    return context


def test_fallback_does_not_require_shopping_list_state() -> None:
    payload = build_fallback_recommendations(_context())

    assert len(payload["meals"]) == 3
    assert all(meal["name"] and meal["description"] for meal in payload["meals"])
    assert all(meal["ingredients"] for meal in payload["meals"])
    assert all(meal["calories"] >= 0 for meal in payload["meals"])


def test_fallback_keeps_macros_feasible_when_only_protein_is_missing() -> None:
    payload = build_fallback_recommendations(
        _context(remaining={"calories": 750, "protein": 150, "carbs": 0, "fat": 0})
    )

    assert all(meal["protein_g"] <= meal["calories"] * 0.40 / 4 + 0.1 for meal in payload["meals"])
    assert all(meal["carbs_g"] > 0 and meal["fat_g"] > 0 for meal in payload["meals"])


def test_fallback_respects_vegan_and_blocked_soy() -> None:
    context = _context(
        dietary_pattern="vegan",
        dietary_restrictions=["lactose_free", "gluten_free"],
        allergies=["soy"],
    )

    payload = build_fallback_recommendations(context)
    serialized = str(payload).casefold()

    assert "tofu" not in serialized
    assert recommendation_policy_issues(payload, context) == []


def test_invalid_provider_output_uses_deterministic_fallback() -> None:
    service = AITaskService()
    value = MealRecommendationsInput.model_validate(_context())

    with patch.object(service, "_invoke", side_effect=ValueError("invalid structured result")):
        result = service._meal_recommendations(value, run_id="run-id")

    assert len(result.meals) == 3
    assert result._resolution_mode == "deterministic_fallback"
    assert result._fallback_reason == "structured_output:ValueError"


def test_provider_constraint_violation_uses_safe_fallback() -> None:
    service = AITaskService()
    value = MealRecommendationsInput.model_validate(
        _context(dietary_pattern="vegan", dietary_restrictions=["lactose_free"])
    )
    invalid = {
        "meals": [
            {
                "name": f"Milk chicken option {index}",
                "description": "Contains milk and chicken",
                "calories": 500,
                "protein_g": 40,
                "carbs_g": 50,
                "fat_g": 15,
                "prep_time": "10 min",
                "estimated_price_rub": 300,
                "ingredients": ["milk", "chicken"],
            }
            for index in range(3)
        ]
    }

    with patch.object(service, "_invoke", return_value=invalid):
        result = service._meal_recommendations(value, run_id="run-id")

    payload = result.model_dump(mode="json")
    assert recommendation_policy_issues(payload, value.model_dump(mode="json")) == []
    assert result._resolution_mode == "deterministic_fallback"


def test_provider_food_alias_violation_is_detected() -> None:
    context = _context(allergies=["fish"])
    payload = {"meals": [{"name": "Лосось"}]}

    assert "blocked_food_tag:fish" in recommendation_policy_issues(payload, context)
