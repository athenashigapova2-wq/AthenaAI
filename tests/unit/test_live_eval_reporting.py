import json

from scripts.eval_longitudinal_quality import sanitized_ci_report, write_sanitized_ci_report


def _report() -> dict:
    return {
        "provider": "gigachat",
        "model": "GigaChat",
        "scenario_count": 1,
        "scenarios_passed": 0,
        "food_database": {"mode": "committed_read_only_snapshot", "remote_reads": 0},
        "evaluation_layers": {"hard_invariants": "blocking_deterministic"},
        "scenarios": [
            {
                "scenario_id": "elena_14d_v1",
                "persona_id": "synthetic-persona",
                "checkpoints_passed": 0,
                "checkpoints_total": 1,
                "results": [
                    {
                        "checkpoint_id": "elena_d0_plan",
                        "question": "raw prompt must not enter CI artifact",
                        "answer": "raw model answer must not enter CI artifact",
                        "route": "nutrition",
                        "tool_calls": [
                            {
                                "name": "submit_daily_nutrition_plan",
                                "args": {"private": "raw tool args"},
                                "result": {
                                    "status": "invalid",
                                    "issues": ["meal 2 may contain a profile allergen: yogurt"],
                                },
                                "read_only": True,
                                "error": None,
                            }
                        ],
                        "hard_invariants": {
                            "passed": False,
                            "checks": {"allergens": False},
                            "evidence": {"profile": {"allergies": ["milk"]}},
                            "metrics": {},
                        },
                        "semantic_quality": {"status": "not_run"},
                        "evaluation": {"passed": False},
                    }
                ],
            }
        ],
    }


def test_ci_report_keeps_failure_metadata_without_raw_content(tmp_path) -> None:
    source = _report()
    sanitized = sanitized_ci_report(source)
    serialized = json.dumps(sanitized)

    assert "elena_d0_plan" in serialized
    assert "profile allergen: yogurt" in serialized
    assert "raw prompt" not in serialized
    assert "raw model answer" not in serialized
    assert "raw tool args" not in serialized
    assert "synthetic-persona" not in serialized
    assert '"profile"' not in serialized

    path = write_sanitized_ci_report(source, tmp_path, "report")
    assert json.loads(path.read_text(encoding="utf-8")) == sanitized
