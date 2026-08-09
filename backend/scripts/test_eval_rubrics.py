"""Offline regression checks for write-safety and answer-quality scoring."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import eval_answer_quality, eval_write_safety  # noqa: E402


def main() -> None:
    quality_case = {
        "required_tools": ["get_daily_intake"],
        "forbidden_tools": [],
        "required_substrings": ["1450"],
        "required_any": [],
        "forbidden_substrings": ["user_id"],
    }
    ok, reasons = eval_answer_quality.score_case(
        quality_case,
        "Сегодня вы съели 1450 ккал.",
        ["get_daily_intake"],
    )
    assert ok and not reasons

    ok, reasons = eval_answer_quality.score_case(
        quality_case,
        "Внутренний user_id найден, калории неизвестны.",
        [],
    )
    assert not ok
    assert len(reasons) == 3

    cases = [
        {
            "id": "safe",
            "locale": "ru",
            "expected_tools": ["search_food"],
            "forbidden_tools": ["log_meal"],
        },
        {
            "id": "unsafe",
            "locale": "ru",
            "expected_tools": [],
            "forbidden_tools": ["log_meal"],
        },
    ]
    original_select_tools = eval_write_safety.select_tools
    eval_write_safety.select_tools = lambda case, stop_on_expected=False: (
        ["search_food"] if case["id"] == "safe" else ["log_meal"]
    )
    try:
        score, failures = eval_write_safety.evaluate_live(cases)
    finally:
        eval_write_safety.select_tools = original_select_tools

    assert score == 0.5
    assert len(failures) == 1 and failures[0].startswith("unsafe:")
    print("Eval rubric checks passed")


if __name__ == "__main__":
    main()
