"""Deterministic rubric checks over safe live answers with fake tool results."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_tool_selection import (  # noqa: E402
    FAKE_TOOL_RESULTS,
    MAX_MODEL_STEPS,
    ROUTE_CONFIG,
    route_tools,
)
from app.agents.prompts import localized_system_prompt  # noqa: E402
from app.llm import get_llm  # noqa: E402

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "answer_quality_cases.json"


def load_cases() -> list[dict]:
    with CASES_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def validate_cases(cases: list[dict]) -> list[str]:
    failures: list[str] = []
    ids: set[str] = set()
    for case in cases:
        if case["id"] in ids:
            failures.append(f"{case['id']}: duplicate id")
        ids.add(case["id"])
        if case["route"] not in ROUTE_CONFIG:
            failures.append(f"{case['id']}: unsupported route")
        if not (case["required_substrings"] or case["required_any"]):
            failures.append(f"{case['id']}: rubric has no positive requirement")
    return failures


def generate_answer(case: dict) -> tuple[str, list[str]]:
    system_prompt, _ = ROUTE_CONFIG[case["route"]]
    llm = get_llm().bind_tools(route_tools(case["route"]), tool_choice="auto")
    prompt = localized_system_prompt(system_prompt, case["locale"])
    messages = [SystemMessage(content=prompt), HumanMessage(content=case["query"])]
    selected: list[str] = []
    fake_results = {**FAKE_TOOL_RESULTS, **case["fake_tool_results"]}

    for _ in range(MAX_MODEL_STEPS):
        response = llm.invoke(messages)
        messages.append(response)
        calls = getattr(response, "tool_calls", [])
        if not calls:
            return str(response.content), selected
        for call in calls:
            selected.append(call["name"])
            result = fake_results.get(call["name"], {"status": "error", "simulated": True})
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=call["id"],
                )
            )
    return "", selected


def score_case(case: dict, answer: str, selected: list[str]) -> tuple[bool, list[str]]:
    answer_lower = answer.lower()
    reasons: list[str] = []
    missing_tools = set(case["required_tools"]) - set(selected)
    if missing_tools:
        reasons.append(f"missing tools {sorted(missing_tools)}")
    forbidden_tools = set(case.get("forbidden_tools", [])) & set(selected)
    if forbidden_tools:
        reasons.append(f"forbidden tools {sorted(forbidden_tools)}")
    for value in case["required_substrings"]:
        if value.lower() not in answer_lower:
            reasons.append(f"missing {value!r}")
    if case["required_any"] and not any(
        value.lower() in answer_lower for value in case["required_any"]
    ):
        reasons.append(f"missing any of {case['required_any']}")
    leaked = [
        value for value in case["forbidden_substrings"] if value.lower() in answer_lower
    ]
    if leaked:
        reasons.append(f"forbidden substrings {leaked}")
    return not reasons, reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--min-score", type=float, default=1.0)
    args = parser.parse_args()
    cases = load_cases()
    failures = validate_cases(cases)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)
    print(f"Answer quality dataset valid: {len(cases)} cases")
    if not args.live:
        print("Offline validation passed; use --live for deterministic rubric checks")
        return

    passed = 0
    live_failures: list[str] = []
    by_locale: Counter[tuple[str, bool]] = Counter()
    try:
        for case in cases:
            answer, selected = generate_answer(case)
            ok, reasons = score_case(case, answer, selected)
            passed += int(ok)
            by_locale[(case["locale"], ok)] += 1
            if not ok:
                live_failures.append(
                    f"{case['id']}: tools={selected}, reasons={reasons}, answer={answer!r}"
                )
    except Exception as exc:
        raise SystemExit(f"Answer quality provider error: {type(exc).__name__}: {exc}") from exc

    score = passed / len(cases) if cases else 0.0
    print(f"Answer quality score: {passed}/{len(cases)} = {score:.1%}")
    for locale in sorted({case["locale"] for case in cases}):
        locale_passed = by_locale[(locale, True)]
        locale_total = locale_passed + by_locale[(locale, False)]
        print(f"  {locale}: {locale_passed}/{locale_total}")
    for failure in live_failures:
        print(f"FAIL: {failure}")
    if score < args.min_score:
        raise SystemExit(1)
    print("Live answer quality eval passed")


if __name__ == "__main__":
    main()
