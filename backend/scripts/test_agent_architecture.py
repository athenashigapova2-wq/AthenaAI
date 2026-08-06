"""Offline checks for Router + specialist tool boundaries.

Does not call Supabase or an LLM; it verifies deterministic routing fallback and that
user_id remains closed over inside tools instead of being exposed to the model schema.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.router import route_with_keywords  # noqa: E402
from app.tools.registry import build_tools  # noqa: E402

USER_ID = "00000000-0000-0000-0000-000000000000"


def assert_routes() -> None:
    cases = {
        "сколько калорий в твороге?": "nutrition",
        "составь тренировку на ноги в зале": "workout",
        "я плохо спала и болят мышцы": "recovery",
        "привет, что ты умеешь?": "general",
    }
    for text, expected in cases.items():
        actual = route_with_keywords(text)
        assert actual == expected, f"{text!r}: expected {expected}, got {actual}"


def assert_tool_boundaries() -> None:
    nutrition = {tool.name: tool for tool in build_tools(USER_ID, domains=("profile", "nutrition"))}
    workout = {tool.name: tool for tool in build_tools(USER_ID, domains=("profile", "workout"))}
    recovery = {tool.name: tool for tool in build_tools(USER_ID, domains=("profile", "recovery", "calendar"))}

    assert {"get_my_profile", "search_food", "get_daily_intake", "log_meal"} <= nutrition.keys()
    assert "log_workout" not in nutrition
    assert {"get_my_profile", "get_workout_history", "log_workout"} <= workout.keys()
    assert "log_meal" not in workout
    assert {"get_my_profile", "get_recovery_logs", "get_weight_trend", "get_cycle_logs"} <= recovery.keys()

    for tools in (nutrition, workout, recovery):
        for tool in tools.values():
            properties = tool.args_schema.model_json_schema().get("properties", {})
            assert "user_id" not in properties, f"{tool.name} exposes user_id"


if __name__ == "__main__":
    assert_routes()
    assert_tool_boundaries()
    print("Agent architecture checks passed")
