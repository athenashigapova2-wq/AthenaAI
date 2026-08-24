from __future__ import annotations

from app.agents.nutrition.constraints import NutritionConstraintEngine
from app.agents.nutrition.grounding import _alternative_plan_candidates
from app.agents.nutrition_validation import GroundedIngredient, GroundedMeal


def _meal(name: str, food: str, grams: float = 100.0) -> GroundedMeal:
    ingredient = GroundedIngredient(
        display_name=food,
        reference_food=food,
        matched_food=food,
        grams=grams,
        calories_per_100g=100,
        protein_per_100g=10,
        fat_per_100g=2,
        carbs_per_100g=10,
        calories=100,
        protein_g=10,
        fat_g=2,
        carbs_g=10,
    )
    return GroundedMeal(
        name=name,
        ingredients=[ingredient],
        calories=100,
        protein_g=10,
        fat_g=2,
        carbs_g=10,
    )


def _stage(report, name: str):
    return next(stage for stage in report.stages if stage.name == name)


def test_constraint_engine_runs_hard_stages_in_stable_order() -> None:
    report = NutritionConstraintEngine().validate(
        [_meal("Breakfast", "egg raw", grams=10)],
        None,
        {
            "allergies": ["eggs"],
            "dietary_pattern": "vegan",
            "disliked_foods": ["egg"],
            "budget": "medium",
        },
    )

    assert [stage.name for stage in report.stages[:6]] == [
        "allergy_validator",
        "dietary_restriction_validator",
        "disliked_food_validator",
        "budget_validator",
        "nutrition_target_validator",
        "portion_feasibility_validator",
    ]
    assert not _stage(report, "allergy_validator").passed
    assert not _stage(report, "dietary_restriction_validator").passed
    assert not _stage(report, "disliked_food_validator").passed
    assert not _stage(report, "portion_feasibility_validator").passed
    assert not report.accepted


def test_dietary_patterns_and_restrictions_are_enforced_deterministically() -> None:
    meals = [
        _meal("Breakfast", "greek yogurt"),
        _meal("Lunch", "chicken breast raw"),
        _meal("Dinner", "cod cooked"),
    ]
    engine = NutritionConstraintEngine()

    vegan = engine.validate(meals, None, {"dietary_pattern": "vegan"})
    vegetarian = engine.validate(meals, None, {"dietary_pattern": "vegetarian"})
    pescatarian = engine.validate(meals, None, {"dietary_pattern": "pescatarian"})
    lactose_free = engine.validate(
        meals,
        None,
        {"dietary_pattern": "omnivore", "dietary_restrictions": ["lactose_free"]},
    )

    assert not _stage(vegan, "dietary_restriction_validator").passed
    assert not _stage(vegetarian, "dietary_restriction_validator").passed
    assert not _stage(pescatarian, "dietary_restriction_validator").passed
    assert not _stage(lactose_free, "dietary_restriction_validator").passed


def test_low_budget_and_gluten_free_rules_fail_closed() -> None:
    meals = [
        _meal("Breakfast", "oats"),
        _meal("Lunch", "salmon raw"),
        _meal("Dinner", "spinach raw"),
    ]
    report = NutritionConstraintEngine().validate(
        meals,
        None,
        {
            "dietary_pattern": "omnivore",
            "dietary_restrictions": ["gluten_free"],
            "budget": "low",
        },
    )

    assert not _stage(report, "dietary_restriction_validator").passed
    assert not _stage(report, "budget_validator").passed


def test_fallback_candidates_prioritize_profile_dietary_pattern() -> None:
    vegetarian = _alternative_plan_candidates(
        "en",
        low_budget=False,
        dietary_pattern="vegetarian",
    )
    vegan = _alternative_plan_candidates(
        "en",
        low_budget=True,
        dietary_pattern="vegan",
    )
    pescatarian = _alternative_plan_candidates(
        "en",
        low_budget=False,
        dietary_pattern="pescatarian",
    )

    assert vegetarian[0][0] == "vegetarian"
    assert vegan[0][0] == "vegan"
    assert pescatarian[0][0] == "pescatarian"

    vegan_foods = {
        str(ingredient.reference_food) for meal in vegan[0][1] for ingredient in meal.ingredients
    }
    assert not vegan_foods & {
        "egg raw",
        "greek yogurt",
        "yogurt",
        "cottage cheese nonfat",
        "chicken breast raw",
        "turkey breast roasted",
        "beef tenderloin steak cooked",
        "cod cooked",
        "salmon raw",
    }
