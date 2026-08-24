"""Deterministic contract tests for structured calorie decisions."""

import pytest
from pydantic import ValidationError

from app.agents.nutrition.calorie_policy import (
    MIN_CALORIE_TARGET,
    _calorie_decision_tool,
)
from app.api.agent import AgentJobResponse


PROFILE = {
    "status": "ok",
    "profile": {"calorie_target": 1_800},
}
TREND = {
    "status": "ok",
    "weights": [
        {"date": "2026-08-01", "weight_kg": 75.0},
        {"date": "2026-08-15", "weight_kg": 74.2},
    ],
    "delta_kg": -0.8,
}


def test_calorie_decision_returns_auditable_structure() -> None:
    result = _calorie_decision_tool(PROFILE, TREND, "ru").invoke(
        {
            "action": "decrease",
            "proposed_calories": 1_700,
            "rationale": "Темп снижения веса замедлился.",
        }
    )

    assert result["status"] == "ok"
    assert result["calorie_decision"] == {
        "action": "decrease",
        "current_calories": 1_800.0,
        "proposed_calories": 1_700.0,
        "minimum_calories": MIN_CALORIE_TARGET,
        "change_kcal": -100.0,
        "weight_records": 2,
        "evidence_period": {"start": "2026-08-01", "end": "2026-08-15"},
        "rationale": "Темп снижения веса замедлился.",
    }


def test_calorie_decision_rejects_below_minimum() -> None:
    result = _calorie_decision_tool(PROFILE, TREND, "ru").invoke(
        {
            "action": "decrease",
            "proposed_calories": 1_100,
            "rationale": "Ускорить снижение веса.",
        }
    )

    assert result["status"] == "rejected"
    assert any("below minimum" in issue for issue in result["issues"])


def test_calorie_change_rejects_insufficient_weight_evidence() -> None:
    one_record = {
        "status": "ok",
        "weights": [{"date": "2026-08-15", "weight_kg": 74.2}],
        "delta_kg": None,
    }
    result = _calorie_decision_tool(PROFILE, one_record, "ru").invoke(
        {
            "action": "increase",
            "proposed_calories": 1_900,
            "rationale": "Изменить цель.",
        }
    )

    assert result["status"] == "rejected"
    assert any("at least two weight records" in issue for issue in result["issues"])


def test_keep_is_allowed_without_a_weight_change_claim() -> None:
    result = _calorie_decision_tool(PROFILE, {"status": "ok", "weights": []}, "en").invoke(
        {
            "action": "keep",
            "proposed_calories": 1_800,
            "rationale": "Collect more measurements before changing the target.",
        }
    )

    assert result["status"] == "ok"
    assert result["calorie_decision"]["action"] == "keep"


def test_job_response_exposes_a_typed_calorie_decision() -> None:
    response = AgentJobResponse.model_validate(
        {
            "job_id": "job-1",
            "status": "succeeded",
            "calorie_decision": {
                "action": "decrease",
                "current_calories": 1_800,
                "proposed_calories": 1_700,
                "minimum_calories": MIN_CALORIE_TARGET,
                "change_kcal": -100,
                "weight_records": 2,
                "evidence_period": {
                    "start": "2026-08-01",
                    "end": "2026-08-15",
                },
                "rationale": "Проверенный тренд веса.",
            },
        }
    )

    assert response.calorie_decision is not None
    assert response.calorie_decision.action == "decrease"
    assert response.calorie_decision.evidence_period.start == "2026-08-01"


def test_job_response_rejects_an_unknown_calorie_action() -> None:
    with pytest.raises(ValidationError):
        AgentJobResponse.model_validate(
            {
                "job_id": "job-1",
                "status": "succeeded",
                "calorie_decision": {
                    "action": "recalculate",
                    "current_calories": 1_800,
                    "proposed_calories": 1_700,
                    "minimum_calories": MIN_CALORIE_TARGET,
                    "change_kcal": -100,
                    "weight_records": 2,
                    "evidence_period": {"start": None, "end": None},
                    "rationale": "Invalid action.",
                },
            }
        )
