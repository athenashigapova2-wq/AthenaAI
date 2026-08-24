"""Reusable offline longitudinal replay and report generation."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from freezegun import freeze_time

from app.agents.graph import run_agent_turn_details
from app.agents.router import route_with_keywords
from app.config import settings
from app.llm import _get_mock_llm, get_router_llm
from app.tools import nutrition, profile, recovery, workout
from app.tools.registry import build_tools
from simulation.profiles import SimulationProfile, generate_profiles, load_anchor_profiles
from simulation.scenarios import LongitudinalScenario, ScenarioCheckpoint


@dataclass
class MemoryResult:
    data: list[dict[str, Any]]


class MemoryQuery:
    def __init__(self, store: "MemorySupabase", table_name: str):
        self.store = store
        self.table_name = table_name
        self.rows = deepcopy(store.tables.get(table_name, []))
        self.limit_count: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> "MemoryQuery":
        return self

    def eq(self, field: str, value: Any) -> "MemoryQuery":
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def gte(self, field: str, value: Any) -> "MemoryQuery":
        self.rows = [row for row in self.rows if row.get(field, "") >= value]
        return self

    def order(self, field: str, desc: bool = False) -> "MemoryQuery":
        self.rows.sort(key=lambda row: row.get(field, ""), reverse=desc)
        return self

    def limit(self, count: int) -> "MemoryQuery":
        self.limit_count = count
        return self

    def insert(self, payload: dict[str, Any]) -> "MemoryQuery":
        self.store.record_write("insert", self.table_name, payload)
        self.store.tables.setdefault(self.table_name, []).append(deepcopy(payload))
        self.rows = [deepcopy(payload)]
        return self

    def execute(self) -> MemoryResult:
        rows = self.rows[: self.limit_count] if self.limit_count else self.rows
        return MemoryResult(rows)


class MemorySupabase:
    """Minimal Supabase substitute used only by simulation tests."""

    def __init__(self, profile_row: dict[str, Any]):
        self.write_audit: list[dict[str, Any]] = []
        self.tables: dict[str, list[dict[str, Any]]] = {
            "user_profiles": [profile_row],
            "meal_logs": [],
            "weight_logs": [],
            "workout_logs": [],
            "user_health_logs": [],
        }

    def record_write(self, operation: str, table_name: str, payload: dict[str, Any]) -> None:
        self.write_audit.append(
            {
                "operation": operation,
                "table": table_name,
                "payload": deepcopy(payload),
            }
        )

    def table(self, table_name: str) -> MemoryQuery:
        return MemoryQuery(self, table_name)


def profile_row(persona: SimulationProfile) -> dict[str, Any]:
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
        "dietary_pattern": persona.dietary_pattern,
        "dietary_restrictions": persona.dietary_restrictions,
        "disliked_foods": [],
        "favorite_foods": persona.favorite_foods,
        "budget": persona.budget,
        "cooking_skill": persona.cooking_skill,
        "onboarding_complete": True,
        "updated_at": persona.start_at,
    }


def scenario_time(start_at: str, day: int, clock: str) -> datetime:
    start = datetime.fromisoformat(start_at)
    hour, minute = (int(part) for part in clock.split(":"))
    return (start + timedelta(days=day)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )


def apply_event(
    store: MemorySupabase,
    user_id: str,
    at: datetime,
    event: Any,
) -> None:
    payload = {"user_id": user_id, "date": at.date().isoformat(), **event.payload}
    table_name = {
        "weight": "weight_logs",
        "meal": "meal_logs",
        "workout": "workout_logs",
        "health_checkin": "user_health_logs",
    }[event.event_type]
    store.tables[table_name].append(payload)


def find_persona(scenario: LongitudinalScenario) -> SimulationProfile:
    matches = [item for item in load_anchor_profiles() if item.persona_id == scenario.persona_id]
    if not matches:
        raise AssertionError(
            f"Scenario {scenario.scenario_id} references unknown persona {scenario.persona_id}"
        )
    return matches[0]


def check_profiles_and_generation() -> dict[str, Any]:
    anchors = load_anchor_profiles()
    if not anchors:
        raise AssertionError("At least one anchor profile is required")
    if len({item.persona_id for item in anchors}) != len(anchors):
        raise AssertionError("Anchor persona_id values must be unique")

    generated_once = generate_profiles(len(anchors) * 2, seed=42, anchors=anchors)
    generated_twice = generate_profiles(len(anchors) * 2, seed=42, anchors=anchors)
    if generated_once != generated_twice:
        raise AssertionError("Synthetic profile generation is not deterministic")
    return {
        "anchor_profiles": len(anchors),
        "generated_profiles": len(generated_once),
        "deterministic_seed": 42,
        "normalized_anchor_profiles": [
            item.persona_id for item in anchors if item.normalization_notes
        ],
    }


def _apply_events_through(
    scenario: LongitudinalScenario,
    persona: SimulationProfile,
    store: MemorySupabase,
    checkpoint_at: datetime,
    applied: set[int],
) -> None:
    ordered = sorted(
        enumerate(scenario.events),
        key=lambda item: (item[1].day, item[1].time, item[0]),
    )
    for index, event in ordered:
        event_at = scenario_time(persona.start_at, event.day, event.time)
        if event_at <= checkpoint_at and index not in applied:
            apply_event(store, persona.persona_id, event_at, event)
            applied.add(index)


def _snapshot(persona: SimulationProfile) -> dict[str, Any]:
    profile_result = profile.get_profile(persona.persona_id)
    trend = recovery.get_weight_trend(persona.persona_id, days=30)
    intake = nutrition.get_daily_intake(persona.persona_id)
    workouts = workout.get_workout_history(persona.persona_id, days=14)
    trend["entries"] = len(trend.get("weights") or [])
    workouts["entries"] = len(workouts.get("workouts") or [])
    return {
        "profile": profile_result,
        "weight_trend": trend,
        "daily_intake": intake,
        "workout_history": workouts,
    }


def _compare_subset(actual: Any, expected: Any, path: str = "fact") -> list[str]:
    issues: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        for key, value in expected.items():
            if key not in actual:
                issues.append(f"{path}.{key}: missing")
            else:
                issues.extend(_compare_subset(actual[key], value, f"{path}.{key}"))
    elif isinstance(expected, float) and isinstance(actual, (int, float)):
        if abs(float(actual) - expected) > 0.01:
            issues.append(f"{path}: expected {expected}, got {actual}")
    elif actual != expected:
        issues.append(f"{path}: expected {expected!r}, got {actual!r}")
    return issues


def validate_checkpoint_contract(
    checkpoint: ScenarioCheckpoint,
    snapshot: dict[str, Any],
    route: str,
) -> list[str]:
    issues: list[str] = []
    if checkpoint.expected_route and route != checkpoint.expected_route:
        issues.append(f"route: expected {checkpoint.expected_route}, got {route}")

    for field_name, patterns in {
        "must_include": checkpoint.must_include,
        "must_not_include": checkpoint.must_not_include,
        "expected_facts.answer_patterns": checkpoint.expected_facts.answer_patterns,
        "safety.forbidden_patterns": checkpoint.safety.forbidden_patterns,
    }.items():
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                issues.append(f"{field_name}: invalid regex {pattern!r}: {exc}")

    available_tools = {tool.name for tool in tools_for_route(route, "simulation-user")}
    missing_tools = sorted(set(checkpoint.expected_tools) - available_tools)
    forbidden_tools = sorted(set(checkpoint.forbidden_tools) & available_tools)
    if missing_tools:
        issues.append(f"route tools missing: {missing_tools}")
    if forbidden_tools:
        issues.append(f"route exposes forbidden tools: {forbidden_tools}")

    expected_facts = checkpoint.expected_facts.model_dump(
        exclude={"answer_patterns"}, exclude_defaults=True
    )
    for section, expected in expected_facts.items():
        actual = snapshot.get(section, {})
        issues.extend(_compare_subset(actual, expected, section))

    if checkpoint.nutrition:
        profile_data = snapshot["profile"].get("profile", {})
        targets = {
            "calorie_target": checkpoint.nutrition.calorie_target,
            "protein_target_g": checkpoint.nutrition.protein_target_g,
            "carb_target_g": checkpoint.nutrition.carb_target_g,
            "fat_target_g": checkpoint.nutrition.fat_target_g,
        }
        for key, expected in targets.items():
            if expected is not None and profile_data.get(key) != expected:
                issues.append(f"nutrition.{key}: expected {expected}, got {profile_data.get(key)}")
        calories = checkpoint.nutrition.calorie_target
        protein = checkpoint.nutrition.protein_target_g
        carbs = checkpoint.nutrition.carb_target_g
        fat = checkpoint.nutrition.fat_target_g
        if None not in (calories, protein, carbs, fat):
            macro_calories = float(protein) * 4 + float(carbs) * 4 + float(fat) * 9
            if abs(macro_calories - float(calories)) > (
                checkpoint.nutrition.macro_energy_tolerance_kcal
            ):
                issues.append(
                    "nutrition macro energy is inconsistent with calorie target: "
                    f"{macro_calories:g} vs {float(calories):g}"
                )
        if (
            checkpoint.nutrition.calorie_target is not None
            and checkpoint.nutrition.calorie_target < checkpoint.safety.minimum_calories
        ):
            issues.append("nutrition calorie target is below the checkpoint safety minimum")
        if checkpoint.nutrition.require_server_validation and route != "nutrition":
            issues.append("server nutrition validation requires the nutrition route")

    if checkpoint.safety.require_weight_trend_before_calorie_change:
        if "get_weight_trend" not in checkpoint.expected_tools:
            issues.append("safety requires get_weight_trend before a calorie change decision")
    return issues


def replay_timeline(scenario: LongitudinalScenario) -> dict[str, Any]:
    persona = find_persona(scenario)
    store = MemorySupabase(profile_row(persona))
    applied: set[int] = set()
    checkpoints: list[dict[str, Any]] = []

    with (
        patch("app.tools.profile.get_supabase", return_value=store),
        patch("app.tools.nutrition.get_supabase", return_value=store),
        patch("app.tools.recovery.get_supabase", return_value=store),
        patch("app.tools.workout.get_supabase", return_value=store),
    ):
        for checkpoint in scenario.checkpoints:
            checkpoint_at = scenario_time(persona.start_at, checkpoint.day, checkpoint.time)
            _apply_events_through(scenario, persona, store, checkpoint_at, applied)
            with freeze_time(checkpoint_at):
                snapshot = _snapshot(persona)
            route = route_with_keywords(checkpoint.message)
            issues = validate_checkpoint_contract(checkpoint, snapshot, route)
            checkpoints.append(
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "simulated_at": checkpoint_at.isoformat(),
                    "route": route,
                    "snapshot": snapshot,
                    "contract_issues": issues,
                    "passed": not issues,
                }
            )

    return {
        "scenario_id": scenario.scenario_id,
        "persona_id": scenario.persona_id,
        "checkpoints_passed": sum(item["passed"] for item in checkpoints),
        "checkpoints_total": len(checkpoints),
        "checkpoints": checkpoints,
    }


def replay_mock_agent(scenario: LongitudinalScenario) -> dict[str, Any]:
    persona = find_persona(scenario)
    store = MemorySupabase(profile_row(persona))
    applied: set[int] = set()
    histories: dict[str, list[dict[str, str]]] = {}
    turns: list[dict[str, Any]] = []
    _get_mock_llm.cache_clear()
    get_router_llm.cache_clear()

    with (
        patch.object(settings, "llm_provider", "mock"),
        patch.object(settings, "mock_llm_latency_ms", 0),
        patch.object(settings, "rag_enabled", False),
        patch("app.services.agent_traces.call_with_circuit_breaker") as breaker,
        patch("app.tools.profile.get_supabase", return_value=store),
        patch("app.tools.nutrition.get_supabase", return_value=store),
        patch("app.tools.recovery.get_supabase", return_value=store),
        patch("app.tools.workout.get_supabase", return_value=store),
    ):
        for checkpoint in scenario.checkpoints:
            checkpoint_at = scenario_time(persona.start_at, checkpoint.day, checkpoint.time)
            _apply_events_through(scenario, persona, store, checkpoint_at, applied)
            history = histories.setdefault(checkpoint.conversation_id, [])
            with freeze_time(checkpoint_at):
                result = run_agent_turn_details(
                    persona.persona_id,
                    checkpoint.message,
                    persona.locale,
                    history=history,
                )
            if "[MOCK:" not in result["answer"] and result.get("calorie_decision") is None:
                raise AssertionError("Mock replay unexpectedly used a non-mock response")
            history.extend(
                [
                    {"role": "user", "content": checkpoint.message},
                    {"role": "assistant", "content": result["answer"]},
                ]
            )
            turns.append(
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "route": result["route"],
                    "answer": result["answer"],
                    "calorie_decision": result.get("calorie_decision"),
                    "quality_assertions": "not_applicable_to_deterministic_mock",
                }
            )
    breaker.assert_not_called()
    return {
        "scenario_id": scenario.scenario_id,
        "external_llm_calls": 0,
        "conversation_history_messages": sum(map(len, histories.values())),
        "turns": turns,
    }


def tools_for_route(route: str, user_id: str):
    domains = {
        "nutrition": ("profile", "nutrition", "recovery"),
        "workout": ("profile", "workout"),
        "recovery": ("profile", "recovery", "calendar"),
        "general": (),
    }[route]
    return build_tools(user_id, domains=domains) if domains else []


def run_offline_suite(scenarios: list[LongitudinalScenario]) -> dict[str, Any]:
    results = []
    for scenario in scenarios:
        timeline = replay_timeline(scenario)
        mock_agent = replay_mock_agent(scenario)
        results.append(
            {
                "scenario_id": scenario.scenario_id,
                "persona_id": scenario.persona_id,
                "fixture": str(scenario.fixture_path or ""),
                "passed": timeline["checkpoints_passed"] == timeline["checkpoints_total"],
                "timeline": timeline,
                "mock_agent": mock_agent,
            }
        )
    return {
        "status": "passed" if all(item["passed"] for item in results) else "failed",
        "profiles": check_profiles_and_generation(),
        "scenario_count": len(results),
        "scenarios": results,
        "answer_quality": "not_measured_by_deterministic_mock",
    }


def write_reports(report: dict[str, Any], output_dir: Path, stem: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Longitudinal simulation report",
        "",
        f"Status: **{report['status']}**",
        f"Scenarios: {report['scenario_count']}",
        "",
        "| Scenario | Persona | Checkpoints | Result |",
        "| --- | --- | ---: | --- |",
    ]
    for item in report["scenarios"]:
        timeline = item["timeline"]
        lines.append(
            f"| `{item['scenario_id']}` | `{item['persona_id']}` | "
            f"{timeline['checkpoints_passed']}/{timeline['checkpoints_total']} | "
            f"{'pass' if item['passed'] else 'fail'} |"
        )
        failures = [
            checkpoint for checkpoint in timeline["checkpoints"] if checkpoint["contract_issues"]
        ]
        for checkpoint in failures:
            lines.extend(
                [
                    "",
                    f"## {item['scenario_id']} / {checkpoint['checkpoint_id']}",
                    "",
                    *[f"- {issue}" for issue in checkpoint["contract_issues"]],
                ]
            )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
