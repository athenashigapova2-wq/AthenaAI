"""Offline checks for required weight context and nutrition-plan validation."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.nutrition_validation import (  # noqa: E402
    FoodNutrientReference,
    GroundedIngredient,
    GroundedMeal,
    NutritionNumbers,
    _portion_bounds,
    assess_food_diversity,
    render_validated_plan,
    validate_nutrition_plan,
)
from app.agents.specialists import (  # noqa: E402
    NUTRITION_SYSTEM,
    RECOVERY_SYSTEM,
    _invoke_tool_agent,
    _invoke_tool,
    _normalize_tool_call_keys,
    _plan_submission_tool,
    _required_nutrition_context,
    _required_recovery_context,
    _requires_full_day_plan,
    _requires_weight_trend,
    _weight_trend_evidence,
)
from app.config import settings  # noqa: E402
from app.tools.nutrition import lookup_food_reference  # noqa: E402


PROFILE_RESULT = {
    "status": "ok",
    "profile": {
        "calorie_target": 1_750,
        "protein_target_g": 130,
        "fat_target_g": 49,
        "carb_target_g": 197,
        "allergies": ["peanuts"],
    },
}
TARGETS = NutritionNumbers(1_750, 130, 49, 197)

VALID_PLAN = """Завтрак: омлет и тост.
[MEAL_KBJU kcal=400 protein=30 fat=12 carbs=43]
Обед: курица, рис и овощи.
[MEAL_KBJU kcal=600 protein=45 fat=18 carbs=64.5]
Ужин: рыба и картофель.
[MEAL_KBJU kcal=500 protein=40 fat=15 carbs=51.25]
Перекус: йогурт и ягоды.
[MEAL_KBJU kcal=250 protein=15 fat=4 carbs=38.25]
[TOTAL_KBJU kcal=1750 protein=130 fat=49 carbs=197]
"""


def _state(message: str) -> dict:
    return {
        "user_id": "user-1",
        "run_id": None,
        "locale": "ru",
        "messages": [HumanMessage(content=message)],
        "route": "nutrition",
        "resolution_mode": "main_llm",
        "rag_enabled": False,
        "rag_context": "",
        "retrieved_chunks": [],
    }


def check_intent_detection() -> None:
    assert _requires_weight_trend("Нужно ли теперь менять калорийность?")
    assert _requires_weight_trend("Стоит ли снизить калории?")
    assert not _requires_weight_trend("Сколько калорий в яблоке?")
    assert _requires_full_day_plan("Составь мне план питания на сегодня")
    assert not _requires_full_day_plan("Как приготовить омлет?")


def check_programmatic_totals() -> None:
    result = validate_nutrition_plan(VALID_PLAN, TARGETS)
    assert result.valid, result.issues
    assert result.meal_count == 4
    assert result.summed is not None
    assert result.summed.calories == 1_750

    inconsistent = VALID_PLAN.replace(
        "kcal=250 protein=15 fat=4 carbs=38.25",
        "kcal=150 protein=15 fat=4 carbs=38.25",
    )
    invalid = validate_nutrition_plan(inconsistent, TARGETS)
    assert not invalid.valid
    assert "declared calories does not equal the meal sum" in invalid.issues

    unstructured = (
        "Завтрак 200 ккал, обед 320 ккал, ужин 342 ккал. "
        "Этот план дает 1750 ккал."
    )
    invalid = validate_nutrition_plan(unstructured, TARGETS)
    assert not invalid.valid
    assert "at least three MEAL_KBJU markers are required" in invalid.issues

    rendered = render_validated_plan(VALID_PLAN, "ru")
    assert "MEAL_KBJU" not in rendered
    assert "TOTAL_KBJU" not in rendered
    assert "Итого: 1750 ккал; Б 130 г; Ж 49 г; У 197 г" in rendered


def check_food_lookup_never_substitutes_a_different_food() -> None:
    class Result:
        def __init__(self, data):
            self.data = data

    class Query:
        def __init__(self, data):
            self.data = data

        def select(self, *_args):
            return self

        def eq(self, _column, value):
            self.data = [row for row in self.data if row["food_name"] == value]
            return self

        def limit(self, count):
            self.data = self.data[:count]
            return self

        def execute(self):
            return Result(self.data)

    rows = [
        {
            "food_name": "oats",
            "calories_per_100g": 357.8,
            "protein_g": 15.6,
            "carbs_g": 60.6,
            "fat_g": 6.4,
        },
        {
            "food_name": "beets raw",
            "calories_per_100g": 41.9,
            "protein_g": 1.6,
            "carbs_g": 9.4,
            "fat_g": 0.1,
        },
    ]

    class FakeSupabase:
        def table(self, _name):
            return Query(deepcopy(rows))

        def rpc(self, _name, _params):
            return Query(deepcopy(rows))

    with patch("app.services.supabase.get_supabase", return_value=FakeSupabase()):
        oats = lookup_food_reference("oats")
        assert oats["food_name"] == "oats"
        assert oats["calories_per_100g"] == 357.8
        try:
            lookup_food_reference("oats raw")
        except LookupError as exc:
            assert "exact food not found" in str(exc)
        else:
            raise AssertionError("oats raw must not be substituted with beets raw")


def check_weight_trend_is_forced() -> None:
    tool = StructuredTool.from_function(
        func=lambda days=30: {"status": "ok"},
        name="get_weight_trend",
        description="weight trend",
    )
    trend = {
        "status": "ok",
        "delta_kg": -1.1,
        "weights": [
            {"date": "2026-09-01", "weight_kg": 74.0},
            {"date": "2026-09-15", "weight_kg": 72.9},
        ],
    }
    with (
        patch.object(settings, "llm_provider", "gigachat"),
        patch("app.agents.specialists._invoke_tool", return_value=trend) as invoke,
    ):
        context, results, validates_plan = _required_nutrition_context(
            _state("Нужно ли теперь менять калорийность?"),
            {tool.name: tool},
        )
    assert invoke.call_count == 1
    assert invoke.call_args.args[1]["name"] == "get_weight_trend"
    assert results["get_weight_trend"]["delta_kg"] == -1.1
    assert "-1.1" in context[0].content
    assert validates_plan is False
    evidence = _weight_trend_evidence(trend, "ru")
    assert "74 кг" in evidence
    assert "72.9 кг" in evidence
    assert "-1.1 кг" in evidence
    assert "01.09.2026" in evidence
    assert "15.09.2026" in evidence
    assert "14 дн." in evidence


def check_tool_call_keys_are_normalized_before_validation() -> None:
    tool = StructuredTool.from_function(
        func=lambda reference_food: {"status": "ok", "food": reference_food},
        name="lookup_reference",
        description="lookup",
    )
    result = _invoke_tool(
        _state("test"),
        {
            "name": tool.name,
            "args": {" reference_food ": "oats"},
            "id": "malformed-key",
        },
        {tool.name: tool},
    )
    assert result == {"status": "ok", "food": "oats"}
    assert _normalize_tool_call_keys({" meals ": [{" grams ": 10}]}) == {
        "meals": [{"grams": 10}]
    }
    try:
        _normalize_tool_call_keys({"grams": 10, " grams ": 20})
    except ValueError as exc:
        assert "Duplicate tool argument key" in str(exc)
    else:
        raise AssertionError("colliding normalized keys must be rejected")


def _grounded_ingredient(name: str, grams: float = 100) -> GroundedIngredient:
    reference = FoodNutrientReference(
        food_name=name,
        calories_per_100g=100,
        protein_g=10,
        fat_g=2,
        carbs_g=10,
    )
    return GroundedIngredient(
        display_name=name,
        reference_food=name,
        matched_food=reference.food_name,
        grams=grams,
        calories_per_100g=reference.calories_per_100g,
        protein_per_100g=reference.protein_g,
        fat_per_100g=reference.fat_g,
        carbs_per_100g=reference.carbs_g,
        calories=100,
        protein_g=10,
        fat_g=2,
        carbs_g=10,
    )


def check_household_portions_and_food_diversity() -> None:
    assert _portion_bounds(_grounded_ingredient("oats"))[0] == 30
    assert _portion_bounds(_grounded_ingredient("egg raw"))[0] == 50
    assert _portion_bounds(_grounded_ingredient("greek yogurt"))[0] == 100
    assert _portion_bounds(_grounded_ingredient("chicken breast raw"))[0] == 80
    assert _portion_bounds(_grounded_ingredient("white rice cooked"))[0] == 80
    assert _portion_bounds(_grounded_ingredient("olive oil"))[0] == 5

    varied_names = (
        "oats",
        "egg raw",
        "greek yogurt",
        "banana",
        "chicken breast raw",
        "white rice cooked",
        "broccoli cooked",
        "turkey breast roasted",
        "buckwheat raw",
        "spinach raw",
    )
    varied = GroundedMeal(
        name="day",
        ingredients=[_grounded_ingredient(name) for name in varied_names],
        calories=1_000,
        protein_g=100,
        fat_g=20,
        carbs_g=100,
    )
    assessment = assess_food_diversity([varied])
    assert assessment.score == 100
    assert assessment.unique_foods == 10
    assert not assessment.issues

    repetitive = [
        GroundedMeal(
            name=f"repetitive-{index}",
            ingredients=[_grounded_ingredient("oats")],
            calories=100,
            protein_g=10,
            fat_g=2,
            carbs_g=10,
        )
        for index in range(4)
    ]
    poor = assess_food_diversity(repetitive)
    assert poor.score < 50
    assert poor.duplicate_meals == 3
    assert poor.repeated_foods == ("oats",)
    assert len(poor.issues) == 2


def check_progress_request_forces_weight_trend_in_recovery() -> None:
    tool = StructuredTool.from_function(
        func=lambda days=30: {"status": "ok"},
        name="get_weight_trend",
        description="weight trend",
    )
    trend = {
        "status": "ok",
        "delta_kg": -0.8,
        "weights": [
            {"date": "2026-09-01", "weight_kg": 74.0},
            {"date": "2026-09-15", "weight_kg": 73.2},
        ],
    }
    state = _state("Какой у меня прогресс за последние две недели?")
    state["route"] = "recovery"
    with (
        patch.object(settings, "llm_provider", "mock"),
        patch("app.agents.specialists._invoke_tool", return_value=trend) as invoke,
    ):
        context, results = _required_recovery_context(
            state,
            {tool.name: tool},
        )

    assert invoke.call_count == 1
    assert invoke.call_args.args[1]["name"] == "get_weight_trend"
    assert results["get_weight_trend"]["delta_kg"] == -0.8
    assert "REQUIRED_SERVER_FACT get_weight_trend" in context[0].content

    selection = SimpleNamespace(model_tier="main")
    with (
        patch.object(settings, "llm_provider", "mock"),
        patch(
            "app.agents.specialists.get_routed_llm",
            return_value=(object(), selection),
        ),
        patch("app.agents.specialists._invoke_tool", return_value=trend) as invoke,
        patch(
            "app.agents.specialists.agent_traces.invoke_llm",
            return_value=AIMessage(
                content=(
                    "За последний месяц ты хорошо продвинулась. "
                    "Но информации о твоём прогрессе нет. Продолжай свой план."
                )
            ),
        ) as invoke_llm,
    ):
        answer = _invoke_tool_agent(state, RECOVERY_SYSTEM, [tool])

    assert invoke.call_count == 1
    assert invoke.call_args.args[1]["name"] == "get_weight_trend"
    system_message = invoke_llm.call_args.args[1][0].content
    assert "REQUIRED_SERVER_FACT get_weight_trend" in system_message
    assert "74 кг" in answer["messages"][0].content
    assert "73.2 кг" in answer["messages"][0].content
    assert "01.09.2026" in answer["messages"][0].content
    assert "15.09.2026" in answer["messages"][0].content
    assert "последний месяц" not in answer["messages"][0].content
    assert "информации о" not in answer["messages"][0].content
    assert "ты " not in answer["messages"][0].content.lower()
    assert "вы хорошо" in answer["messages"][0].content.lower()
    assert "продолжайте свой план" in answer["messages"][0].content.lower()


def check_invalid_draft_is_fitted_before_return() -> None:
    profile_tool = StructuredTool.from_function(
        func=lambda: PROFILE_RESULT,
        name="get_my_profile",
        description="profile",
    )
    intake_tool = StructuredTool.from_function(
        func=lambda day=None: {"status": "ok", "totals": {}, "meals": []},
        name="get_daily_intake",
        description="daily intake",
    )
    base_llm = SimpleNamespace()
    bound_llm = object()
    base_llm.bind_tools = lambda *_args, **_kwargs: bound_llm
    selection = SimpleNamespace(model_tier="main")
    foods = {
        "oats": (400, 30, 12, 43),
        "chicken breast raw": (600, 45, 18, 64.5),
        "cod cooked": (500, 40, 15, 51.25),
        "greek yogurt": (250, 15, 4, 38.25),
    }

    def fake_food_resolver(query: str) -> dict:
        calories, protein, fat, carbs = foods[query]
        return {
            "food_name": query,
            "calories_per_100g": calories,
            "protein_g": protein,
            "fat_g": fat,
            "carbs_g": carbs,
        }

    valid_args = {
        "meals": [
            {
                "name": "Завтрак",
                "ingredients": [{
                    "display_name": "Ложное название, которому нельзя доверять",
                    "reference_food": "oats",
                    "grams": 100,
                }],
            },
            {
                "name": "Обед",
                "ingredients": [{
                    "reference_food": "chicken breast raw",
                    "grams": 100,
                }],
            },
            {
                "name": "Ужин",
                "ingredients": [{
                    "reference_food": "cod cooked",
                    "grams": 100,
                }],
            },
            {
                "name": "Перекус",
                "ingredients": [{
                    "reference_food": "greek yogurt",
                    "grams": 100,
                }],
            },
        ],
    }
    invalid_args = deepcopy(valid_args)
    invalid_args["meals"][-1]["ingredients"][0]["grams"] = 10
    invalid_draft = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submit_daily_nutrition_plan",
                "args": invalid_args,
                "id": "submit-invalid",
                "type": "tool_call",
            }
        ],
    )
    repaired = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submit_daily_nutrition_plan",
                "args": valid_args,
                "id": "submit-valid",
                "type": "tool_call",
            }
        ],
    )

    with (
        patch.object(settings, "llm_provider", "gigachat"),
        patch(
            "app.agents.specialists.get_routed_llm",
            return_value=(base_llm, selection),
        ),
        patch(
            "app.agents.specialists.agent_traces.invoke_llm",
            side_effect=[invalid_draft, repaired],
        ) as invoke_llm,
        patch(
            "app.agents.specialists.lookup_food_reference",
            side_effect=fake_food_resolver,
        ),
    ):
        result = _invoke_tool_agent(
            _state("Составь мне план питания на сегодня"),
            NUTRITION_SYSTEM,
            [profile_tool, intake_tool],
        )

    # The model selects foods once. The server repairs portions without paying for
    # another LLM call or trusting the model to redo arithmetic.
    assert invoke_llm.call_count == 1
    assert result["resolution_mode"] == "main_llm"
    answer = result["messages"][0].content
    assert "MEAL_KBJU" not in answer
    assert "**Итого:**" in answer, answer
    assert "food_nutrients" not in answer
    assert "[" not in answer
    assert " raw" not in answer.lower()
    assert "аллергии на арахис" in answer
    assert "Ложное название" not in answer
    assert "Овсяные хлопья" in answer
    assert "Куриная грудка" in answer
    assert "Разнообразие:" in answer
    assert "/100" in answer

    allergen_args = deepcopy(valid_args)
    allergen_args["meals"][0]["name"] = "Тост с арахисовой пастой"
    submission_tool = _plan_submission_tool(
        TARGETS,
        "ru",
        PROFILE_RESULT,
        food_resolver=fake_food_resolver,
    )
    rejected = submission_tool.invoke(allergen_args)
    assert rejected["status"] == "invalid"
    assert any("allergen" in issue for issue in rejected["issues"])


if __name__ == "__main__":
    check_intent_detection()
    check_programmatic_totals()
    check_food_lookup_never_substitutes_a_different_food()
    check_weight_trend_is_forced()
    check_tool_call_keys_are_normalized_before_validation()
    check_household_portions_and_food_diversity()
    check_progress_request_forces_weight_trend_in_recovery()
    check_invalid_draft_is_fitted_before_return()
    print("Nutrition guardrail checks passed")
