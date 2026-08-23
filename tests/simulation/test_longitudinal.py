"""Every discovered longitudinal scenario runs with frozen time and mock LLM."""

import json

import pytest

from simulation.longitudinal import (
    check_profiles_and_generation,
    replay_mock_agent,
    replay_timeline,
    write_reports,
)
from simulation.scenarios import SCENARIO_SELECTION_ENV, load_scenarios


pytestmark = pytest.mark.simulation
SCENARIOS = load_scenarios()


def test_profiles_and_generation() -> None:
    report = check_profiles_and_generation()
    assert report


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.scenario_id)
def test_timeline_and_checkpoint_contracts(scenario) -> None:
    report = replay_timeline(scenario)
    failures = {
        item["checkpoint_id"]: item["contract_issues"]
        for item in report["checkpoints"]
        if item["contract_issues"]
    }
    assert report["checkpoints_passed"] == report["checkpoints_total"], failures


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.scenario_id)
def test_mock_agent_replay(scenario) -> None:
    report = replay_mock_agent(scenario)
    assert report["external_llm_calls"] == 0


def test_scenario_discovery_and_environment_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(SCENARIO_SELECTION_ENV, raising=False)
    template = {
        "source": "test",
        "persona_id": "persona",
        "timezone": "Europe/Moscow",
        "events": [],
        "checkpoints": [
            {
                "checkpoint_id": "checkpoint",
                "day": 0,
                "time": "09:00",
                "conversation_id": "main",
                "turn": 1,
                "message": "hello",
                "rubric": "contract",
            }
        ],
    }
    for days in (14, 30):
        payload = {**template, "scenario_id": f"scenario_{days}", "duration_days": days}
        (tmp_path / f"persona_{days}d.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    assert [item.scenario_id for item in load_scenarios(fixtures_dir=tmp_path)] == [
        "scenario_14",
        "scenario_30",
    ]
    monkeypatch.setenv(SCENARIO_SELECTION_ENV, "scenario_30")
    assert [item.scenario_id for item in load_scenarios(fixtures_dir=tmp_path)] == [
        "scenario_30"
    ]


def test_json_and_markdown_report_writer(tmp_path) -> None:
    report = {
        "status": "passed",
        "scenario_count": 1,
        "scenarios": [
            {
                "scenario_id": "scenario",
                "persona_id": "persona",
                "passed": True,
                "timeline": {
                    "checkpoints_passed": 1,
                    "checkpoints_total": 1,
                    "checkpoints": [],
                },
            }
        ],
    }
    json_path, markdown_path = write_reports(report, tmp_path, "report")
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "passed"
    assert "scenario" in markdown_path.read_text(encoding="utf-8")
