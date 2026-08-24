"""Deterministic policy and structured output for calorie-target decisions."""

from typing import Any, Literal

from langchain_core.tools import StructuredTool

from app.agents.common.response_pipeline import (
    _sanitize_internal_notation,
    _weight_trend_dates,
)

MIN_CALORIE_TARGET = 1_200.0

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
