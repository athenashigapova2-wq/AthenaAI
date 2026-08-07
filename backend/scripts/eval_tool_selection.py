"""Validate tool-selection cases offline or evaluate a safe multi-step LLM plan."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.prompts import (  # noqa: E402
    NUTRITION_SYSTEM,
    RECOVERY_SYSTEM,
    WORKOUT_SYSTEM,
)
from app.llm import get_llm  # noqa: E402
from app.tools.registry import build_tools  # noqa: E402

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "tool_selection_cases.json"
EVAL_USER_ID = "00000000-0000-0000-0000-000000000000"
ROUTE_CONFIG = {
    "nutrition": (NUTRITION_SYSTEM, ("profile", "nutrition")),
    "workout": (WORKOUT_SYSTEM, ("profile", "workout")),
    "recovery": (RECOVERY_SYSTEM, ("profile", "recovery", "calendar")),
}
MAX_MODEL_STEPS = 4

FAKE_TOOL_RESULTS = {
    "get_my_profile": {"status": "ok", "profile": {"goal": "maintain"}},
    "search_food": {"status": "ok", "foods": []},
    "get_daily_intake": {"status": "ok", "totals": {}, "meals": []},
    "get_workout_history": {"status": "ok", "workouts": []},
    "get_recovery_logs": {"status": "ok", "logs": []},
    "get_weight_trend": {"status": "ok", "weights": []},
    "get_cycle_logs": {"status": "ok", "logs": []},
    "log_meal": {"status": "ok", "simulated": True},
    "log_workout": {"status": "ok", "simulated": True},
}


def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def route_tools(route: str):
    _, domains = ROUTE_CONFIG[route]
    return build_tools(EVAL_USER_ID, domains=domains)


def validate_cases(cases: list[dict]) -> list[str]:
    """Validate labels and specialist boundaries without calling an LLM or tools."""
    failures: list[str] = []
    seen_ids: set[str] = set()
    for case in cases:
        case_id = case["id"]
        if case_id in seen_ids:
            failures.append(f"{case_id}: duplicate id")
        seen_ids.add(case_id)

        if case["route"] not in ROUTE_CONFIG:
            failures.append(f"{case_id}: unsupported route {case['route']}")
            continue

        available = {tool.name for tool in route_tools(case["route"])}
        expected = set(case["expected_tools"])
        forbidden = set(case["forbidden_tools"])
        if not expected <= available:
            failures.append(f"{case_id}: unavailable expected tools {expected - available}")
        if expected & forbidden:
            failures.append(f"{case_id}: tools cannot be expected and forbidden")
    return failures


def select_tools(case: dict) -> list[str]:
    """Collect a multi-step tool plan using fake results; never execute a tool."""
    system_prompt, _ = ROUTE_CONFIG[case["route"]]
    tools = route_tools(case["route"])
    llm = get_llm().bind_tools(tools, tool_choice="auto")
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=case["query"])]
    selected: list[str] = []
    expected = set(case["expected_tools"])
    forbidden = set(case["forbidden_tools"])

    for _ in range(MAX_MODEL_STEPS):
        response = llm.invoke(messages)
        messages.append(response)
        calls = getattr(response, "tool_calls", [])
        if not calls:
            break
        for call in calls:
            name = call["name"]
            selected.append(name)
            fake_result = FAKE_TOOL_RESULTS.get(name, {"status": "error", "simulated": True})
            messages.append(
                ToolMessage(
                    content=json.dumps(fake_result, ensure_ascii=False),
                    tool_call_id=call["id"],
                )
            )
        selected_set = set(selected)
        if expected <= selected_set or forbidden & selected_set:
            break
    return selected


def evaluate_live(cases: list[dict]) -> tuple[float, list[str]]:
    failures: list[str] = []
    passed = 0
    by_locale: Counter[tuple[str, bool]] = Counter()
    for case in cases:
        selected = select_tools(case)
        expected = set(case["expected_tools"])
        forbidden = set(case["forbidden_tools"])
        selected_set = set(selected)
        ok = expected <= selected_set and not forbidden & selected_set
        passed += int(ok)
        by_locale[(case["locale"], ok)] += 1
        if not ok:
            failures.append(
                f"{case['id']}: selected={selected}, expected={sorted(expected)}, "
                f"forbidden={sorted(forbidden)}"
            )

    score = passed / len(cases) if cases else 0.0
    print(f"Tool selection score: {passed}/{len(cases)} = {score:.1%}")
    for locale in sorted({case["locale"] for case in cases}):
        locale_passed = by_locale[(locale, True)]
        locale_total = locale_passed + by_locale[(locale, False)]
        print(f"  {locale}: {locale_passed}/{locale_total}")
    return score, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the configured LLM with fake tool results; tools are never executed.",
    )
    parser.add_argument("--min-score", type=float, default=1.0)
    args = parser.parse_args()

    cases = load_cases()
    failures = validate_cases(cases)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)
    print(f"Tool selection dataset valid: {len(cases)} cases")

    if not args.live:
        print("Offline validation passed; use --live to evaluate the configured LLM")
        return

    try:
        score, live_failures = evaluate_live(cases)
    except Exception as exc:
        raise SystemExit(
            f"Live eval provider error: {type(exc).__name__}: {exc}\n"
            "Check backend/.env and the tool schema named in the provider response"
        ) from exc
    for failure in live_failures:
        print(f"FAIL: {failure}")
    if score < args.min_score:
        raise SystemExit(1)
    print("Live tool selection eval passed")


if __name__ == "__main__":
    main()
