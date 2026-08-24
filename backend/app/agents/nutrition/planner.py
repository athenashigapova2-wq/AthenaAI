"""Grounded, validated daily nutrition-plan submission."""

import logging
from typing import Any

from langchain_core.tools import StructuredTool

from app.agents.nutrition.constraints import _allergen_issues
from app.agents.nutrition.grounding import _alternative_plan_candidates
from app.agents.nutrition_validation import (
    GroundedMealPlanItem,
    NutritionNumbers,
    assess_food_diversity,
    fit_grounded_meal_portions,
    ground_meal_plan,
    nutrition_plan_contract,
    render_grounded_plan,
    validate_nutrition_numbers,
)
from app.tools.nutrition import PLAN_FOOD_REFERENCE_NAMES, lookup_food_reference

logger = logging.getLogger(__name__)

def _plan_submission_tool(
    targets: NutritionNumbers | None,
    locale: str,
    profile_result: Any,
    food_resolver: Any | None = None,
) -> StructuredTool:
    """Build the only allowed output path for a complete daily plan."""
    profile_data = (
        profile_result.get("profile", {})
        if isinstance(profile_result, dict) and profile_result.get("status") == "ok"
        else {}
    )
    allergies = [str(item).strip().lower() for item in profile_data.get("allergies") or []]
    allergy_aliases = {
        "peanuts": ("peanut", "арахис", "орех"),
        "peanut": ("peanut", "арахис", "орех"),
        "apples": ("apple", "яблок"),
        "apple": ("apple", "яблок"),
    }
    forbidden_terms = {
        term
        for allergy in allergies
        for term in allergy_aliases.get(allergy, (allergy,))
        if term
    }
    contract = nutrition_plan_contract(
        targets,
        sorted(forbidden_terms),
        list(PLAN_FOOD_REFERENCE_NAMES),
    )
    if str(profile_data.get("budget", "")).lower() == "low":
        contract += (
            " This profile requires a low-budget plan. Prefer oats, egg raw, chicken "
            "breast raw, white rice raw or buckwheat raw, potato raw, seasonal catalogue "
            "vegetables and small amounts of olive oil; prefer cod cooked over salmon raw."
        )
    reference_cache: dict[str, Any] = {}

    def resolve_food(query: str) -> Any:
        cache_key = query.strip().lower()
        if cache_key not in reference_cache:
            reference_cache[cache_key] = (food_resolver or lookup_food_reference)(query)
        return reference_cache[cache_key]

    def submit_daily_nutrition_plan(
        meals: list[GroundedMealPlanItem],
    ) -> dict[str, Any]:
        normalized_meals = [
            meal
            if isinstance(meal, GroundedMealPlanItem)
            else GroundedMealPlanItem.model_validate(meal)
            for meal in meals
        ]
        grounded_meals, grounding_issues = ground_meal_plan(
            normalized_meals,
            resolve_food,
            locale,
        )
        portion_issues: tuple[str, ...] = ()
        if not grounding_issues and targets is not None:
            grounded_meals, portion_issues = fit_grounded_meal_portions(
                grounded_meals,
                targets,
            )
        meal_numbers = [
            NutritionNumbers(
                calories=meal.calories,
                protein_g=meal.protein_g,
                fat_g=meal.fat_g,
                carbs_g=meal.carbs_g,
            )
            for meal in grounded_meals
        ]
        computed = NutritionNumbers(
            calories=sum(item.calories for item in meal_numbers),
            protein_g=sum(item.protein_g for item in meal_numbers),
            fat_g=sum(item.fat_g for item in meal_numbers),
            carbs_g=sum(item.carbs_g for item in meal_numbers),
        )
        validation = validate_nutrition_numbers(meal_numbers, computed, targets)
        diversity = assess_food_diversity(grounded_meals)
        allergen_issues = _allergen_issues(normalized_meals, forbidden_terms)
        issues = [
            *grounding_issues,
            *portion_issues,
            *validation.issues,
            *allergen_issues,
            *diversity.issues,
        ]
        selected_food_set = "model"
        attempted_alternatives: list[str] = []
        if issues and targets is not None:
            original_food_set = {
                str(ingredient.reference_food)
                for meal in normalized_meals
                for ingredient in meal.ingredients
            }
            budget_is_low = str(profile_data.get("budget", "")).lower() == "low"
            for candidate_name, candidate_meals in _alternative_plan_candidates(
                locale,
                low_budget=budget_is_low,
            ):
                candidate_food_set = {
                    str(ingredient.reference_food)
                    for meal in candidate_meals
                    for ingredient in meal.ingredients
                }
                if candidate_food_set == original_food_set:
                    continue
                attempted_alternatives.append(candidate_name)
                candidate_grounded, candidate_grounding_issues = ground_meal_plan(
                    candidate_meals,
                    resolve_food,
                    locale,
                )
                candidate_portion_issues: tuple[str, ...] = ()
                if not candidate_grounding_issues:
                    candidate_grounded, candidate_portion_issues = (
                        fit_grounded_meal_portions(candidate_grounded, targets)
                    )
                candidate_numbers = [
                    NutritionNumbers(
                        calories=meal.calories,
                        protein_g=meal.protein_g,
                        fat_g=meal.fat_g,
                        carbs_g=meal.carbs_g,
                    )
                    for meal in candidate_grounded
                ]
                candidate_computed = NutritionNumbers(
                    calories=sum(item.calories for item in candidate_numbers),
                    protein_g=sum(item.protein_g for item in candidate_numbers),
                    fat_g=sum(item.fat_g for item in candidate_numbers),
                    carbs_g=sum(item.carbs_g for item in candidate_numbers),
                )
                candidate_validation = validate_nutrition_numbers(
                    candidate_numbers,
                    candidate_computed,
                    targets,
                )
                candidate_diversity = assess_food_diversity(candidate_grounded)
                candidate_issues = [
                    *candidate_grounding_issues,
                    *candidate_portion_issues,
                    *candidate_validation.issues,
                    *_allergen_issues(candidate_meals, forbidden_terms),
                    *candidate_diversity.issues,
                ]
                if candidate_issues:
                    continue

                logger.info(
                    "Server replaced incompatible nutrition food set: template=%s original=%s",
                    candidate_name,
                    sorted(original_food_set),
                )
                normalized_meals = candidate_meals
                grounded_meals = candidate_grounded
                meal_numbers = candidate_numbers
                computed = candidate_computed
                validation = candidate_validation
                diversity = candidate_diversity
                grounding_issues = ()
                portion_issues = ()
                allergen_issues = []
                issues = []
                selected_food_set = f"server:{candidate_name}"
                break
        if issues:
            adjustments = (
                {
                    "calories": round(targets.calories - computed.calories, 1),
                    "protein_g": round(targets.protein_g - computed.protein_g, 1),
                    "fat_g": round(targets.fat_g - computed.fat_g, 1),
                    "carbs_g": round(targets.carbs_g - computed.carbs_g, 1),
                }
                if targets is not None
                else None
            )
            logger.warning(
                "Daily nutrition plan validation failed: issues=%s computed=%s targets=%s adjustments=%s",
                issues,
                computed,
                targets,
                adjustments,
            )
            overused_foods = set(diversity.repeated_foods)
            replacement_candidates = [
                food
                for food in PLAN_FOOD_REFERENCE_NAMES
                if food.strip().lower() not in overused_foods
            ]
            return {
                "status": "invalid",
                "issues": issues,
                "computed_totals": {
                    "calories": computed.calories,
                    "protein_g": computed.protein_g,
                    "fat_g": computed.fat_g,
                    "carbs_g": computed.carbs_g,
                },
                "required_targets": (
                    {
                        "calories": targets.calories,
                        "protein_g": targets.protein_g,
                        "fat_g": targets.fat_g,
                        "carbs_g": targets.carbs_g,
                    }
                    if targets is not None
                    else None
                ),
                "required_adjustments": adjustments,
                "diversity": {
                    "score": diversity.score,
                    "unique_foods": diversity.unique_foods,
                    "total_ingredients": diversity.total_ingredients,
                    "protein_sources": diversity.protein_sources,
                    "plant_foods": diversity.plant_foods,
                    "duplicate_meals": diversity.duplicate_meals,
                    "duplicate_ingredients": list(diversity.duplicate_ingredients),
                    "repeated_foods": list(diversity.repeated_foods),
                    "repeated_food_meals": [
                        {"food": food, "meal_indexes": list(meal_indexes)}
                        for food, meal_indexes in diversity.repeated_food_meals
                    ],
                },
                "correction_hints": {
                    "server_alternative_sets_tried": attempted_alternatives,
                    "replace_repeated_foods_only_in_excess_meals": [
                        {
                            "food": food,
                            "keep_in_meals": list(meal_indexes[:2]),
                            "replace_in_meals": list(meal_indexes[2:]),
                        }
                        for food, meal_indexes in diversity.repeated_food_meals
                    ],
                    "remove_or_merge_duplicates_inside_meals": list(
                        diversity.duplicate_ingredients
                    ),
                    "allowed_replacement_reference_foods": replacement_candidates,
                },
                "database_matches": [
                    {
                        "display_name": ingredient.display_name,
                        "reference_food": ingredient.reference_food,
                        "matched_food": ingredient.matched_food,
                        "grams": ingredient.grams,
                        "per_100g": {
                            "calories": ingredient.calories_per_100g,
                            "protein_g": ingredient.protein_per_100g,
                            "fat_g": ingredient.fat_per_100g,
                            "carbs_g": ingredient.carbs_per_100g,
                        },
                    }
                    for meal in grounded_meals
                    for ingredient in meal.ingredients
                ],
                "instruction": (
                    "Replace every unknown reference_food with an exact name from the verified "
                    "catalogue in the tool description. Never use a composite dish as one "
                    "ingredient and never repeat an unchanged invalid submission. Apply every "
                    "entry in correction_hints: keep an overused food only in keep_in_meals, "
                    "replace it in replace_in_meals with an allowed replacement that is not "
                    "already present in that meal, and never list one reference_food twice in "
                    "one meal. Preserve valid meals when possible. Change ingredient gram "
                    "portions using required_adjustments, then call "
                    "submit_daily_nutrition_plan again. "
                    "All nutrition values will be recalculated from food_nutrients."
                ),
            }
        goal = str(profile_data.get("goal", "")).lower()
        budget_is_low = str(profile_data.get("budget", "")).lower() == "low"
        if locale == "ru":
            if goal == "gain_muscle":
                plan_intro = "Вот проверенный план питания на день для набора мышечной массы"
            elif goal in {"lose_weight", "weight_loss"}:
                plan_intro = "Вот проверенный план питания на день для снижения веса"
            else:
                plan_intro = "Вот проверенный план питания на день"
            if budget_is_low:
                plan_intro += " с учётом ограниченного бюджета"
            if "peanuts" in allergies:
                plan_intro += " и аллергии на арахис"
            plan_intro += "."
        else:
            plan_intro = "Here is a server-validated daily meal plan"
            if goal == "gain_muscle":
                plan_intro += " for muscle gain"
            elif goal in {"lose_weight", "weight_loss"}:
                plan_intro += " for weight loss"
            if budget_is_low:
                plan_intro += " on a low budget"
            plan_intro += "."
        return {
            "status": "ok",
            "food_set_selection": selected_food_set,
            "answer": render_grounded_plan(
                plan_intro,
                grounded_meals,
                computed,
                (
                    "Порции подобраны программно, а калории и БЖУ рассчитаны сервером "
                    "по проверенной базе продуктов. "
                    f"Разнообразие: {diversity.unique_foods} разных продуктов, "
                    f"оценка {diversity.score}/100."
                    if locale == "ru"
                    else (
                        "Portions were fitted programmatically; calories and macros were "
                        "calculated by the server from the verified food database. "
                        f"Diversity: {diversity.unique_foods} different foods, "
                        f"score {diversity.score}/100."
                    )
                ),
                locale,
            ),
            "validated_totals": {
                "calories": computed.calories,
                "protein_g": computed.protein_g,
                "fat_g": computed.fat_g,
                "carbs_g": computed.carbs_g,
            },
            "database_matches": [
                {
                    "matched_food": ingredient.matched_food,
                    "grams": ingredient.grams,
                    "per_100g": {
                        "calories": ingredient.calories_per_100g,
                        "protein_g": ingredient.protein_per_100g,
                        "fat_g": ingredient.fat_per_100g,
                        "carbs_g": ingredient.carbs_per_100g,
                    },
                }
                for meal in grounded_meals
                for ingredient in meal.ingredients
            ],
            "allergen_check": {
                "profile_allergies": allergies,
                "violations": [],
            },
            "diversity": {
                "score": diversity.score,
                "unique_foods": diversity.unique_foods,
                "total_ingredients": diversity.total_ingredients,
                "protein_sources": diversity.protein_sources,
                "plant_foods": diversity.plant_foods,
                "duplicate_meals": diversity.duplicate_meals,
                "duplicate_ingredients": list(diversity.duplicate_ingredients),
                "repeated_foods": list(diversity.repeated_foods),
                "repeated_food_meals": [
                    {"food": food, "meal_indexes": list(meal_indexes)}
                    for food, meal_indexes in diversity.repeated_food_meals
                ],
            },
        }

    return StructuredTool.from_function(
        func=submit_daily_nutrition_plan,
        name="submit_daily_nutrition_plan",
        metadata={"read_only": True},
        description=(
            "Required final submission for a complete daily meal plan. The server validates "
            "meal sums, macro-derived calories, and the user's profile targets before display. "
            + contract
        ),
    )
