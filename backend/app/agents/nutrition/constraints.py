"""Nutrition request classification and hard safety constraints."""

import re

from app.agents.nutrition_validation import GroundedMealPlanItem

def _allergen_issues(
    meals: list[GroundedMealPlanItem],
    forbidden_terms: set[str],
) -> list[str]:
    """Return profile-allergen violations for one normalized plan."""
    issues: list[str] = []
    for index, meal in enumerate(meals, start=1):
        ingredient_text = " ".join(
            str(ingredient.reference_food) for ingredient in meal.ingredients
        )
        meal_text = f"{meal.name} {ingredient_text}".lower()
        matched = sorted(term for term in forbidden_terms if term in meal_text)
        if matched:
            issues.append(
                f"meal {index} may contain a profile allergen: {', '.join(matched)}"
            )
    return issues

def _requires_weight_trend(message: str) -> bool:
    calorie_term = re.search(r"(?:калори|ккал|calorie|kcal)", message, re.IGNORECASE)
    change_term = re.search(
        r"(?:меня|измен|сниж|сниз|уменьш|повыш|увелич|коррект|adjust|change|reduce|increase)",
        message,
        re.IGNORECASE,
    )
    return bool(calorie_term and change_term)


def _requires_full_day_plan(message: str) -> bool:
    return bool(
        re.search(
            r"(?:план\s+питания|рацион\s+(?:на\s+)?(?:сегодня|день|сутки)|"
            r"меню\s+(?:на\s+)?(?:сегодня|день|сутки)|daily\s+(?:meal\s+)?plan|"
            r"meal\s+plan\s+for\s+(?:today|the\s+day))",
            message,
            re.IGNORECASE,
        )
    )
