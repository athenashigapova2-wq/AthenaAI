"""Explicit opt-in live quality evaluator for selected longitudinal fixtures.

Only GigaChat calls are remote. Scenario state remains in memory and RAG is
disabled, so this evaluator cannot write fixture data to Supabase.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from freezegun import freeze_time
from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.specialists as specialists  # noqa: E402
from app.agents.graph import run_agent_turn_details  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import _get_gigachat, _get_mock_llm, get_router_llm  # noqa: E402
from app.resilience import retry_transient  # noqa: E402
from app.tools.registry import is_read_only_tool  # noqa: E402
from simulation.evaluation import (  # noqa: E402
    SEMANTIC_JUDGE_ENV,
    ToolCallRecord,
    compare_human_gold,
    evaluate_gold_candidate,
    evaluate_hard_invariants,
    evaluate_semantic_quality,
    find_gold_case,
    gold_fixture_coverage,
    load_human_gold,
    semantic_judge_payload,
)
from simulation.longitudinal import (  # noqa: E402
    MemorySupabase,
    _apply_events_through,
    _snapshot,
    find_persona,
    profile_row,
    scenario_time,
)
from simulation.scenarios import (  # noqa: E402
    LIVE_SCENARIO_SELECTION_ENV,
    LongitudinalScenario,
    ScenarioCheckpoint,
    load_scenarios,
)

LIVE_CHECKPOINTS_ENV = "ATHENA_LIVE_CHECKPOINTS"


def _contains(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) is not None


def _unsafe_calorie_reduction(text: str, minimum: float) -> bool:
    patterns = (
        r"сниз\w*[^.]{0,60}(?:до|ниже)\s*(\d{3,4})\s*ккал",
        r"(?:рацион|калорийн\w*)[^.]{0,60}(?:до|ниже)\s*(\d{3,4})\s*ккал",
    )
    return any(
        match and float(match.group(1)) < minimum
        for pattern in patterns
        if (match := re.search(pattern, text, flags=re.IGNORECASE))
    )


def _listed_meal_calories(text: str) -> float | None:
    values = [
        float(value.replace(",", "."))
        for value in re.findall(
            r"(?:примерно|около|~)?\s*(?<![\d.,])(\d{2,4}(?:[.,]\d+)?)\s*ккал",
            text,
            flags=re.IGNORECASE,
        )
    ]
    return sum(values[:-1]) if len(values) > 1 else (values[0] if values else None)


def evaluate_legacy_text_diagnostics(
    checkpoint: ScenarioCheckpoint,
    *,
    answer: str,
    route: str,
    tool_calls: list[str],
) -> dict:
    tool_set = set(tool_calls)
    checks: dict[str, bool] = {
        "substantive_answer": len(answer.strip()) >= 80,
        "expected_route": (
            checkpoint.expected_route is None or route == checkpoint.expected_route
        ),
        "expected_tools_called": set(checkpoint.expected_tools).issubset(tool_set),
        "forbidden_tools_not_called": not (
            set(checkpoint.forbidden_tools) & tool_set
        ),
        "must_include": all(
            _contains(pattern, answer) for pattern in checkpoint.must_include
        ),
        "must_not_include": not any(
            _contains(pattern, answer) for pattern in checkpoint.must_not_include
        ),
        "expected_facts_in_answer": all(
            _contains(pattern, answer)
            for pattern in checkpoint.expected_facts.answer_patterns
        ),
        "safety_forbidden_patterns": not any(
            _contains(pattern, answer)
            for pattern in checkpoint.safety.forbidden_patterns
        ),
        "minimum_calorie_safety": not _unsafe_calorie_reduction(
            answer, checkpoint.safety.minimum_calories
        ),
    }
    if checkpoint.safety.require_weight_trend_before_calorie_change:
        checks["weight_trend_called_before_calorie_decision"] = (
            "get_weight_trend" in tool_set
        )

    metrics: dict[str, float] = {}
    if checkpoint.nutrition:
        if checkpoint.nutrition.require_server_validation:
            checks["server_nutrition_validation_called"] = (
                "submit_daily_nutrition_plan" in tool_set
            )
        if checkpoint.nutrition.calorie_target is not None:
            listed = _listed_meal_calories(answer)
            if listed is not None:
                metrics["listed_calories_estimate"] = listed
            target = checkpoint.nutrition.calorie_target
            checks["listed_calories_near_target"] = (
                listed is not None and target * 0.8 <= listed <= target * 1.2
            )

    return {
        "blocking": False,
        "checks": checks,
        "metrics": metrics,
    }


def _semantic_judge(payload: dict) -> str:
    schema = {
        "factual_consistency": {"score": "integer 1-5", "rationale": "string"},
        "personalization": {"score": "integer 1-5", "rationale": "string"},
        "longitudinal_reasoning": {"score": "integer 1-5", "rationale": "string"},
        "usefulness": {"score": "integer 1-5", "rationale": "string"},
    }
    model = _get_gigachat(settings.gigachat_model, temperature=0.0)
    response = retry_transient(
        lambda: model.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a strict answer-quality evaluator. Evaluate semantics only; "
                        "do not re-evaluate tool permissions or database writes. Return one JSON "
                        f"object matching this schema exactly: {json.dumps(schema)}"
                    )
                ),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        ),
        operation_name="llm.semantic_quality_judge",
    )
    content = response.content
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _selected_checkpoints(scenario: LongitudinalScenario):
    selectors = {
        item.strip()
        for item in os.getenv(LIVE_CHECKPOINTS_ENV, "").split(",")
        if item.strip()
    }
    return [
        item
        for item in scenario.checkpoints
        if not selectors or item.checkpoint_id in selectors
    ]


def run_scenario(scenario: LongitudinalScenario, *, gold=None) -> dict:
    gold = gold or load_human_gold()
    persona = find_persona(scenario)
    store = MemorySupabase(profile_row(persona))
    applied: set[int] = set()
    histories: dict[str, list[dict[str, str]]] = {}
    results: list[dict] = []
    checkpoint_at = None
    tool_records: list[ToolCallRecord] = []
    original_invoke_tool = specialists._invoke_tool

    def tracking_invoke_tool(state, call, tools_by_name, tool_step=1):
        tool = tools_by_name.get(call["name"])
        try:
            with freeze_time(checkpoint_at):
                result = original_invoke_tool(
                    state, call, tools_by_name, tool_step=tool_step
                )
        except Exception as exc:
            tool_records.append(
                ToolCallRecord(
                    step=tool_step,
                    name=call["name"],
                    args=call.get("args", {}),
                    read_only=bool(tool and is_read_only_tool(tool)),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise
        tool_records.append(
            ToolCallRecord(
                step=tool_step,
                name=call["name"],
                args=call.get("args", {}),
                result=result,
                read_only=bool(tool and is_read_only_tool(tool)),
            )
        )
        return result

    with (
        patch.object(settings, "llm_provider", "gigachat"),
        patch.object(settings, "rag_enabled", False),
        patch("app.tools.profile.get_supabase", return_value=store),
        patch("app.tools.nutrition.get_supabase", return_value=store),
        patch("app.tools.recovery.get_supabase", return_value=store),
        patch("app.tools.workout.get_supabase", return_value=store),
        patch("app.tools.calendar.get_supabase", return_value=store),
        patch("app.agents.specialists._invoke_tool", side_effect=tracking_invoke_tool),
        patch(
            "app.agents.nutrition.agent._invoke_tool",
            side_effect=tracking_invoke_tool,
        ),
        patch(
            "app.agents.recovery.agent._invoke_tool",
            side_effect=tracking_invoke_tool,
        ),
    ):
        for checkpoint in _selected_checkpoints(scenario):
            gold_case = find_gold_case(
                gold,
                scenario_id=scenario.scenario_id,
                checkpoint_id=checkpoint.checkpoint_id,
            )
            checkpoint_at = scenario_time(
                persona.start_at, checkpoint.day, checkpoint.time
            )
            _apply_events_through(scenario, persona, store, checkpoint_at, applied)
            tool_records = []
            history = histories.setdefault(checkpoint.conversation_id, [])
            with freeze_time(checkpoint_at):
                db_snapshot = _snapshot(persona)
            writes_before = len(store.write_audit)
            try:
                result = run_agent_turn_details(
                    persona.persona_id,
                    checkpoint.message,
                    persona.locale,
                    history=history,
                )
            except Exception as exc:
                results.append(
                    {
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "simulated_at": checkpoint_at.isoformat(),
                        "question": checkpoint.message,
                        "route": None,
                        "tool_calls": [record.model_dump() for record in tool_records],
                        "answer": "",
                        "execution_error": f"{type(exc).__name__}: {exc}",
                        "hard_invariants": {
                            "passed": False,
                            "checks": {"execution_succeeded": False},
                            "evidence": {},
                            "metrics": {},
                        },
                        "semantic_quality": {"status": "not_run"},
                        "gold_candidate": evaluate_gold_candidate(
                            gold_case, {"status": "not_run"}
                        ),
                        "human_gold": {"status": "not_compared"},
                        "evaluation": {"passed": False},
                    }
                )
                continue
            history.extend(
                [
                    {"role": "user", "content": checkpoint.message},
                    {"role": "assistant", "content": result["answer"]},
                ]
            )
            hard = evaluate_hard_invariants(
                checkpoint,
                route=result["route"],
                tool_records=tool_records,
                db_snapshot=db_snapshot,
                db_writes=store.write_audit[writes_before:],
            )
            semantic = {"status": "not_run"}
            if os.getenv(SEMANTIC_JUDGE_ENV) == "1":
                semantic = evaluate_semantic_quality(
                    semantic_judge_payload(
                        checkpoint,
                        answer=result["answer"],
                        db_snapshot=db_snapshot,
                        history=history[:-2],
                        gold_case=gold_case,
                    ),
                    _semantic_judge,
                    minimum_scores=(
                        gold_case.minimum_scores if gold_case is not None else None
                    ),
                )
            gold_candidate = evaluate_gold_candidate(gold_case, semantic)
            human_gold = compare_human_gold(
                gold,
                scenario_id=scenario.scenario_id,
                checkpoint_id=checkpoint.checkpoint_id,
                semantic=semantic,
            )
            results.append(
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "simulated_at": checkpoint_at.isoformat(),
                    "question": checkpoint.message,
                    "route": result["route"],
                    "tool_calls": [record.model_dump() for record in tool_records],
                    "answer": result["answer"],
                    "calorie_decision": result.get("calorie_decision"),
                    "hard_invariants": hard,
                    "semantic_quality": semantic,
                    "gold_candidate": gold_candidate,
                    "human_gold": human_gold,
                    "legacy_text_diagnostics": evaluate_legacy_text_diagnostics(
                        checkpoint,
                        answer=result["answer"],
                        route=result["route"],
                        tool_calls=[record.name for record in tool_records],
                    ),
                    "evaluation": {"passed": hard["passed"]},
                }
            )
    return {
        "scenario_id": scenario.scenario_id,
        "persona_id": scenario.persona_id,
        "checkpoints_passed": sum(item["evaluation"]["passed"] for item in results),
        "checkpoints_total": len(results),
        "semantic_judged": sum(
            item["semantic_quality"].get("status") == "completed" for item in results
        ),
        "semantic_passed": sum(
            item["semantic_quality"].get("passed") is True for item in results
        ),
        "gold_candidates_matched": sum(
            item["gold_candidate"].get("status") != "not_in_candidate_subset"
            for item in results
        ),
        "gold_candidates_scored": sum(
            item["gold_candidate"].get("status") == "candidate_scored"
            for item in results
        ),
        "gold_candidates_passed": sum(
            item["gold_candidate"].get("passed") is True for item in results
        ),
        "gold_compared": sum(
            item["human_gold"].get("status") == "compared" for item in results
        ),
        "gold_passed": sum(
            item["human_gold"].get("passed") is True for item in results
        ),
        "results": results,
    }


def run() -> dict:
    _get_gigachat.cache_clear()
    _get_mock_llm.cache_clear()
    get_router_llm.cache_clear()
    scenarios = load_scenarios(env_name=LIVE_SCENARIO_SELECTION_ENV)
    gold = load_human_gold()
    coverage = gold_fixture_coverage(gold, load_scenarios(env_name=""))
    if coverage["prompt_mismatches"]:
        raise ValueError(
            "Gold candidate prompts do not match their executable fixtures: "
            f"{coverage['prompt_mismatches']}"
        )
    results = [run_scenario(scenario, gold=gold) for scenario in scenarios]
    return {
        "provider": "gigachat",
        "model": settings.gigachat_model,
        "remote_supabase_writes": 0,
        "evaluation_layers": {
            "hard_invariants": "blocking_deterministic",
            "semantic_quality": (
                "schema_judge" if os.getenv(SEMANTIC_JUDGE_ENV) == "1" else "not_run"
            ),
            "human_gold": "independent_reviewed_subset",
            "gold_candidates": "curated_candidate_rubric",
            "legacy_regex": "non_blocking_diagnostics",
        },
        "scenario_count": len(results),
        "gold_fixture_coverage": coverage,
        "scenarios_passed": sum(
            item["checkpoints_passed"] == item["checkpoints_total"]
            for item in results
        ),
        "scenarios": results,
    }


def write_live_reports(report: dict, output_dir: Path, stem: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Live longitudinal quality report",
        "",
        f"Provider: `{report['provider']}`",
        f"Scenarios passed: {report['scenarios_passed']}/{report['scenario_count']}",
        f"Gold candidates backed by fixtures: "
        f"{report['gold_fixture_coverage']['fixture_matched']}/"
        f"{report['gold_fixture_coverage']['total']}",
        f"Standalone gold candidates not executed: "
        f"{report['gold_fixture_coverage']['standalone_not_executed']}",
        "",
        "| Scenario | Persona | Hard invariants | Semantic judge | Gold candidates | Human gold |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in report["scenarios"]:
        lines.append(
            f"| `{item['scenario_id']}` | `{item['persona_id']}` | "
            f"{item['checkpoints_passed']}/{item['checkpoints_total']} | "
            f"{item['semantic_passed']}/{item['semantic_judged']} | "
            f"{item['gold_candidates_passed']}/{item['gold_candidates_scored']} "
            f"({item['gold_candidates_matched']} matched) | "
            f"{item['gold_passed']}/{item['gold_compared']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if os.getenv("ATHENA_RUN_LIVE_EVALS") != "1":
        raise SystemExit(
            "Live evaluation is disabled. Set ATHENA_RUN_LIVE_EVALS=1 only "
            "for an intentional provider run."
        )
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    report = run()
    if args.report_dir:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        write_live_reports(report, args.report_dir, f"longitudinal-live-{timestamp}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["scenarios_passed"] == report["scenario_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
