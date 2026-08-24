"""Discovery and validation for longitudinal simulation scenarios."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from simulation.profiles import FIXTURES_DIR

SCENARIO_SELECTION_ENV = "ATHENA_SIMULATION_SCENARIOS"
LIVE_SCENARIO_SELECTION_ENV = "ATHENA_LIVE_SCENARIOS"
SCENARIO_FILENAME = re.compile(r"^.+_(1[4-9]|2[0-9]|30)d\.json$")


class ScenarioEvent(BaseModel):
    day: int = Field(ge=0)
    time: str
    event_type: Literal["weight", "meal", "workout", "health_checkin"]
    payload: dict[str, Any]


class ExpectedFacts(BaseModel):
    """Facts computed from the frozen in-memory timeline."""

    profile: dict[str, Any] = Field(default_factory=dict)
    weight_trend: dict[str, Any] = Field(default_factory=dict)
    daily_intake: dict[str, Any] = Field(default_factory=dict)
    workout_history: dict[str, Any] = Field(default_factory=dict)
    answer_patterns: list[str] = Field(default_factory=list)


class NutritionExpectation(BaseModel):
    calorie_target: float | None = Field(default=None, ge=0)
    protein_target_g: float | None = Field(default=None, ge=0)
    carb_target_g: float | None = Field(default=None, ge=0)
    fat_target_g: float | None = Field(default=None, ge=0)
    macro_energy_tolerance_kcal: float = Field(default=80, ge=0)
    target_tolerance_ratio: float = Field(default=0.1, ge=0, le=0.5)
    require_server_validation: bool = False


class SafetyExpectation(BaseModel):
    minimum_calories: float = Field(default=1_200, ge=0)
    require_weight_trend_before_calorie_change: bool = False
    forbidden_patterns: list[str] = Field(default_factory=list)


class HardInvariantExpectation(BaseModel):
    """Deterministic permissions and persistence contract for one checkpoint."""

    allowed_write_tools: list[str] = Field(default_factory=list)
    max_db_writes: int = Field(default=0, ge=0)


class ScenarioCheckpoint(BaseModel):
    checkpoint_id: str
    day: int = Field(ge=0)
    time: str
    conversation_id: str
    turn: int = Field(ge=1)
    message: str
    expected_route: Literal["nutrition", "workout", "recovery", "general"] | None = None
    expected_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    expected_facts: ExpectedFacts = Field(default_factory=ExpectedFacts)
    nutrition: NutritionExpectation | None = None
    safety: SafetyExpectation = Field(default_factory=SafetyExpectation)
    hard_invariants: HardInvariantExpectation = Field(
        default_factory=HardInvariantExpectation
    )
    rubric: str


class LongitudinalScenario(BaseModel):
    scenario_id: str
    source: str
    persona_id: str
    timezone: str = "Europe/Moscow"
    duration_days: int = Field(ge=14, le=30)
    events: list[ScenarioEvent]
    checkpoints: list[ScenarioCheckpoint]
    fixture_path: Path | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_timeline(self) -> "LongitudinalScenario":
        checkpoint_ids = [item.checkpoint_id for item in self.checkpoints]
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise ValueError("checkpoint_id values must be unique")
        if not self.checkpoints:
            raise ValueError("scenario must contain at least one checkpoint")
        for item in [*self.events, *self.checkpoints]:
            if item.day > self.duration_days:
                raise ValueError(
                    f"day {item.day} exceeds duration_days={self.duration_days}"
                )
        return self


def discover_scenario_paths(fixtures_dir: Path = FIXTURES_DIR) -> list[Path]:
    """Find every 14-to-30-day fixture deterministically."""
    paths = {
        path.resolve()
        for path in fixtures_dir.glob("*.json")
        if path.is_file() and SCENARIO_FILENAME.fullmatch(path.name)
    }
    return sorted(paths, key=lambda path: path.name.casefold())


def load_scenario(path: Path) -> LongitudinalScenario:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenario = LongitudinalScenario.model_validate(payload)
    scenario.fixture_path = path.resolve()
    expected_suffix = f"_{scenario.duration_days}d.json"
    if not path.name.endswith(expected_suffix):
        raise ValueError(
            f"{path.name} duration_days does not match suffix {expected_suffix}"
        )
    return scenario


def _selectors_from_env(env_name: str) -> set[str]:
    return {
        item.strip()
        for item in os.getenv(env_name, "").split(",")
        if item.strip()
    }


def load_scenarios(
    *,
    env_name: str = SCENARIO_SELECTION_ENV,
    fixtures_dir: Path = FIXTURES_DIR,
) -> list[LongitudinalScenario]:
    """Load all fixtures, or only comma-separated selectors from an env var.

    A selector may be a scenario id, persona id, filename, or filename stem.
    Unknown selectors fail loudly so CI cannot silently run the wrong scenario.
    """
    scenarios = [load_scenario(path) for path in discover_scenario_paths(fixtures_dir)]
    if not scenarios:
        raise ValueError(f"No longitudinal fixtures found in {fixtures_dir}")

    selectors = _selectors_from_env(env_name)
    if not selectors:
        return scenarios

    selected = [
        scenario
        for scenario in scenarios
        if selectors.intersection(
            {
                scenario.scenario_id,
                scenario.persona_id,
                scenario.fixture_path.name if scenario.fixture_path else "",
                scenario.fixture_path.stem if scenario.fixture_path else "",
            }
        )
    ]
    matched = {
        selector
        for selector in selectors
        if any(
            selector
            in {
                scenario.scenario_id,
                scenario.persona_id,
                scenario.fixture_path.name if scenario.fixture_path else "",
                scenario.fixture_path.stem if scenario.fixture_path else "",
            }
            for scenario in selected
        )
    }
    missing = sorted(selectors - matched)
    if missing:
        raise ValueError(f"Unknown longitudinal scenario selectors: {missing}")
    return selected
