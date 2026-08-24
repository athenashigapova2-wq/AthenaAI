"""Deterministic validation for generated full-day nutrition plans."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from scipy.optimize import lsq_linear

from app.tools.nutrition import PLAN_FOOD_REFERENCE_NAMES


_RU_FOOD_NAMES = {
    "oats": "овсяные хлопья",
    "egg raw": "яйцо",
    "greek yogurt": "греческий йогурт",
    "yogurt": "йогурт",
    "banana": "банан",
    "cottage cheese nonfat": "обезжиренный творог",
    "chicken breast raw": "куриная грудка",
    "turkey breast roasted": "запечённая грудка индейки",
    "beef tenderloin steak cooked": "приготовленная говяжья вырезка",
    "cod cooked": "приготовленная треска",
    "salmon raw": "лосось",
    "white rice cooked": "варёный белый рис",
    "white rice raw": "белый рис",
    "buckwheat raw": "гречневая крупа",
    "potato raw": "картофель",
    "cucumber": "огурец",
    "carrots raw": "морковь",
    "broccoli cooked": "приготовленная брокколи",
    "spinach raw": "шпинат",
    "vegetable salad": "овощной салат",
    "olive oil": "оливковое масло",
}


_NUMBER = r"(\d+(?:[.,]\d+)?)"
_MEAL_PATTERN = re.compile(
    rf"\[MEAL_KBJU\s+kcal={_NUMBER}\s+protein={_NUMBER}"
    rf"\s+fat={_NUMBER}\s+carbs={_NUMBER}\s*\]",
    flags=re.IGNORECASE,
)
_TOTAL_PATTERN = re.compile(
    rf"\[TOTAL_KBJU\s+kcal={_NUMBER}\s+protein={_NUMBER}"
    rf"\s+fat={_NUMBER}\s+carbs={_NUMBER}\s*\]",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class NutritionNumbers:
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float


@dataclass(frozen=True)
class NutritionPlanValidation:
    valid: bool
    issues: tuple[str, ...]
    meal_count: int
    summed: NutritionNumbers | None
    declared: NutritionNumbers | None


class MealPlanItem(BaseModel):
    """One meal submitted by the model for deterministic validation."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    calories: float = Field(ge=20, le=2_000)
    protein_g: float = Field(ge=0, le=250)
    fat_g: float = Field(ge=0, le=250)
    carbs_g: float = Field(ge=0, le=250)


PlanFoodReference = StrEnum(  # type: ignore[misc]
    "PlanFoodReference",
    {
        f"food_{index}": food_name
        for index, food_name in enumerate(PLAN_FOOD_REFERENCE_NAMES, start=1)
    },
)


class MealIngredient(BaseModel):
    """A concrete ingredient and portion that can be checked against the food DB."""

    reference_food: PlanFoodReference
    grams: float = Field(gt=0, le=1_500)


class GroundedMealPlanItem(BaseModel):
    """A meal whose nutrients must be derived from database-backed ingredients."""

    name: str = Field(min_length=1, max_length=120)
    ingredients: list[MealIngredient] = Field(min_length=1, max_length=12)


class FoodNutrientReference(BaseModel):
    """Canonical food nutrient values stored per 100 grams."""

    food_name: str
    calories_per_100g: float = Field(ge=0, le=900)
    protein_g: float = Field(ge=0, le=100)
    fat_g: float = Field(ge=0, le=100)
    carbs_g: float = Field(ge=0, le=100)


class GroundedIngredient(BaseModel):
    display_name: str
    reference_food: str
    matched_food: str
    grams: float
    calories_per_100g: float
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float


class GroundedMeal(BaseModel):
    name: str
    ingredients: list[GroundedIngredient]
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float


@dataclass(frozen=True)
class FoodDiversityAssessment:
    """Deterministic, user-independent diversity metrics for one daily plan."""

    score: int
    unique_foods: int
    total_ingredients: int
    protein_sources: int
    plant_foods: int
    duplicate_meals: int
    repeated_foods: tuple[str, ...]
    issues: tuple[str, ...]


def _meal_target_rows(targets: NutritionNumbers) -> list[NutritionNumbers]:
    """Split daily targets into five exact, model-friendly meal rows."""
    weights = (0.25, 0.10, 0.30, 0.10)
    rows: list[NutritionNumbers] = []
    for weight in weights:
        protein = round(targets.protein_g * weight, 1)
        fat = round(targets.fat_g * weight, 1)
        carbs = round(targets.carbs_g * weight, 1)
        rows.append(
            NutritionNumbers(
                calories=round(protein * 4 + fat * 9 + carbs * 4, 1),
                protein_g=protein,
                fat_g=fat,
                carbs_g=carbs,
            )
        )

    protein = round(targets.protein_g - sum(row.protein_g for row in rows), 1)
    fat = round(targets.fat_g - sum(row.fat_g for row in rows), 1)
    carbs = round(targets.carbs_g - sum(row.carbs_g for row in rows), 1)
    rows.append(
        NutritionNumbers(
            calories=round(protein * 4 + fat * 9 + carbs * 4, 1),
            protein_g=protein,
            fat_g=fat,
            carbs_g=carbs,
        )
    )
    return rows


def nutrition_plan_contract(
    targets: NutritionNumbers | None = None,
    forbidden_ingredients: list[str] | None = None,
    allowed_reference_foods: list[str] | None = None,
) -> str:
    """Return the machine-checkable contract added to meal-plan prompts."""
    contract = (
        "For a complete daily meal plan you MUST call submit_daily_nutrition_plan. "
        "For every meal provide concrete ingredients. Each ingredient needs reference_food "
        "(a precise English food name for database lookup, including cooked/raw "
        "state), and grams. Never provide calories or macros yourself: the server derives them "
        "from food_nutrients values per 100 g and rejects unknown foods or a plan that misses "
        "the profile targets. The server derives the displayed product name from the matched "
        "food_nutrients row; do not provide a display name. Do not answer with a prose plan "
        "without submitting it to this tool."
    )
    if allowed_reference_foods:
        contract += (
            " Every reference_food MUST be copied exactly from this verified catalogue; "
            "use separate ingredients instead of composite dish names: "
            f"{', '.join(allowed_reference_foods)}. "
            "Use this practical meal order: meal 1 breakfast (oats/egg/yogurt/banana/"
            "cottage cheese); meal 2 snack (yogurt/banana/cottage cheese); meal 3 lunch "
            "(one meat or fish, one rice/buckwheat/potato, vegetables, optional oil); "
            "meal 4 snack (yogurt/banana/cottage cheese); meal 5 dinner (one meat or "
            "fish, one rice/buckwheat/potato, vegetables, optional oil). Do not put meat "
            "or fish into a snack. Use different food combinations for meals 2 and 4. "
            "The server enforces practical household portions and rejects plans with "
            "fewer than four different foods or the same food in more than two meals."
        )
    if targets is not None:
        rows = _meal_target_rows(targets)
        row_text = "; ".join(
            f"meal {index}: calories={row.calories:g}, protein_g={row.protein_g:g}, "
            f"fat_g={row.fat_g:g}, carbs_g={row.carbs_g:g}"
            for index, row in enumerate(rows, start=1)
        )
        contract += (
            " Use exactly five meals. Choose database-searchable foods and gram portions whose "
            f"calculated values are close to these per-meal targets: {row_text}."
        )
    if forbidden_ingredients:
        contract += (
            " Never include these ingredients or close variants in a meal name or "
            f"description: {', '.join(forbidden_ingredients)}."
        )
    return contract


def ground_meal_plan(
    meals: list[GroundedMealPlanItem],
    resolver: Any,
    locale: str = "en",
) -> tuple[list[GroundedMeal], tuple[str, ...]]:
    """Resolve ingredients and calculate every nutrition value from DB rows."""
    grounded_meals: list[GroundedMeal] = []
    issues: list[str] = []
    for meal_index, meal in enumerate(meals, start=1):
        grounded_ingredients: list[GroundedIngredient] = []
        for ingredient_index, ingredient in enumerate(meal.ingredients, start=1):
            try:
                raw_reference = resolver(ingredient.reference_food)
                reference = (
                    raw_reference
                    if isinstance(raw_reference, FoodNutrientReference)
                    else FoodNutrientReference.model_validate(raw_reference)
                )
            except Exception as exc:
                issues.append(
                    f"meal {meal_index} ingredient {ingredient_index} was not found "
                    f"in food_nutrients: {ingredient.reference_food} ({type(exc).__name__})"
                )
                continue

            factor = ingredient.grams / 100.0
            grounded_ingredients.append(
                GroundedIngredient(
                    display_name=_display_name_from_matched_food(
                        reference.food_name,
                        locale,
                    ),
                    reference_food=ingredient.reference_food,
                    matched_food=reference.food_name,
                    grams=round(ingredient.grams, 1),
                    calories_per_100g=round(reference.calories_per_100g, 1),
                    protein_per_100g=round(reference.protein_g, 1),
                    fat_per_100g=round(reference.fat_g, 1),
                    carbs_per_100g=round(reference.carbs_g, 1),
                    calories=round(reference.calories_per_100g * factor, 1),
                    protein_g=round(reference.protein_g * factor, 1),
                    fat_g=round(reference.fat_g * factor, 1),
                    carbs_g=round(reference.carbs_g * factor, 1),
                )
            )

        if not grounded_ingredients:
            issues.append(f"meal {meal_index} has no database-verified ingredients")
            continue
        grounded_meals.append(
            GroundedMeal(
                name=meal.name,
                ingredients=grounded_ingredients,
                calories=round(sum(item.calories for item in grounded_ingredients), 1),
                protein_g=round(sum(item.protein_g for item in grounded_ingredients), 1),
                fat_g=round(sum(item.fat_g for item in grounded_ingredients), 1),
                carbs_g=round(sum(item.carbs_g for item in grounded_ingredients), 1),
            )
        )
    return grounded_meals, tuple(issues)


def _display_name_from_matched_food(matched_food: str, locale: str = "en") -> str:
    """Build the user-visible product name only from the canonical database match."""
    normalized = re.sub(r"\s+", " ", matched_food.replace("_", " ")).strip()
    if not normalized:
        raise ValueError("matched food name is empty")
    if locale == "ru":
        display_name = _RU_FOOD_NAMES.get(normalized.lower())
        if display_name is None:
            display_name = re.sub(
                r"\b(?:raw|cooked|roasted)\b",
                "",
                normalized,
                flags=re.IGNORECASE,
            )
            display_name = re.sub(r"\s+", " ", display_name).strip()
    else:
        display_name = normalized
    return display_name[0].upper() + display_name[1:]


def _portion_bounds(ingredient: GroundedIngredient) -> tuple[float, float]:
    """Return practical household portion bounds for one catalogue food."""
    name = ingredient.matched_food.lower()
    if "oil" in name:
        return 5.0, 25.0
    if any(term in name for term in ("oats", "rice raw", "buckwheat raw")):
        return 30.0, 150.0
    if "rice cooked" in name:
        return 80.0, 300.0
    if "potato" in name:
        return 100.0, 450.0
    if "spinach" in name:
        return 30.0, 250.0
    if any(term in name for term in ("vegetable", "cucumber", "carrot", "broccoli")):
        return 50.0, 250.0
    if any(term in name for term in ("yogurt", "cottage cheese")):
        return 100.0, 300.0
    if "banana" in name:
        return 80.0, 250.0
    if "egg" in name:
        return 50.0, 200.0
    if any(term in name for term in ("chicken", "turkey", "beef", "cod", "salmon")):
        return 80.0, 250.0
    return 50.0, 250.0


def assess_food_diversity(meals: list[GroundedMeal]) -> FoodDiversityAssessment:
    """Score catalogue-food variety without asking the model to self-evaluate."""
    names = [
        ingredient.matched_food.strip().lower()
        for meal in meals
        for ingredient in meal.ingredients
    ]
    counts = Counter(names)
    unique_names = set(counts)
    meal_food_sets = [
        {
            ingredient.matched_food.strip().lower()
            for ingredient in meal.ingredients
        }
        for meal in meals
    ]
    meal_presence = Counter(
        name
        for meal_foods in meal_food_sets
        for name in meal_foods
    )
    meal_compositions = Counter(
        tuple(sorted(meal_foods))
        for meal_foods in meal_food_sets
        if meal_foods
    )
    protein_terms = (
        "egg",
        "yogurt",
        "cottage cheese",
        "chicken",
        "turkey",
        "beef",
        "cod",
        "salmon",
    )
    plant_terms = (
        "oats",
        "banana",
        "rice",
        "buckwheat",
        "potato",
        "cucumber",
        "carrot",
        "broccoli",
        "spinach",
        "vegetable",
    )
    protein_sources = sum(
        any(term in name for term in protein_terms) for name in unique_names
    )
    plant_foods = sum(any(term in name for term in plant_terms) for name in unique_names)
    repeated = tuple(
        sorted(name for name, count in meal_presence.items() if count > 2)
    )
    duplicate_meals = sum(
        count - 1 for count in meal_compositions.values() if count > 1
    )
    unique_foods = len(unique_names)
    score = round(
        50 * min(unique_foods / 10, 1)
        + 25 * min(protein_sources / 3, 1)
        + 25 * min(plant_foods / 5, 1)
        - 10 * duplicate_meals
    )
    score = max(0, min(100, score))
    issues: list[str] = []
    if unique_foods < 4:
        issues.append("a daily plan must contain at least four different foods")
    if repeated:
        issues.append(
            "the same food may not appear in more than two meals: "
            + ", ".join(repeated)
        )
    return FoodDiversityAssessment(
        score=score,
        unique_foods=unique_foods,
        total_ingredients=len(names),
        protein_sources=protein_sources,
        plant_foods=plant_foods,
        duplicate_meals=duplicate_meals,
        repeated_foods=repeated,
        issues=tuple(issues),
    )


def fit_grounded_meal_portions(
    meals: list[GroundedMeal],
    targets: NutritionNumbers,
) -> tuple[list[GroundedMeal], tuple[str, ...]]:
    """Fit ingredient grams to profile targets without asking the LLM to do math.

    The model still chooses foods and meal grouping. A bounded least-squares fit
    changes only portions, prioritising daily calories/macros and secondarily keeping
    the five meals near the configured energy split.
    """
    flat = [ingredient for meal in meals for ingredient in meal.ingredients]
    if not flat:
        return meals, ("no database-grounded ingredients are available for portion fitting",)

    target_values = (
        targets.calories,
        targets.protein_g,
        targets.fat_g,
        targets.carbs_g,
    )
    if any(value <= 0 for value in target_values):
        return meals, ("profile targets must be positive for portion fitting",)

    # Each coefficient is a nutrient contribution per gram, normalised by its
    # target. Macro rows receive the highest weight. Energy rows per meal keep the
    # result usable instead of concentrating the whole day in one meal.
    nutrient_rows: list[list[float]] = []
    for attribute, target in zip(
        ("calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g"),
        target_values,
    ):
        nutrient_rows.append(
            [3.0 * float(getattr(item, attribute)) / 100.0 / target for item in flat]
        )
    expected_meals = _meal_target_rows(targets)
    meal_rows: list[list[float]] = []
    offset = 0
    for meal_index, meal in enumerate(meals):
        meal_target = expected_meals[min(meal_index, len(expected_meals) - 1)].calories
        row = [0.0] * len(flat)
        for local_index, ingredient in enumerate(meal.ingredients):
            row[offset + local_index] = (
                0.35 * ingredient.calories_per_100g / 100.0 / meal_target
            )
        meal_rows.append(row)
        offset += len(meal.ingredients)

    matrix = [*nutrient_rows, *meal_rows]
    expected = [3.0] * len(nutrient_rows) + [0.35] * len(meal_rows)
    bounds = [_portion_bounds(item) for item in flat]
    try:
        fit = lsq_linear(
            matrix,
            expected,
            bounds=(
                [item[0] for item in bounds],
                [item[1] for item in bounds],
            ),
            lsmr_tol="auto",
            max_iter=500,
        )
    except Exception as exc:
        return meals, (f"portion fitting failed: {type(exc).__name__}",)
    if not fit.success:
        return meals, (f"portion fitting did not converge: {fit.message}",)

    fitted_meals: list[GroundedMeal] = []
    value_index = 0
    for meal in meals:
        fitted_ingredients: list[GroundedIngredient] = []
        for ingredient in meal.ingredients:
            grams = round(float(fit.x[value_index]), 1)
            value_index += 1
            factor = grams / 100.0
            fitted_ingredients.append(
                ingredient.model_copy(
                    update={
                        "grams": grams,
                        "calories": round(ingredient.calories_per_100g * factor, 1),
                        "protein_g": round(ingredient.protein_per_100g * factor, 1),
                        "fat_g": round(ingredient.fat_per_100g * factor, 1),
                        "carbs_g": round(ingredient.carbs_per_100g * factor, 1),
                    }
                )
            )
        fitted_meals.append(
            GroundedMeal(
                name=meal.name,
                ingredients=fitted_ingredients,
                calories=round(sum(item.calories for item in fitted_ingredients), 1),
                protein_g=round(sum(item.protein_g for item in fitted_ingredients), 1),
                fat_g=round(sum(item.fat_g for item in fitted_ingredients), 1),
                carbs_g=round(sum(item.carbs_g for item in fitted_ingredients), 1),
            )
        )
    return fitted_meals, ()


def render_grounded_plan(
    introduction: str,
    meals: list[GroundedMeal],
    totals: NutritionNumbers,
    notes: str,
    locale: str,
) -> str:
    """Render only user-facing ingredients and server-calculated values."""
    lines = [introduction.strip()]
    for meal in meals:
        ingredients = "; ".join(
            f"{item.display_name} — {item.grams:g} г"
            for item in meal.ingredients
        )
        if locale == "ru":
            nutrition = (
                f"{meal.calories:g} ккал; Б {meal.protein_g:g} г; "
                f"Ж {meal.fat_g:g} г; У {meal.carbs_g:g} г"
            )
        else:
            nutrition = (
                f"{meal.calories:g} kcal; protein {meal.protein_g:g} g; "
                f"fat {meal.fat_g:g} g; carbs {meal.carbs_g:g} g"
            )
        lines.append(f"\n**{meal.name}:** {ingredients}\n({nutrition})")

    if locale == "ru":
        lines.append(
            f"\n**Итого:** {totals.calories:g} ккал; Б {totals.protein_g:g} г; "
            f"Ж {totals.fat_g:g} г; У {totals.carbs_g:g} г"
        )
    else:
        lines.append(
            f"\n**Total:** {totals.calories:g} kcal; protein {totals.protein_g:g} g; "
            f"fat {totals.fat_g:g} g; carbs {totals.carbs_g:g} g"
        )
    lines.append(f"\n{notes.strip()}")
    return "\n".join(lines).strip()


def targets_from_profile_result(result: Any) -> NutritionNumbers | None:
    """Extract targets from the bound profile-tool response."""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    profile = result.get("profile")
    if not isinstance(profile, dict):
        return None
    keys = (
        "calorie_target",
        "protein_target_g",
        "fat_target_g",
        "carb_target_g",
    )
    if any(profile.get(key) is None for key in keys):
        return None
    try:
        return NutritionNumbers(
            calories=float(profile["calorie_target"]),
            protein_g=float(profile["protein_target_g"]),
            fat_g=float(profile["fat_target_g"]),
            carbs_g=float(profile["carb_target_g"]),
        )
    except (TypeError, ValueError):
        return None


def _numbers(groups: Sequence[str | Any]) -> NutritionNumbers:
    values = [float(item.replace(",", ".")) for item in groups]
    return NutritionNumbers(values[0], values[1], values[2], values[3])


def _sum_meals(meals: list[NutritionNumbers]) -> NutritionNumbers:
    return NutritionNumbers(
        calories=sum(item.calories for item in meals),
        protein_g=sum(item.protein_g for item in meals),
        fat_g=sum(item.fat_g for item in meals),
        carbs_g=sum(item.carbs_g for item in meals),
    )


def validate_nutrition_numbers(
    meals: list[NutritionNumbers],
    declared: NutritionNumbers | None,
    targets: NutritionNumbers | None,
) -> NutritionPlanValidation:
    """Validate already structured meal numbers."""
    summed = _sum_meals(meals) if meals else None
    issues: list[str] = []

    if len(meals) < 3:
        issues.append("at least three meals are required")
    if declared is None:
        issues.append("declared daily totals are required")

    for index, meal in enumerate(meals, start=1):
        if not 20 <= meal.calories <= 2_000:
            issues.append(f"meal {index} calories are outside a plausible range")
        if any(value < 0 or value > 250 for value in (meal.protein_g, meal.fat_g, meal.carbs_g)):
            issues.append(f"meal {index} macros are outside a plausible range")

    if summed is not None and declared is not None:
        comparisons = (
            ("calories", summed.calories, declared.calories, 5.0),
            ("protein", summed.protein_g, declared.protein_g, max(2.0, len(meals) * 0.5)),
            ("fat", summed.fat_g, declared.fat_g, max(2.0, len(meals) * 0.5)),
            ("carbs", summed.carbs_g, declared.carbs_g, max(2.0, len(meals) * 0.5)),
        )
        for name, actual, expected, tolerance in comparisons:
            if not _close(actual, expected, tolerance):
                issues.append(f"declared {name} does not equal the meal sum")

        macro_calories = (
            declared.protein_g * 4
            + declared.fat_g * 9
            + declared.carbs_g * 4
        )
        if not _close(
            macro_calories,
            declared.calories,
            max(100.0, declared.calories * 0.12),
        ):
            issues.append("declared calories are inconsistent with declared macros")

    if declared is not None and targets is not None:
        target_comparisons = (
            ("calories", declared.calories, targets.calories, max(100.0, targets.calories * 0.08)),
            ("protein", declared.protein_g, targets.protein_g, max(8.0, targets.protein_g * 0.15)),
            ("fat", declared.fat_g, targets.fat_g, max(6.0, targets.fat_g * 0.15)),
            ("carbs", declared.carbs_g, targets.carbs_g, max(10.0, targets.carbs_g * 0.15)),
        )
        for name, actual, expected, tolerance in target_comparisons:
            if not _close(actual, expected, tolerance):
                issues.append(f"declared {name} does not match the profile target")

    return NutritionPlanValidation(
        valid=not issues,
        issues=tuple(issues),
        meal_count=len(meals),
        summed=summed,
        declared=declared,
    )


def _close(actual: float, expected: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


def validate_nutrition_plan(
    answer: str,
    targets: NutritionNumbers | None,
) -> NutritionPlanValidation:
    """Validate meal sums, declared total, macro energy and profile targets."""
    meals = [_numbers(match.groups()) for match in _MEAL_PATTERN.finditer(answer)]
    total_matches = list(_TOTAL_PATTERN.finditer(answer))
    declared = _numbers(total_matches[0].groups()) if len(total_matches) == 1 else None
    validation = validate_nutrition_numbers(meals, declared, targets)
    issues = list(validation.issues)
    if len(total_matches) != 1:
        issues = [
            issue for issue in issues if issue != "declared daily totals are required"
        ]
        issues.append("exactly one TOTAL_KBJU marker is required")
    if len(meals) < 3:
        issues = [issue for issue in issues if issue != "at least three meals are required"]
        issues.append("at least three MEAL_KBJU markers are required")
    return NutritionPlanValidation(
        valid=not issues,
        issues=tuple(issues),
        meal_count=validation.meal_count,
        summed=validation.summed,
        declared=validation.declared,
    )


def render_structured_plan(
    introduction: str,
    meals: list[MealPlanItem],
    totals: NutritionNumbers,
    notes: str | None,
    locale: str,
) -> str:
    """Render only values that have already passed deterministic validation."""
    lines = [introduction.strip()]
    for meal in meals:
        if locale == "ru":
            nutrition = (
                f"{meal.calories:g} ккал; Б {meal.protein_g:g} г; "
                f"Ж {meal.fat_g:g} г; У {meal.carbs_g:g} г"
            )
        else:
            nutrition = (
                f"{meal.calories:g} kcal; protein {meal.protein_g:g} g; "
                f"fat {meal.fat_g:g} g; carbs {meal.carbs_g:g} g"
            )
        lines.append(f"\n**{meal.name}:** {meal.description}\n({nutrition})")

    if locale == "ru":
        lines.append(
            f"\n**Итого:** {totals.calories:g} ккал; Б {totals.protein_g:g} г; "
            f"Ж {totals.fat_g:g} г; У {totals.carbs_g:g} г"
        )
    else:
        lines.append(
            f"\n**Total:** {totals.calories:g} kcal; protein {totals.protein_g:g} g; "
            f"fat {totals.fat_g:g} g; carbs {totals.carbs_g:g} g"
        )
    if notes:
        lines.append(f"\n{notes.strip()}")
    return "\n".join(lines).strip()


def render_validated_plan(answer: str, locale: str) -> str:
    """Replace internal markers with readable nutrition values."""
    def render_meal(match: re.Match[str]) -> str:
        values = _numbers(match.groups())
        if locale == "ru":
            return (
                f"({values.calories:g} ккал; Б {values.protein_g:g} г; "
                f"Ж {values.fat_g:g} г; У {values.carbs_g:g} г)"
            )
        return (
            f"({values.calories:g} kcal; protein {values.protein_g:g} g; "
            f"fat {values.fat_g:g} g; carbs {values.carbs_g:g} g)"
        )

    def render_total(match: re.Match[str]) -> str:
        values = _numbers(match.groups())
        prefix = "Итого" if locale == "ru" else "Total"
        if locale == "ru":
            return (
                f"{prefix}: {values.calories:g} ккал; Б {values.protein_g:g} г; "
                f"Ж {values.fat_g:g} г; У {values.carbs_g:g} г"
            )
        return (
            f"{prefix}: {values.calories:g} kcal; protein {values.protein_g:g} g; "
            f"fat {values.fat_g:g} g; carbs {values.carbs_g:g} g"
        )

    return _TOTAL_PATTERN.sub(render_total, _MEAL_PATTERN.sub(render_meal, answer))


def validation_failure_message(locale: str) -> str:
    """Fail closed instead of returning nutrition numbers that did not validate."""
    if locale == "ru":
        return (
            "Я не смогла надёжно сверить сумму калорий и БЖУ этого плана, поэтому "
            "не буду выдавать непроверенные цифры. Попробуйте запросить план ещё раз."
        )
    return (
        "I could not reliably verify this plan's calorie and macro totals, so I will not "
        "return unverified numbers. Please request the plan again."
    )
