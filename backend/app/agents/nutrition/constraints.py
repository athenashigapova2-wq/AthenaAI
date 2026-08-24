"""Nutrition request classification and deterministic plan constraints."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

from app.agents.nutrition_validation import (
    FoodDiversityAssessment,
    GroundedMeal,
    GroundedMealPlanItem,
    NutritionNumbers,
    assess_food_diversity,
    portion_feasibility_issues,
    validate_nutrition_numbers,
)

DIETARY_PATTERNS = frozenset({"omnivore", "vegetarian", "vegan", "pescatarian"})
DIETARY_RESTRICTIONS = frozenset({"halal", "kosher", "lactose_free", "gluten_free"})

_MEAT_TERMS = frozenset(
    {"chicken", "turkey", "beef", "pork", "lamb", "куриц", "индей", "говядин", "свинин", "баранин"}
)
_FISH_TERMS = frozenset({"cod", "salmon", "tuna", "fish", "треск", "лосос", "тун", "рыб"})
_DAIRY_TERMS = frozenset(
    {"milk", "yogurt", "cottage cheese", "cheese", "молок", "йогурт", "творог", "сыр"}
)
_EGG_TERMS = frozenset({"egg", "яйц"})
_GLUTEN_RISK_TERMS = frozenset({"oats", "wheat", "barley", "rye", "овся", "пшениц", "ячмен", "рож"})
_LOW_BUDGET_PREMIUM_TERMS = frozenset(
    {"salmon", "beef tenderloin", "turkey breast", "лосос", "говяжья вырезка", "грудка индейки"}
)

_ALLERGY_ALIASES: dict[str, frozenset[str]] = {
    "milk": _DAIRY_TERMS,
    "dairy": _DAIRY_TERMS,
    "молоко": _DAIRY_TERMS,
    "лактоза": _DAIRY_TERMS,
    "egg": _EGG_TERMS,
    "eggs": _EGG_TERMS,
    "яйца": _EGG_TERMS,
    "fish": _FISH_TERMS,
    "рыба": _FISH_TERMS,
    "peanut": frozenset({"peanut", "арахис"}),
    "peanuts": frozenset({"peanut", "арахис"}),
    "арахис": frozenset({"peanut", "арахис"}),
    "apple": frozenset({"apple", "яблок"}),
    "apples": frozenset({"apple", "яблок"}),
    "яблоки": frozenset({"apple", "яблок"}),
    "nuts": frozenset({"nut", "almond", "hazelnut", "орех", "миндал", "фундук"}),
    "hazelnuts": frozenset({"hazelnut", "фундук"}),
}


@dataclass(frozen=True)
class ConstraintStageResult:
    name: str
    passed: bool
    issues: tuple[str, ...]


@dataclass(frozen=True)
class PlanConstraintReport:
    accepted: bool
    stages: tuple[ConstraintStageResult, ...]
    computed: NutritionNumbers
    diversity: FoodDiversityAssessment

    @property
    def issues(self) -> tuple[str, ...]:
        return tuple(issue for stage in self.stages for issue in stage.issues)


def _normalized_values(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _meal_text(meal: GroundedMeal | GroundedMealPlanItem) -> str:
    ingredients = " ".join(
        str(getattr(item, "matched_food", None) or item.reference_food) for item in meal.ingredients
    )
    return f"{meal.name} {ingredients}".lower()


def _matching_issues(
    meals: Sequence[GroundedMeal | GroundedMealPlanItem],
    terms: set[str],
    message: str,
) -> list[str]:
    issues: list[str] = []
    normalized_terms = {term.strip().lower() for term in terms if term.strip()}
    for index, meal in enumerate(meals, start=1):
        text = _meal_text(meal)
        matched = sorted(term for term in normalized_terms if term in text)
        if matched:
            issues.append(f"meal {index} {message}: {', '.join(matched)}")
    return issues


def _expanded_profile_terms(values: list[str]) -> set[str]:
    return {
        term for value in values for term in _ALLERGY_ALIASES.get(value, frozenset({value})) if term
    }


def _allergen_issues(
    meals: Sequence[GroundedMeal | GroundedMealPlanItem],
    forbidden_terms: set[str],
) -> list[str]:
    """Compatibility wrapper for callers that already expanded allergy terms."""
    return _matching_issues(meals, forbidden_terms, "may contain a profile allergen")


def _dietary_restriction_issues(
    meals: list[GroundedMeal],
    pattern: str,
    restrictions: set[str],
) -> list[str]:
    forbidden: set[str] = set()
    if pattern == "vegetarian":
        forbidden.update(_MEAT_TERMS | _FISH_TERMS)
    elif pattern == "vegan":
        forbidden.update(_MEAT_TERMS | _FISH_TERMS | _DAIRY_TERMS | _EGG_TERMS)
    elif pattern == "pescatarian":
        forbidden.update(_MEAT_TERMS)
    if "lactose_free" in restrictions:
        forbidden.update(_DAIRY_TERMS)
    if "gluten_free" in restrictions:
        # Ordinary oats are not treated as certified gluten-free.
        forbidden.update(_GLUTEN_RISK_TERMS)
    if restrictions & {"halal", "kosher"}:
        # The catalogue has no certification metadata, so meat fails closed.
        forbidden.update(_MEAT_TERMS)
    return _matching_issues(meals, forbidden, "violates dietary restrictions")


def _budget_issues(meals: list[GroundedMeal], budget: str) -> list[str]:
    if budget != "low":
        return []
    return _matching_issues(meals, set(_LOW_BUDGET_PREMIUM_TERMS), "violates low-budget policy")


def _numbers(meals: list[GroundedMeal]) -> tuple[list[NutritionNumbers], NutritionNumbers]:
    rows = [
        NutritionNumbers(
            calories=meal.calories,
            protein_g=meal.protein_g,
            fat_g=meal.fat_g,
            carbs_g=meal.carbs_g,
        )
        for meal in meals
    ]
    return rows, NutritionNumbers(
        calories=sum(row.calories for row in rows),
        protein_g=sum(row.protein_g for row in rows),
        fat_g=sum(row.fat_g for row in rows),
        carbs_g=sum(row.carbs_g for row in rows),
    )


class NutritionConstraintEngine:
    """Run hard plan checks in stable order without consulting an LLM."""

    def validate(
        self,
        meals: list[GroundedMeal],
        targets: NutritionNumbers | None,
        profile: dict[str, Any],
    ) -> PlanConstraintReport:
        pattern = str(profile.get("dietary_pattern") or "omnivore").strip().lower()
        if pattern not in DIETARY_PATTERNS:
            pattern = "omnivore"
        restrictions = set(_normalized_values(profile.get("dietary_restrictions")))
        allergies = _normalized_values(profile.get("allergies"))
        disliked = _normalized_values(profile.get("disliked_foods"))
        rows, computed = _numbers(meals)
        diversity = assess_food_diversity(meals)

        validators: tuple[tuple[str, Callable[[], list[str] | tuple[str, ...]]], ...] = (
            (
                "allergy_validator",
                lambda: _matching_issues(
                    meals, _expanded_profile_terms(allergies), "may contain a profile allergen"
                ),
            ),
            (
                "dietary_restriction_validator",
                lambda: _dietary_restriction_issues(meals, pattern, restrictions),
            ),
            (
                "disliked_food_validator",
                lambda: _matching_issues(
                    meals, _expanded_profile_terms(disliked), "contains a disliked food"
                ),
            ),
            (
                "budget_validator",
                lambda: _budget_issues(meals, str(profile.get("budget") or "medium").lower()),
            ),
            (
                "nutrition_target_validator",
                lambda: validate_nutrition_numbers(rows, computed, targets).issues,
            ),
            ("portion_feasibility_validator", lambda: portion_feasibility_issues(meals)),
            ("food_diversity_validator", lambda: diversity.issues),
        )
        stages = tuple(
            ConstraintStageResult(name=name, passed=not (issues := tuple(check())), issues=issues)
            for name, check in validators
        )
        return PlanConstraintReport(
            accepted=all(stage.passed for stage in stages),
            stages=stages,
            computed=computed,
            diversity=diversity,
        )


def constraint_report_payload(report: PlanConstraintReport) -> dict[str, Any]:
    return {
        "accepted": report.accepted,
        "stages": [
            {"name": stage.name, "passed": stage.passed, "issues": list(stage.issues)}
            for stage in report.stages
        ],
    }


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
