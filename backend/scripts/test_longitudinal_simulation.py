"""First offline longitudinal checks based on the profiles workbook.

The script never contacts GigaChat or the real Supabase project. It validates
profile generation, replays Anna's 14-day timeline in memory, verifies the
date-sensitive tools under freezegun, and runs the agent graph with mock LLM.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from freezegun import freeze_time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.graph import run_agent_turn_details  # noqa: E402
from app.agents.router import route_with_keywords  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import _get_mock_llm, get_router_llm  # noqa: E402
from simulation.profiles import (  # noqa: E402
    FIXTURES_DIR,
    generate_profiles,
    load_anchor_profiles,
)
from app.tools import nutrition, profile, recovery, workout  # noqa: E402
from app.tools.registry import build_tools  # noqa: E402

SCENARIO_PATH = FIXTURES_DIR / "anna_14d.json"


@dataclass
class _Result:
    data: list[dict]


class _Query:
    def __init__(self, store: "_MemorySupabase", table_name: str):
        self.store = store
        self.table_name = table_name
        self.rows = deepcopy(store.tables.get(table_name, []))
        self.limit_count: int | None = None

    def select(self, *_args, **_kwargs) -> "_Query":
        return self

    def eq(self, field: str, value) -> "_Query":
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def gte(self, field: str, value) -> "_Query":
        self.rows = [row for row in self.rows if row.get(field, "") >= value]
        return self

    def order(self, field: str, desc: bool = False) -> "_Query":
        self.rows.sort(key=lambda row: row.get(field, ""), reverse=desc)
        return self

    def limit(self, count: int) -> "_Query":
        self.limit_count = count
        return self

    def insert(self, payload: dict) -> "_Query":
        self.store.tables.setdefault(self.table_name, []).append(deepcopy(payload))
        self.rows = [deepcopy(payload)]
        return self

    def execute(self) -> _Result:
        rows = self.rows[: self.limit_count] if self.limit_count else self.rows
        return _Result(rows)


class _MemorySupabase:
    def __init__(self, profile_row: dict):
        self.tables: dict[str, list[dict]] = {
            "user_profiles": [profile_row],
            "meal_logs": [],
            "weight_logs": [],
            "workout_logs": [],
            "user_health_logs": [],
        }

    def table(self, table_name: str) -> _Query:
        return _Query(self, table_name)


def _load_scenario() -> dict:
    return json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))


def _profile_row(persona) -> dict:
    return {
        "user_id": persona.persona_id,
        "age": persona.age,
        "sex": persona.sex,
        "height_cm": persona.height_cm,
        "weight_kg": persona.weight_kg,
        "goal": persona.goal,
        "calorie_target": persona.calorie_target,
        "protein_target_g": persona.protein_target_g,
        "carb_target_g": persona.carb_target_g,
        "fat_target_g": persona.fat_target_g,
        "allergies": persona.allergies,
        "disliked_foods": [],
        "favorite_foods": persona.favorite_foods,
        "budget": persona.budget,
        "cooking_skill": persona.cooking_skill,
        "onboarding_complete": True,
        "updated_at": persona.start_at,
    }


def _at(start_at: str, day: int, clock: str) -> datetime:
    start = datetime.fromisoformat(start_at)
    hour, minute = (int(part) for part in clock.split(":"))
    return (start + timedelta(days=day)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def _apply_event(store: _MemorySupabase, user_id: str, at: datetime, event: dict) -> None:
    payload = {"user_id": user_id, "date": at.date().isoformat(), **event["payload"]}
    table_name = {
        "weight": "weight_logs",
        "meal": "meal_logs",
        "workout": "workout_logs",
        "health_checkin": "user_health_logs",
    }.get(event["event_type"])
    if table_name is None:
        raise AssertionError(f"Unsupported first-run event: {event['event_type']}")
    store.tables[table_name].append(payload)


def check_profiles_and_generation() -> dict:
    anchors = load_anchor_profiles()
    assert len(anchors) == 12
    assert len({profile.persona_id for profile in anchors}) == len(anchors)
    assert all(profile.budget in {"low", "medium", "high"} for profile in anchors)

    generated_once = generate_profiles(24, seed=42, anchors=anchors)
    generated_twice = generate_profiles(24, seed=42, anchors=anchors)
    assert generated_once == generated_twice
    assert len({profile.persona_id for profile in generated_once}) == 24

    normalized = [
        profile.persona_id
        for profile in anchors
        if profile.normalization_notes
    ]
    return {
        "anchor_profiles": len(anchors),
        "generated_profiles": len(generated_once),
        "deterministic_seed": 42,
        "normalized_anchor_profiles": normalized,
    }


def check_timeline_and_date_sensitive_tools() -> dict:
    scenario = _load_scenario()
    persona = next(
        item
        for item in load_anchor_profiles()
        if item.persona_id == scenario["persona_id"]
    )
    store = _MemorySupabase(_profile_row(persona))
    events = sorted(
        scenario["events"],
        key=lambda item: (item["day"], item["time"]),
    )
    timepoints = [
        scenario["checkpoints"][0],
        {
            "checkpoint_id": "anna_d1_meal_visibility",
            "day": 1,
            "time": "14:00",
        },
        *scenario["checkpoints"][1:],
    ]
    applied: set[tuple[int, str, str]] = set()
    observations: list[dict] = []

    with (
        patch("app.tools.profile.get_supabase", return_value=store),
        patch("app.tools.nutrition.get_supabase", return_value=store),
        patch("app.tools.recovery.get_supabase", return_value=store),
        patch("app.tools.workout.get_supabase", return_value=store),
    ):
        for checkpoint in timepoints:
            checkpoint_at = _at(
                persona.start_at,
                checkpoint["day"],
                checkpoint["time"],
            )
            for event in events:
                key = (event["day"], event["time"], event["event_type"])
                event_at = _at(persona.start_at, event["day"], event["time"])
                if event_at <= checkpoint_at and key not in applied:
                    _apply_event(store, persona.persona_id, event_at, event)
                    applied.add(key)

            with freeze_time(checkpoint_at):
                profile_result = profile.get_profile(persona.persona_id)
                trend = recovery.get_weight_trend(persona.persona_id, days=30)
                intake = nutrition.get_daily_intake(persona.persona_id)
                workouts = workout.get_workout_history(persona.persona_id, days=14)

            observations.append(
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "frozen_at": checkpoint_at.isoformat(),
                    "profile_status": profile_result["status"],
                    "weight_entries": len(trend["weights"]),
                    "weight_delta_kg": trend["delta_kg"],
                    "meals_today": intake["meals_count"],
                    "workouts_in_window": len(workouts["workouts"]),
                }
            )

    assert observations[0]["weight_entries"] == 1
    assert observations[0]["weight_delta_kg"] is None
    assert observations[1]["meals_today"] == 1
    assert observations[2]["weight_entries"] == 2
    assert observations[2]["weight_delta_kg"] == -0.6
    assert observations[2]["workouts_in_window"] == 1
    assert observations[3]["weight_entries"] == 3
    assert observations[3]["weight_delta_kg"] == -1.1
    return {"scenario_id": scenario["scenario_id"], "observations": observations}


def check_mock_agent_replay() -> dict:
    scenario = _load_scenario()
    persona = next(
        item
        for item in load_anchor_profiles()
        if item.persona_id == scenario["persona_id"]
    )
    history: list[dict[str, str]] = []
    turns: list[dict] = []
    _get_mock_llm.cache_clear()
    get_router_llm.cache_clear()

    with (
        patch.object(settings, "llm_provider", "mock"),
        patch.object(settings, "mock_llm_latency_ms", 0),
        patch.object(settings, "rag_enabled", False),
        patch("app.services.agent_traces.call_with_circuit_breaker") as breaker,
    ):
        for checkpoint in scenario["checkpoints"]:
            checkpoint_at = _at(
                persona.start_at,
                checkpoint["day"],
                checkpoint["time"],
            )
            with freeze_time(checkpoint_at):
                result = run_agent_turn_details(
                    persona.persona_id,
                    checkpoint["message"],
                    persona.locale,
                    history=history,
                )
            assert result["answer"].startswith("[MOCK:")
            history.extend(
                [
                    {"role": "user", "content": checkpoint["message"]},
                    {"role": "assistant", "content": result["answer"]},
                ]
            )

            available_tools = {
                tool.name
                for tool in _tools_for_route(
                    route_with_keywords(checkpoint["message"]),
                    persona.persona_id,
                )
            }
            missing_tools = sorted(set(checkpoint["expected_tools"]) - available_tools)
            turns.append(
                {
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "route": result["route"],
                    "answer": result["answer"],
                    "quality_assertions": "skipped_for_infrastructure_mock",
                    "missing_expected_tools_on_mock_route": missing_tools,
                }
            )

    breaker.assert_not_called()
    return {
        "external_llm_calls": 0,
        "conversation_history_messages": len(history),
        "turns": turns,
    }


def _tools_for_route(route: str, user_id: str):
    domains = {
        "nutrition": ("profile", "nutrition", "recovery"),
        "workout": ("profile", "workout"),
        "recovery": ("profile", "recovery", "calendar"),
        "general": (),
    }[route]
    return build_tools(user_id, domains=domains) if domains else []


if __name__ == "__main__":
    report = {
        "profiles": check_profiles_and_generation(),
        "timeline": check_timeline_and_date_sensitive_tools(),
        "mock_agent": check_mock_agent_replay(),
        "status": "foundation_checks_passed",
        "answer_quality": (
            "not_measured: the deterministic mock validates orchestration only"
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
