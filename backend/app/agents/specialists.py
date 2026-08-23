"""Specialist agents with their own tool sets and system prompts."""

import json
import logging
import re
from time import perf_counter
from typing import Any

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
    fit_grounded_meal_portions,
    ground_meal_plan,
    nutrition_plan_contract,
    render_grounded_plan,
    targets_from_profile_result,
    validate_nutrition_numbers,
    validation_failure_message,
)
from app.agents.state import AgentState
from app.config import settings
from app.llm import get_routed_llm
from app.resilience import retry_transient
from app.services import agent_traces
from app.tools.nutrition import PLAN_FOOD_REFERENCE_NAMES, lookup_food_reference
from app.tools.registry import build_tools, is_read_only_tool

MAX_TOOL_STEPS = 6
MAX_PLAN_SUBMISSIONS = 8
logger = logging.getLogger(__name__)


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
            f"Проверенный тренд веса: {first_weight:g} кг ({first.get('date')}) → "
            f"{last_weight:g} кг ({last.get('date')}), изменение {float(delta):+g} кг."
        )
    return (
        f"Verified weight trend: {first_weight:g} kg ({first.get('date')}) → "
        f"{last_weight:g} kg ({last.get('date')}), change {float(delta):+g} kg."
    )


def _required_nutrition_context(
    state: AgentState,
    tools_by_name: dict[str, BaseTool],
) -> tuple[list[SystemMessage], dict[str, Any], bool]:
    """Fetch facts that must be present before specific nutrition advice."""
    if settings.llm_provider == "mock":
        return [], {}, False

    message = _latest_user_text(state)
    needs_plan_validation = _requires_full_day_plan(message)
    required_names: list[str] = []
    if needs_plan_validation:
        required_names.extend(("get_my_profile", "get_daily_intake"))
    if _requires_weight_trend(message):
        required_names.append("get_weight_trend")

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
        allergen_issues = []
        for index, meal in enumerate(normalized_meals, start=1):
            ingredient_text = " ".join(
                f"{ingredient.display_name} {ingredient.reference_food}"
                for ingredient in meal.ingredients
            )
            meal_text = f"{meal.name} {ingredient_text}".lower()
            matched = sorted(term for term in forbidden_terms if term in meal_text)
            if matched:
                allergen_issues.append(
                    f"meal {index} may contain a profile allergen: {', '.join(matched)}"
                )
        issues = [
            *grounding_issues,
            *portion_issues,
            *validation.issues,
            *allergen_issues,
        ]
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
                    "ingredient and never repeat an unchanged invalid submission. Change "
                    "ingredient gram portions using required_adjustments, then call "
                    "submit_daily_nutrition_plan again. "
                    "All nutrition values will be recalculated from food_nutrients."
                ),
            }
        return {
            "status": "ok",
            "answer": render_grounded_plan(
                (
                    "Вот проверенный план на день с учётом цели снижения веса и "
                    "аллергии на арахис."
                    if locale == "ru" and "peanuts" in allergies
                    else (
                        "Вот проверенный план питания на день."
                        if locale == "ru"
                        else "Here is a server-validated daily meal plan."
                    )
                ),
                grounded_meals,
                computed,
                (
                    "Порции подобраны программно, а калории и БЖУ рассчитаны сервером "
                    "по значениям food_nutrients на 100 г."
                    if locale == "ru"
                    else (
                        "Portions were fitted programmatically; calories and macros were "
                        "calculated by the server from food_nutrients values per 100 g."
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
    tool = tools_by_name.get(call["name"])
    run_id = state.get("run_id")
    if tool is None:
        error = ValueError(f"Unknown tool: {call['name']}")
        if run_id is not None:
            tool_call_id = agent_traces.create_tool_call(
                run_id=run_id,
                tool_name=call["name"],
                tool_args=call["args"],
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
                lambda: tool.invoke(call["args"]),
                operation_name=f"tool.{tool.name}",
            )
        return tool.invoke(call["args"])

    if run_id is None:
        return invoke()

    tool_call_id = agent_traces.create_tool_call(
        run_id=run_id,
        tool_name=call["name"],
        tool_args=call["args"],
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
    if state["route"] == "nutrition":
        required_context, required_results, needs_plan_validation = (
            _required_nutrition_context(state, tools_by_name)
        )
    if needs_plan_validation:
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
            if needs_plan_validation:
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
            if evidence:
                ai_msg = AIMessage(content=f"{evidence}\n\n{ai_msg.content}")
            return {"messages": [ai_msg], "resolution_mode": "main_llm"}

        for call in ai_msg.tool_calls:
            result = _invoke_tool(state, call, tools_by_name, tool_step=tool_step)
            if (
                call["name"] == "submit_daily_nutrition_plan"
                and isinstance(result, dict)
                and result.get("status") == "ok"
            ):
                return {
                    "messages": [AIMessage(content=str(result["answer"]))],
                    "resolution_mode": "main_llm",
                }
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

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
    return {"messages": [response], "resolution_mode": "main_llm"}
