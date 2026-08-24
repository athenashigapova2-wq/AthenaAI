"""Specialist agents with their own tool sets and system prompts."""

import json
import logging
import re
from datetime import date
from time import perf_counter
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from app.agents.prompts import (
    GENERAL_SYSTEM,
    NUTRITION_SYSTEM,
    RECOVERY_SYSTEM,
    WORKOUT_SYSTEM,
    localized_system_prompt,
)
from app.agents.nutrition_validation import (
    GroundedMealPlanItem,
    NutritionNumbers,
    assess_food_diversity,
    fit_grounded_meal_portions,
    ground_meal_plan,
    nutrition_plan_contract,
    render_grounded_plan,
    targets_from_profile_result,
    validate_nutrition_numbers,
    validation_failure_message,
)
from app.agents.state import AgentState
from app.agents.router import is_progress_request
from app.config import settings
from app.llm import get_routed_llm
from app.resilience import retry_transient
from app.services import agent_traces
from app.tools.nutrition import PLAN_FOOD_REFERENCE_NAMES, lookup_food_reference
from app.tools.registry import build_tools, is_read_only_tool

MAX_TOOL_STEPS = 6
MAX_PLAN_SUBMISSIONS = 8
MIN_CALORIE_TARGET = 1_200.0
logger = logging.getLogger(__name__)


# The model may choose a nutritionally incompatible ingredient set even when every
# individual food exists in the catalogue. These bounded server-owned templates let
# the validator change the food set (not merely the grams) without inventing foods or
# paying for another LLM call. Every candidate still goes through database grounding,
# portion fitting, allergy checks, diversity checks, and target validation.
_ALTERNATIVE_PLAN_TEMPLATES: tuple[
    tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...
] = (
    (
        "balanced_lean",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("greek yogurt", "cucumber")),
            (
                "Lunch",
                ("chicken breast raw", "white rice cooked", "broccoli cooked", "olive oil"),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("cod cooked", "buckwheat raw", "spinach raw", "olive oil")),
        ),
    ),
    (
        "turkey_potato",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("yogurt", "cucumber")),
            (
                "Lunch",
                ("turkey breast roasted", "white rice cooked", "broccoli cooked", "olive oil"),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("cod cooked", "potato raw", "spinach raw", "olive oil")),
        ),
    ),
    (
        "higher_energy",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("greek yogurt", "cucumber")),
            (
                "Lunch",
                (
                    "beef tenderloin steak cooked",
                    "white rice cooked",
                    "broccoli cooked",
                    "olive oil",
                ),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("salmon raw", "buckwheat raw", "spinach raw", "olive oil")),
        ),
    ),
    (
        "low_budget",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("yogurt", "cucumber")),
            (
                "Lunch",
                ("chicken breast raw", "white rice raw", "broccoli cooked", "olive oil"),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("cod cooked", "potato raw", "spinach raw", "olive oil")),
        ),
    ),
)


def _alternative_plan_candidates(
    locale: str,
    *,
    low_budget: bool,
) -> list[tuple[str, list[GroundedMealPlanItem]]]:
    """Build deterministic candidate plans in profile-aware priority order."""
    templates = list(_ALTERNATIVE_PLAN_TEMPLATES)
    if low_budget:
        templates.sort(key=lambda item: item[0] != "low_budget")
    ru_names = ("Завтрак", "Перекус 1", "Обед", "Перекус 2", "Ужин")
    candidates: list[tuple[str, list[GroundedMealPlanItem]]] = []
    for template_name, meal_specs in templates:
        meals = [
            GroundedMealPlanItem.model_validate(
                {
                    "name": ru_names[index] if locale == "ru" else meal_name,
                    "ingredients": [
                        {"reference_food": food, "grams": 100.0}
                        for food in foods
                    ],
                }
            )
            for index, (meal_name, foods) in enumerate(meal_specs)
        ]
        candidates.append((template_name, meals))
    return candidates


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


def _normalize_tool_call_keys(value: Any) -> Any:
    """Strip accidental whitespace from model-produced keys before validation."""
    if isinstance(value, dict):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = key.strip() if isinstance(key, str) else key
            if normalized_key in normalized:
                raise ValueError(
                    f"Duplicate tool argument key after whitespace normalization: {normalized_key!r}"
                )
            normalized[normalized_key] = _normalize_tool_call_keys(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_tool_call_keys(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_tool_call_keys(item) for item in value)
    return value


def _weight_trend_dates(result: Any) -> tuple[date, date] | None:
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    weights = result.get("weights") or []
    if len(weights) < 2:
        return None
    try:
        first = date.fromisoformat(str(weights[0]["date"]))
        last = date.fromisoformat(str(weights[-1]["date"]))
    except (KeyError, TypeError, ValueError):
        return None
    return first, last


def _actual_progress_period(result: Any, locale: str) -> str:
    dates = _weight_trend_dates(result)
    if dates is None:
        return ""
    first, last = dates
    days = (last - first).days
    if locale == "ru":
        return (
            f"за период с {first.strftime('%d.%m.%Y')} по "
            f"{last.strftime('%d.%m.%Y')} ({days} дн.)"
        )
    return f"from {first.isoformat()} to {last.isoformat()} ({days} days)"


def _remove_known_trend_contradictions(text: str, trend: Any, locale: str) -> str:
    """Remove only claims that progress data is absent when the server has a trend."""
    if _weight_trend_dates(trend) is None:
        return text
    denial_terms = (
        ("нет", "недостаточно", "отсутств", "не удалось", "невозможно")
        if locale == "ru"
        else ("no ", "not enough", "insufficient", "unavailable", "unable")
    )
    progress_terms = (
        ("прогресс", "динамик", "изменен", "тренд", "вес")
        if locale == "ru"
        else ("progress", "trend", "change", "weight")
    )
    data_terms = (
        ("информац", "данн", "запис")
        if locale == "ru"
        else ("information", "data", "record")
    )
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    kept = []
    for part in parts:
        lowered = part.lower()
        contradiction = (
            any(term in lowered for term in denial_terms)
            and any(term in lowered for term in progress_terms)
            and any(term in lowered for term in data_terms)
        )
        if part.strip() and not contradiction:
            kept.append(part.strip())
    return " ".join(kept)


def _normalize_progress_period(text: str, trend: Any, locale: str) -> str:
    period = _actual_progress_period(trend, locale)
    if not period:
        return text
    pattern = (
        r"(?:за|в\s+течение)\s+(?:последн\w+\s+)?(?:\d+\s+)?"
        r"(?:д(?:ень|ня|ней)|недел\w*|месяц\w*)"
        if locale == "ru"
        else r"(?:over|during|for)\s+the\s+(?:last|past)\s+(?:\d+\s+)?(?:days?|weeks?|months?)"
    )
    return re.sub(pattern, period, text, flags=re.IGNORECASE)


def _normalize_address_style(text: str, locale: str) -> str:
    if locale != "ru":
        return text
    replacements = {
        "ты": "вы",
        "тебя": "вас",
        "тебе": "вам",
        "тобой": "вами",
        "твой": "ваш",
        "твоя": "ваша",
        "твоё": "ваше",
        "твое": "ваше",
        "твои": "ваши",
        "твоего": "вашего",
        "твоей": "вашей",
        "твоему": "вашему",
        "твоим": "вашим",
        "твоих": "ваших",
    }
    pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, replacements)) + r")\b",
        re.IGNORECASE,
    )
    normalized = pattern.sub(lambda match: replacements[match.group(0).lower()], text)
    informal_imperatives = {
        "продолжай": "продолжайте",
        "попробуй": "попробуйте",
        "добавь": "добавьте",
        "убери": "уберите",
        "замени": "замените",
        "следи": "следите",
        "сохраняй": "сохраняйте",
        "обратись": "обратитесь",
        "учти": "учтите",
        "помни": "помните",
    }
    imperative_pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, informal_imperatives)) + r")\b",
        re.IGNORECASE,
    )
    return imperative_pattern.sub(
        lambda match: informal_imperatives[match.group(0).lower()],
        normalized,
    )


def _sanitize_internal_notation(text: str, locale: str) -> str:
    cleaned = re.sub(
        r"\[(?:food_nutrients|matched_food|reference_food)\s*:[^\]]*\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    database_label = "проверенная база продуктов" if locale == "ru" else "verified food database"
    cleaned = re.sub(r"\bfood_nutrients\b", database_label, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:matched_food|reference_food)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bserver[- ]fetched\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return re.sub(r"\s+([,.;:])", r"\1", cleaned).strip()


def _finalize_answer(text: Any, locale: str, trend: Any = None) -> str:
    answer = _sanitize_internal_notation(str(text), locale)
    answer = _remove_known_trend_contradictions(answer, trend, locale)
    answer = _normalize_progress_period(answer, trend, locale)
    return _normalize_address_style(answer, locale).strip()


def _latest_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


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


def _weight_trend_evidence(result: Any, locale: str) -> str:
    """Render the server-fetched trend so a calorie decision always shows its evidence."""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return ""
    weights = result.get("weights") or []
    delta = result.get("delta_kg")
    if len(weights) < 2 or delta is None:
        if locale == "ru":
            return (
                "Данных о динамике веса пока недостаточно; без такого тренда менять "
                "целевую калорийность не следует."
            )
        return (
            "There is not enough weight-trend data yet; the calorie target should not "
            "be changed without it."
        )
    first = weights[0]
    last = weights[-1]
    first_weight = float(first["weight_kg"])
    last_weight = float(last["weight_kg"])
    if locale == "ru":
        return (
            f"Проверенный прогресс {_actual_progress_period(result, locale)}: "
            f"вес {first_weight:g} кг ({first.get('date')}) → "
            f"{last_weight:g} кг ({last.get('date')}), изменение {float(delta):+g} кг."
        )
    return (
        f"Verified progress {_actual_progress_period(result, locale)}: "
        f"weight {first_weight:g} kg ({first.get('date')}) → "
        f"{last_weight:g} kg ({last.get('date')}), change {float(delta):+g} kg."
    )


def _required_nutrition_context(
    state: AgentState,
    tools_by_name: dict[str, BaseTool],
) -> tuple[list[SystemMessage], dict[str, Any], bool]:
    """Fetch facts that must be present before specific nutrition advice."""
    message = _latest_user_text(state)
    if settings.llm_provider == "mock" and not _requires_weight_trend(message):
        return [], {}, False
    needs_plan_validation = _requires_full_day_plan(message)
    required_names: list[str] = []
    if needs_plan_validation:
        required_names.extend(("get_my_profile", "get_daily_intake"))
    if _requires_weight_trend(message):
        required_names.extend(("get_my_profile", "get_weight_trend"))

    results: dict[str, Any] = {}
    context: list[SystemMessage] = []
    for index, name in enumerate(dict.fromkeys(required_names)):
        result = _invoke_tool(
            state,
            {"name": name, "args": {}, "id": f"required-{name}"},
            tools_by_name,
            tool_step=index + 1,
        )
        results[name] = result
        context.append(
            SystemMessage(
                content=(
                    f"REQUIRED_SERVER_FACT {name}: "
                    f"{json.dumps(result, ensure_ascii=False, default=str)}. "
                    "This fact was fetched by the server for this request. Use it explicitly "
                    "and do not contradict it. Do not call the same tool again."
                    + (
                        " When describing the weight-trend duration, use its exact dates or "
                        "days field; do not relabel or round it to a week or month."
                        if name == "get_weight_trend"
                        else ""
                    )
                )
            )
        )

    return context, results, needs_plan_validation


def _required_recovery_context(
    state: AgentState,
    tools_by_name: dict[str, BaseTool],
) -> tuple[list[SystemMessage], dict[str, Any]]:
    """Fetch the weight trend before answering any request about progress."""
    if not is_progress_request(_latest_user_text(state)):
        return [], {}

    required_names = ["get_weight_trend"]
    if _requires_weight_trend(_latest_user_text(state)):
        required_names.insert(0, "get_my_profile")
    results: dict[str, Any] = {}
    context: list[SystemMessage] = []
    for index, name in enumerate(required_names, start=1):
        result = _invoke_tool(
            state,
            {"name": name, "args": {}, "id": f"required-{name}"},
            tools_by_name,
            tool_step=index,
        )
        results[name] = result
        context.append(
            SystemMessage(
                content=(
                    f"REQUIRED_SERVER_FACT {name}: "
                    f"{json.dumps(result, ensure_ascii=False, default=str)}. "
                    "This fact was fetched by the server before answering. Use it "
                    "explicitly and do not contradict it."
                    + (
                        " When describing the trend duration, use its exact dates or "
                        "days field; do not relabel or round it."
                        if name == "get_weight_trend"
                        else ""
                    )
                )
            )
        )
    return context, results


def _calorie_decision_tool(
    profile_result: Any,
    trend_result: Any,
    locale: str,
) -> StructuredTool:
    """Build the mandatory structured output path for calorie-target changes."""
    profile_data = (
        profile_result.get("profile", {})
        if isinstance(profile_result, dict) and profile_result.get("status") == "ok"
        else {}
    )
    current = profile_data.get("calorie_target")

    def submit_calorie_decision(
        action: Literal["keep", "increase", "decrease"],
        proposed_calories: float,
        rationale: str,
    ) -> dict[str, Any]:
        normalized_action = action
        if not isinstance(current, (int, float)):
            return {
                "status": "rejected",
                "issues": ["current calorie target is unavailable"],
            }
        proposed = round(float(proposed_calories), 1)
        issues: list[str] = []
        if proposed < MIN_CALORIE_TARGET:
            issues.append(
                f"proposed calories {proposed:g} are below minimum {MIN_CALORIE_TARGET:g}"
            )
        if proposed > 6_000:
            issues.append("proposed calories exceed the supported profile limit 6000")
        if normalized_action == "keep" and proposed != float(current):
            issues.append("keep requires proposed_calories to equal current_calories")
        if normalized_action == "increase" and proposed <= float(current):
            issues.append("increase requires proposed_calories above current_calories")
        if normalized_action == "decrease" and proposed >= float(current):
            issues.append("decrease requires proposed_calories below current_calories")
        trend_dates = _weight_trend_dates(trend_result)
        if normalized_action != "keep" and trend_dates is None:
            issues.append("a calorie-target change requires at least two weight records")
        if issues:
            return {
                "status": "rejected",
                "issues": issues,
                "current_calories": float(current),
                "minimum_calories": MIN_CALORIE_TARGET,
            }

        first_date, last_date = trend_dates if trend_dates else (None, None)
        decision = {
            "action": normalized_action,
            "current_calories": float(current),
            "proposed_calories": proposed,
            "minimum_calories": MIN_CALORIE_TARGET,
            "change_kcal": round(proposed - float(current), 1),
            "weight_records": len(
                trend_result.get("weights") or []
                if isinstance(trend_result, dict)
                else []
            ),
            "evidence_period": {
                "start": first_date.isoformat() if first_date else None,
                "end": last_date.isoformat() if last_date else None,
            },
            "rationale": _sanitize_internal_notation(rationale, locale),
        }
        if locale == "ru":
            action_text = {
                "keep": "сохранить",
                "increase": "увеличить",
                "decrease": "снизить",
            }[normalized_action]
            answer = (
                f"Решение по калорийности: {action_text} цель с {float(current):g} "
                f"до {proposed:g} ккал. {decision['rationale']}"
            )
        else:
            answer = (
                f"Calorie decision: {normalized_action} the target from "
                f"{float(current):g} to {proposed:g} kcal. {decision['rationale']}"
            )
        return {"status": "ok", "calorie_decision": decision, "answer": answer.strip()}

    return StructuredTool.from_function(
        func=submit_calorie_decision,
        name="submit_calorie_decision",
        metadata={"read_only": True},
        description=(
            "Mandatory final structured output for any request asking whether to change "
            "the calorie target. action must be keep, increase, or decrease. Copy the "
            "current target from get_my_profile. A change requires the fetched weight "
            f"trend and proposed_calories must never be below {MIN_CALORIE_TARGET:g}. "
            "Call this tool instead of answering only in prose."
        ),
    )


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


def _rag_messages(state: AgentState) -> list[SystemMessage]:
    context = state.get("rag_context", "")
    return [SystemMessage(content=context)] if context else []


def _invoke_tool(
    state: AgentState,
    call: dict[str, Any],
    tools_by_name: dict[str, BaseTool],
    tool_step: int = 1,
) -> Any:
    """Invoke one tool and trace it when this graph turn has a run id."""
    normalized_args = _normalize_tool_call_keys(call.get("args", {}))
    tool = tools_by_name.get(call["name"])
    run_id = state.get("run_id")
    if tool is None:
        error = ValueError(f"Unknown tool: {call['name']}")
        if run_id is not None:
            tool_call_id = agent_traces.create_tool_call(
                run_id=run_id,
                tool_name=call["name"],
                tool_args=normalized_args,
                tool_step=tool_step,
            )
            agent_traces.fail_tool_call(
                tool_call_id=tool_call_id,
                run_id=run_id,
                error=error,
                latency_ms=0,
            )
        return {"status": "error", "message": str(error)}

    def invoke() -> Any:
        if is_read_only_tool(tool):
            return retry_transient(
                lambda: tool.invoke(normalized_args),
                operation_name=f"tool.{tool.name}",
            )
        return tool.invoke(normalized_args)

    if run_id is None:
        return invoke()

    tool_call_id = agent_traces.create_tool_call(
        run_id=run_id,
        tool_name=call["name"],
        tool_args=normalized_args,
        tool_step=tool_step,
    )
    started_at = perf_counter()
    try:
        result = invoke()
    except Exception as exc:
        agent_traces.fail_tool_call(
            tool_call_id=tool_call_id,
            run_id=run_id,
            error=exc,
            latency_ms=agent_traces.elapsed_ms(started_at),
        )
        raise

    agent_traces.succeed_tool_call(
        tool_call_id=tool_call_id,
        run_id=run_id,
        tool_result=result,
        latency_ms=agent_traces.elapsed_ms(started_at),
    )
    return result


def _invoke_tool_agent(state: AgentState, system_prompt: str, tools: list[BaseTool]) -> dict:
    tools_by_name = {tool.name: tool for tool in tools}
    base_llm, selection = get_routed_llm(
        node_name=state["route"],
        purpose="tool_planning_or_answer",
        default_tier="main",
    )
    localized_prompt = localized_system_prompt(system_prompt, state["locale"])
    required_context: list[SystemMessage] = []
    required_results: dict[str, Any] = {}
    needs_plan_validation = False
    needs_calorie_decision = _requires_weight_trend(_latest_user_text(state))
    if state["route"] == "nutrition":
        required_context, required_results, needs_plan_validation = (
            _required_nutrition_context(state, tools_by_name)
        )
    elif state["route"] == "recovery":
        required_context, required_results = _required_recovery_context(
            state,
            tools_by_name,
        )
    calorie_tool: StructuredTool | None = None
    if needs_calorie_decision and not needs_plan_validation:
        calorie_tool = _calorie_decision_tool(
            required_results.get("get_my_profile"),
            required_results.get("get_weight_trend"),
            state["locale"],
        )
        tools_by_name[calorie_tool.name] = calorie_tool
        llm = base_llm.bind_tools([calorie_tool], tool_choice=calorie_tool.name)
    elif needs_plan_validation:
        profile_result = required_results.get("get_my_profile")
        targets = targets_from_profile_result(profile_result)
        submission_tool = _plan_submission_tool(
            targets,
            state["locale"],
            profile_result,
        )
        tools_by_name[submission_tool.name] = submission_tool
        llm = base_llm.bind_tools(
            [submission_tool],
            tool_choice=submission_tool.name,
        )
    else:
        remaining_tools = [
            tool for tool in tools if tool.name not in required_results
        ]
        llm = (
            base_llm.bind_tools(remaining_tools, tool_choice="auto")
            if remaining_tools
            else base_llm
        )
    system_parts = [localized_prompt]
    system_parts.extend(str(message.content) for message in required_context)
    if needs_plan_validation:
        system_parts.append(submission_tool.description)
    if calorie_tool is not None:
        system_parts.append(calorie_tool.description)
    system_parts.extend(str(message.content) for message in _rag_messages(state))
    messages = [
        SystemMessage(content="\n\n".join(system_parts)),
        *state["messages"],
    ]

    max_steps = MAX_PLAN_SUBMISSIONS if needs_plan_validation else MAX_TOOL_STEPS
    for tool_step in range(1, max_steps + 1):
        ai_msg = agent_traces.invoke_llm(
            llm,
            messages,
            run_id=state.get("run_id"),
            node_name=state["route"],
            purpose="tool_planning_or_answer",
            model_tier=selection.model_tier,
            model_selection=selection,
        )
        messages.append(ai_msg)
        if not getattr(ai_msg, "tool_calls", None):
            if needs_plan_validation or calorie_tool is not None:
                return {
                    "messages": [
                        AIMessage(content=validation_failure_message(state["locale"]))
                    ],
                    "resolution_mode": "fallback",
                }
            evidence = _weight_trend_evidence(
                required_results.get("get_weight_trend"),
                state["locale"],
            )
            finalized = _finalize_answer(
                ai_msg.content,
                state["locale"],
                required_results.get("get_weight_trend"),
            )
            if evidence:
                finalized = f"{evidence}\n\n{finalized}".strip()
            ai_msg = AIMessage(content=finalized)
            return {"messages": [ai_msg], "resolution_mode": "main_llm"}

        for call in ai_msg.tool_calls:
            result = _invoke_tool(state, call, tools_by_name, tool_step=tool_step)
            if (
                call["name"] == "submit_daily_nutrition_plan"
                and isinstance(result, dict)
                and result.get("status") == "ok"
            ):
                return {
                    "messages": [
                        AIMessage(
                            content=_finalize_answer(result["answer"], state["locale"])
                        )
                    ],
                    "resolution_mode": "main_llm",
                }
            if (
                call["name"] == "submit_calorie_decision"
                and isinstance(result, dict)
                and result.get("status") == "ok"
            ):
                evidence = _weight_trend_evidence(
                    required_results.get("get_weight_trend"),
                    state["locale"],
                )
                answer = _finalize_answer(result["answer"], state["locale"])
                if evidence:
                    answer = f"{evidence}\n\n{answer}".strip()
                return {
                    "messages": [AIMessage(content=answer)],
                    "resolution_mode": "main_llm",
                    "calorie_decision": result["calorie_decision"],
                }
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=call["id"],
                )
            )

    return {
        "messages": [AIMessage(content="Я остановилась, чтобы не зациклиться на инструментах. Попробуй уточнить запрос.")],
        "resolution_mode": "fallback",
    }


def nutrition_node(state: AgentState) -> dict:
    return _invoke_tool_agent(
        state,
        NUTRITION_SYSTEM,
        build_tools(state["user_id"], domains=("profile", "nutrition", "recovery")),
    )


def workout_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, WORKOUT_SYSTEM, build_tools(state["user_id"], domains=("profile", "workout")))


def recovery_node(state: AgentState) -> dict:
    return _invoke_tool_agent(state, RECOVERY_SYSTEM, build_tools(state["user_id"], domains=("profile", "recovery", "calendar")))


def general_node(state: AgentState) -> dict:
    prompt = localized_system_prompt(GENERAL_SYSTEM, state["locale"])
    llm, selection = get_routed_llm(
        node_name="general",
        purpose="answer",
        default_tier="main",
    )
    response = agent_traces.invoke_llm(
        llm,
        [SystemMessage(content=prompt), *_rag_messages(state), *state["messages"]],
        run_id=state.get("run_id"),
        node_name="general",
        purpose="answer",
        model_tier=selection.model_tier,
        model_selection=selection,
    )
    return {
        "messages": [
            AIMessage(content=_finalize_answer(response.content, state["locale"]))
        ],
        "resolution_mode": "main_llm",
    }
