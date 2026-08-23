"""Deterministic offline regression eval for agent routing and tool boundaries."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.router import route_with_keywords  # noqa: E402
from app.tools.registry import build_tools  # noqa: E402

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "agent_cases.json"
EVAL_USER_ID = "00000000-0000-0000-0000-000000000000"
ROUTE_DOMAINS = {
    "nutrition": ("profile", "nutrition", "recovery"),
    "workout": ("profile", "workout"),
    "recovery": ("profile", "recovery", "calendar"),
    "general": (),
}


def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def available_tools(route: str) -> set[str]:
    domains = ROUTE_DOMAINS[route]
    if not domains:
        return set()
    return {tool.name for tool in build_tools(EVAL_USER_ID, domains=domains)}


def evaluate(cases: list[dict]) -> tuple[float, list[str]]:
    failures: list[str] = []
    correct = 0
    by_locale: Counter[tuple[str, bool]] = Counter()

    for case in cases:
        actual_route = route_with_keywords(case["query"])
        route_ok = actual_route == case["expected_route"]
        correct += int(route_ok)
        by_locale[(case["locale"], route_ok)] += 1

        if not route_ok:
            failures.append(
                f"{case['id']}: route={actual_route}, expected={case['expected_route']}"
            )
            continue

        required_tool = case.get("required_tool")
        if required_tool and required_tool not in available_tools(actual_route):
            failures.append(
                f"{case['id']}: {actual_route} cannot access {required_tool}"
            )

    accuracy = correct / len(cases) if cases else 0.0
    print(f"Agent router accuracy: {correct}/{len(cases)} = {accuracy:.1%}")
    for locale in sorted({case["locale"] for case in cases}):
        locale_correct = by_locale[(locale, True)]
        locale_total = locale_correct + by_locale[(locale, False)]
        print(f"  {locale}: {locale_correct}/{locale_total}")
    return accuracy, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-accuracy", type=float, default=1.0)
    args = parser.parse_args()

    accuracy, failures = evaluate(load_cases())
    for failure in failures:
        print(f"FAIL: {failure}")
    if accuracy < args.min_accuracy or failures:
        raise SystemExit(1)
    print("Agent evals passed")


if __name__ == "__main__":
    main()
