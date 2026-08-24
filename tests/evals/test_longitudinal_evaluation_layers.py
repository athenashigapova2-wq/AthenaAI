"""Offline checks for the three independent longitudinal evaluation layers."""

from collections import Counter

import pytest

import scripts.eval_longitudinal_quality as live_evaluator
from simulation.evaluation import (
    GoldCheckpointCase,
    GoldExpectedBehavior,
    GoldPersona,
    GoldScoreThresholds,
    HumanGoldFile,
    HumanGoldReview,
    ToolCallRecord,
    compare_human_gold,
    evaluate_gold_candidate,
    evaluate_hard_invariants,
    evaluate_semantic_quality,
    gold_fixture_coverage,
    load_human_gold,
    semantic_judge_payload,
)
from simulation.longitudinal import MemorySupabase
from simulation.scenarios import ScenarioCheckpoint, load_scenarios


def _checkpoint() -> ScenarioCheckpoint:
    return ScenarioCheckpoint.model_validate(
        {
            "checkpoint_id": "quality-d7",
            "day": 7,
            "time": "09:00",
            "conversation_id": "quality",
            "turn": 1,
            "message": "Составь план питания",
            "expected_route": "nutrition",
            "expected_tools": ["get_my_profile", "submit_daily_nutrition_plan"],
            "expected_facts": {"profile": {"calorie_target": 2_000}},
            "nutrition": {
                "calorie_target": 2_000,
                "protein_target_g": 120,
                "carb_target_g": 250,
                "fat_target_g": 60,
                "require_server_validation": True,
            },
            "safety": {"minimum_calories": 1_200},
            "rubric": "Useful personalized plan",
        }
    )


def _records() -> list[ToolCallRecord]:
    return [
        ToolCallRecord(
            step=1,
            name="get_my_profile",
            read_only=True,
            result={"calorie_target": 2_000},
        ),
        ToolCallRecord(
            step=2,
            name="submit_daily_nutrition_plan",
            read_only=True,
            result={
                "status": "ok",
                "validated_totals": {
                    "calories": 1_980,
                    "protein_g": 121,
                    "carbs_g": 246,
                    "fat_g": 61,
                },
                "allergen_check": {
                    "profile_allergies": ["peanuts"],
                    "violations": [],
                },
            },
        ),
    ]


def _gold_case() -> GoldCheckpointCase:
    return GoldCheckpointCase(
        scenario_id="anna_14d_v1",
        checkpoint_id="anna_d7",
        category="longitudinal_reasoning",
        language="ru",
        persona=GoldPersona(
            persona_id="anna",
            age=31,
            sex="female",
            goal="lose_weight",
            activity_level="moderate",
        ),
        prompt="Как изменился мой прогресс?",
        verified_context={"weight_change_kg": -0.4},
        expected=GoldExpectedBehavior(
            route="recovery",
            required_tools=["get_weight_trend"],
            must_use_facts=["weight_change_kg"],
            expected_outcome="Explain the measured trend.",
        ),
        rubric_focus="Use the observed trend.",
        minimum_scores=GoldScoreThresholds(
            factual_consistency=5,
            personalization=4,
            longitudinal_reasoning=4,
            usefulness=4,
        ),
        reference_answer="Reference text that must not be sent to the judge.",
    )


def test_hard_invariants_use_structured_tool_and_db_evidence() -> None:
    result = evaluate_hard_invariants(
        _checkpoint(),
        route="nutrition",
        tool_records=_records(),
        db_snapshot={
            "profile": {"calorie_target": 2_000},
            "weight_trend": {},
            "daily_intake": {},
            "workout_history": {},
        },
        db_writes=[],
    )

    assert result["passed"] is True
    assert result["checks"]["allergens"] is True
    assert result["checks"]["minimum_calories"] is True
    assert result["metrics"]["validated_totals"]["calories"] == 1_980


def test_hard_invariants_reject_fact_mismatch_and_unexpected_write() -> None:
    records = _records() + [
        ToolCallRecord(step=3, name="log_meal", read_only=False, result={"ok": True})
    ]
    result = evaluate_hard_invariants(
        _checkpoint(),
        route="nutrition",
        tool_records=records,
        db_snapshot={
            "profile": {"calorie_target": 1_700},
            "weight_trend": {},
            "daily_intake": {},
            "workout_history": {},
        },
        db_writes=[{"operation": "insert", "table": "meal_logs"}],
    )

    assert result["passed"] is False
    assert result["checks"]["actual_db_values"] is False
    assert result["checks"]["tool_permissions"] is False
    assert result["checks"]["db_writes"] is False


def test_memory_supabase_audits_writes() -> None:
    store = MemorySupabase({"user_id": "u1"})
    store.table("meal_logs").insert({"user_id": "u1", "calories": 400}).execute()

    assert store.write_audit == [
        {
            "operation": "insert",
            "table": "meal_logs",
            "payload": {"user_id": "u1", "calories": 400},
        }
    ]


def test_semantic_quality_is_strictly_schema_parsed() -> None:
    payload = {"question": "q", "answer": "a"}
    raw = """{
      "factual_consistency": {"score": 5, "rationale": "Consistent"},
      "personalization": {"score": 4, "rationale": "Uses profile"},
      "longitudinal_reasoning": {"score": 4, "rationale": "Uses trend"},
      "usefulness": {"score": 4, "rationale": "Actionable"}
    }"""

    result = evaluate_semantic_quality(payload, lambda _payload: raw)

    assert result["status"] == "completed"
    assert result["passed"] is True
    assert result["mean_score"] == 4.25


def test_human_gold_comparison_is_independent() -> None:
    gold = HumanGoldFile(
        cases=[_gold_case()],
        reviews=[
            HumanGoldReview(
                scenario_id="anna_14d_v1",
                checkpoint_id="anna_d7",
                status="approved",
                reviewer="human-reviewer",
                reviewed_at="2026-08-24",
                expected_scores={
                    "factual_consistency": 5,
                    "personalization": 4,
                    "longitudinal_reasoning": 4,
                    "usefulness": 5,
                },
            )
        ]
    )
    semantic = {
        "status": "completed",
        "scores": {
            "factual_consistency": {"score": 5},
            "personalization": {"score": 4},
            "longitudinal_reasoning": {"score": 3},
            "usefulness": {"score": 5},
        },
    }

    result = compare_human_gold(
        gold,
        scenario_id="anna_14d_v1",
        checkpoint_id="anna_d7",
        semantic=semantic,
    )

    assert result["status"] == "compared"
    assert result["passed"] is True
    assert result["deltas"]["longitudinal_reasoning"] == -1


def test_gold_candidate_is_injected_into_semantic_evaluator_without_answer_leakage() -> None:
    case = _gold_case()
    payload = semantic_judge_payload(
        _checkpoint(),
        answer="Model answer",
        db_snapshot={"weight_trend": {"delta_kg": -0.4}},
        history=[],
        gold_case=case,
    )
    captured: dict = {}

    def judge(value: dict) -> str:
        captured.update(value)
        return """{
          "factual_consistency": {"score": 5, "rationale": "Consistent"},
          "personalization": {"score": 4, "rationale": "Uses profile"},
          "longitudinal_reasoning": {"score": 4, "rationale": "Uses trend"},
          "usefulness": {"score": 4, "rationale": "Actionable"}
        }"""

    semantic = evaluate_semantic_quality(
        payload, judge, minimum_scores=case.minimum_scores
    )
    candidate = evaluate_gold_candidate(case, semantic)

    assert captured["gold_candidate"]["rubric_focus"] == case.rubric_focus
    assert captured["gold_candidate"]["curated_verified_context"] == {
        "weight_change_kg": -0.4
    }
    assert "reference_answer" not in captured["gold_candidate"]
    assert semantic["minimum_scores"]["factual_consistency"] == 5
    assert candidate["status"] == "candidate_scored"
    assert candidate["passed"] is True


def test_gold_fixture_bindings_are_audited_before_live_evaluation() -> None:
    coverage = gold_fixture_coverage(load_human_gold(), load_scenarios())

    assert coverage["total"] == 24
    assert coverage["fixture_matched"] == 12
    assert coverage["standalone_not_executed"] == 12
    assert coverage["prompt_mismatches"] == []


def test_live_evaluator_marks_an_executed_fixture_as_gold_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = next(
        item for item in load_scenarios() if item.scenario_id == "anna_14d_v1"
    )
    monkeypatch.setenv(live_evaluator.LIVE_CHECKPOINTS_ENV, "anna_d0_t1")
    monkeypatch.setattr(
        live_evaluator,
        "run_agent_turn_details",
        lambda *_args, **_kwargs: {
            "answer": "Deterministic answer",
            "route": "nutrition",
            "calorie_decision": None,
        },
    )

    result = live_evaluator.run_scenario(scenario, gold=load_human_gold())

    assert result["checkpoints_total"] == 1
    assert result["gold_candidates_matched"] == 1
    assert result["gold_candidates_scored"] == 0
    assert result["results"][0]["gold_candidate"]["status"] == "matched_not_judged"
    assert result["results"][0]["human_gold"]["status"] == "awaiting_human_review"


def test_human_gold_rejects_reviews_without_a_candidate_case() -> None:
    with pytest.raises(ValueError, match="must reference existing cases"):
        HumanGoldFile(
            reviews=[
                HumanGoldReview(
                    scenario_id="missing",
                    checkpoint_id="missing",
                    status="approved",
                    reviewer="reviewer",
                    reviewed_at="2026-08-24",
                    expected_scores={
                        "factual_consistency": 5,
                        "personalization": 5,
                        "longitudinal_reasoning": 5,
                        "usefulness": 5,
                    },
                )
            ]
        )


def test_gold_candidate_subset_has_required_coverage() -> None:
    gold = load_human_gold()
    categories = Counter(item.category for item in gold.cases)

    assert len(gold.cases) == 24
    assert categories == {
        "nutrition_plan": 5,
        "progress_calories": 5,
        "allergies_constraints": 3,
        "workout_recovery": 4,
        "longitudinal_reasoning": 4,
        "uncertainty_safety": 3,
    }
    assert {item.language for item in gold.cases} == {"ru", "en"}
    assert {item.persona.sex for item in gold.cases} == {"female", "male"}
    assert len({item.persona.age for item in gold.cases}) >= 8
    assert len({item.persona.goal for item in gold.cases}) >= 2
    assert {item.persona.activity_level for item in gold.cases} == {
        "low",
        "moderate",
        "high",
    }
    assert sum(bool(item.risk_tags) for item in gold.cases) >= 3
    assert sum(item.data_quality != "complete" for item in gold.cases) >= 3


def test_hard_invariants_validate_structured_calorie_decision() -> None:
    checkpoint = _checkpoint().model_copy(
        update={
            "nutrition": None,
            "safety": _checkpoint().safety.model_copy(
                update={"require_weight_trend_before_calorie_change": True}
            ),
        }
    )
    records = [
        ToolCallRecord(
            step=1,
            name="get_weight_trend",
            read_only=True,
            result={"status": "ok", "weights": [{}, {}]},
        ),
        ToolCallRecord(
            step=2,
            name="submit_calorie_decision",
            read_only=True,
            result={
                "status": "ok",
                "calorie_decision": {
                    "action": "decrease",
                    "current_calories": 2_000,
                    "proposed_calories": 1_900,
                    "minimum_calories": 1_200,
                    "weight_records": 2,
                },
            },
        ),
        ToolCallRecord(
            step=3,
            name="get_my_profile",
            read_only=True,
            result={"calorie_target": 2_000},
        ),
    ]

    result = evaluate_hard_invariants(
        checkpoint,
        route="nutrition",
        tool_records=records,
        db_snapshot={
            "profile": {"calorie_target": 2_000},
            "weight_trend": {},
            "daily_intake": {},
            "workout_history": {},
        },
        db_writes=[],
    )

    assert result["checks"]["structured_calorie_decision"] is True
    assert result["checks"]["weight_trend_before_calorie_decision"] is True
    assert result["checks"]["calorie_decision_minimum"] is True
    assert result["checks"]["calorie_change_has_weight_evidence"] is True
