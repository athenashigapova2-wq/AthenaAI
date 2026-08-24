"""Independent hard, semantic, and human-gold evaluation layers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from pydantic import BaseModel, Field, model_validator

from simulation.longitudinal import _compare_subset
from simulation.scenarios import ScenarioCheckpoint

SEMANTIC_JUDGE_ENV = "ATHENA_RUN_SEMANTIC_JUDGE"
DEFAULT_GOLD_PATH = Path(__file__).resolve().parent / "gold" / "human_reviewed.json"


class ToolCallRecord(BaseModel):
    step: int = Field(ge=1)
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    read_only: bool
    error: str | None = None


class SemanticCriterion(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str = Field(min_length=1, max_length=1_000)


class SemanticQualityJudgment(BaseModel):
    factual_consistency: SemanticCriterion
    personalization: SemanticCriterion
    longitudinal_reasoning: SemanticCriterion
    usefulness: SemanticCriterion

    @property
    def mean_score(self) -> float:
        values = [
            self.factual_consistency.score,
            self.personalization.score,
            self.longitudinal_reasoning.score,
            self.usefulness.score,
        ]
        return round(sum(values) / len(values), 2)

    @property
    def passed(self) -> bool:
        values = [
            self.factual_consistency.score,
            self.personalization.score,
            self.longitudinal_reasoning.score,
            self.usefulness.score,
        ]
        return min(values) >= 3 and self.mean_score >= 4.0


class HumanGoldReview(BaseModel):
    scenario_id: str
    checkpoint_id: str
    status: Literal["approved"]
    reviewer: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=1)
    expected_scores: dict[
        Literal[
            "factual_consistency",
            "personalization",
            "longitudinal_reasoning",
            "usefulness",
        ],
        int,
    ]
    tolerance: int = Field(default=1, ge=0, le=2)
    notes: str = ""

    @model_validator(mode="after")
    def require_all_dimensions(self) -> "HumanGoldReview":
        required = {
            "factual_consistency",
            "personalization",
            "longitudinal_reasoning",
            "usefulness",
        }
        if set(self.expected_scores) != required:
            raise ValueError("expected_scores must contain all four semantic dimensions")
        if any(score < 1 or score > 5 for score in self.expected_scores.values()):
            raise ValueError("human gold scores must be between 1 and 5")
        return self


GoldCategory = Literal[
    "nutrition_plan",
    "progress_calories",
    "allergies_constraints",
    "workout_recovery",
    "longitudinal_reasoning",
    "uncertainty_safety",
]


class GoldPersona(BaseModel):
    persona_id: str
    age: int = Field(ge=18, le=100)
    sex: Literal["female", "male"]
    goal: str
    activity_level: Literal["low", "moderate", "high"]


class GoldExpectedBehavior(BaseModel):
    route: Literal["nutrition", "workout", "recovery", "general"]
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    must_use_facts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_outcome: str

    @model_validator(mode="after")
    def require_consistent_lists(self) -> "GoldExpectedBehavior":
        for name in (
            "required_tools",
            "forbidden_tools",
            "must_use_facts",
            "forbidden_claims",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} values must be unique")
        overlap = set(self.required_tools) & set(self.forbidden_tools)
        if overlap:
            raise ValueError(f"tools cannot be both required and forbidden: {overlap}")
        return self


class GoldScoreThresholds(BaseModel):
    factual_consistency: int = Field(default=4, ge=1, le=5)
    personalization: int = Field(default=3, ge=1, le=5)
    longitudinal_reasoning: int = Field(default=3, ge=1, le=5)
    usefulness: int = Field(default=3, ge=1, le=5)


class GoldCheckpointCase(BaseModel):
    scenario_id: str
    checkpoint_id: str
    status: Literal["candidate"] = "candidate"
    category: GoldCategory
    language: Literal["ru", "en"]
    persona: GoldPersona
    prompt: str = Field(min_length=1)
    verified_context: dict[str, Any]
    expected: GoldExpectedBehavior
    risk_tags: list[str] = Field(default_factory=list)
    data_quality: Literal["complete", "incomplete", "contradictory"] = "complete"
    rubric_focus: str = Field(min_length=1)
    minimum_scores: GoldScoreThresholds = Field(default_factory=GoldScoreThresholds)
    reference_answer: str = Field(min_length=1)


class HumanGoldFile(BaseModel):
    schema_version: Literal[2] = 2
    rubric: dict[str, str] = Field(default_factory=dict)
    cases: list[GoldCheckpointCase] = Field(default_factory=list)
    reviews: list[HumanGoldReview] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_consistent_entries(self) -> "HumanGoldFile":
        keys = [(item.scenario_id, item.checkpoint_id) for item in self.cases]
        if len(keys) != len(set(keys)):
            raise ValueError("gold checkpoint keys must be unique")
        review_keys = [(item.scenario_id, item.checkpoint_id) for item in self.reviews]
        if len(review_keys) != len(set(review_keys)):
            raise ValueError("human gold review keys must be unique")
        unknown_reviews = sorted(set(review_keys) - set(keys))
        if unknown_reviews:
            raise ValueError(
                f"human gold reviews must reference existing cases: {unknown_reviews}"
            )
        return self


def find_gold_case(
    gold: HumanGoldFile, *, scenario_id: str, checkpoint_id: str
) -> GoldCheckpointCase | None:
    return next(
        (
            item
            for item in gold.cases
            if item.scenario_id == scenario_id and item.checkpoint_id == checkpoint_id
        ),
        None,
    )


def _normalized_prompt(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return re.sub(r"[.!?…]+$", "", normalized).strip()


def gold_fixture_coverage(
    gold: HumanGoldFile, scenarios: Sequence[Any]
) -> dict[str, Any]:
    """Describe which curated cases are executable by the longitudinal runner."""
    checkpoints = {
        (scenario.scenario_id, checkpoint.checkpoint_id): checkpoint
        for scenario in scenarios
        for checkpoint in scenario.checkpoints
    }
    matched: list[str] = []
    standalone: list[str] = []
    prompt_mismatches: list[dict[str, str]] = []
    for case in gold.cases:
        key = (case.scenario_id, case.checkpoint_id)
        label = f"{key[0]}:{key[1]}"
        checkpoint = checkpoints.get(key)
        if checkpoint is None:
            standalone.append(label)
            continue
        matched.append(label)
        if _normalized_prompt(checkpoint.message) != _normalized_prompt(case.prompt):
            prompt_mismatches.append(
                {
                    "case": label,
                    "fixture_prompt": checkpoint.message,
                    "gold_prompt": case.prompt,
                }
            )
    return {
        "total": len(gold.cases),
        "fixture_matched": len(matched),
        "standalone_not_executed": len(standalone),
        "matched_cases": matched,
        "standalone_cases": standalone,
        "prompt_mismatches": prompt_mismatches,
    }


def _last_successful_result(
    records: list[ToolCallRecord], name: str
) -> dict[str, Any] | None:
    for record in reversed(records):
        if record.name == name and record.error is None and isinstance(record.result, dict):
            return record.result
    return None


def evaluate_hard_invariants(
    checkpoint: ScenarioCheckpoint,
    *,
    route: str,
    tool_records: list[ToolCallRecord],
    db_snapshot: dict[str, Any],
    db_writes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate only machine-verifiable facts; no answer-text heuristics."""
    called = [record.name for record in tool_records]
    called_set = set(called)
    expected_facts = checkpoint.expected_facts.model_dump(exclude={"answer_patterns"})
    fact_issues = _compare_subset(db_snapshot, expected_facts)
    unexpected_write_tools = sorted(
        {
            record.name
            for record in tool_records
            if not record.read_only
            and record.name not in checkpoint.hard_invariants.allowed_write_tools
        }
    )
    failed_tool_results = [
        record.name
        for record in tool_records
        if record.error
        or (
            isinstance(record.result, dict)
            and record.result.get("status") in {"error", "rejected"}
        )
    ]
    checks: dict[str, bool] = {
        "expected_route": (
            checkpoint.expected_route is None or route == checkpoint.expected_route
        ),
        "expected_tools_called": set(checkpoint.expected_tools).issubset(called_set),
        "forbidden_tools_not_called": not (
            set(checkpoint.forbidden_tools) & called_set
        ),
        "actual_db_values": not fact_issues,
        "tool_permissions": not unexpected_write_tools,
        "db_writes": len(db_writes) <= checkpoint.hard_invariants.max_db_writes,
        "tool_calls_succeeded": not failed_tool_results,
    }
    nutrition_result = _last_successful_result(
        tool_records, "submit_daily_nutrition_plan"
    )
    calorie_result = _last_successful_result(tool_records, "submit_calorie_decision")
    metrics: dict[str, Any] = {
        "db_write_count": len(db_writes),
        "tool_call_count": len(tool_records),
    }
    if checkpoint.nutrition:
        checks["server_nutrition_validation_called"] = (
            not checkpoint.nutrition.require_server_validation
            or nutrition_result is not None
        )
        totals = (
            nutrition_result.get("validated_totals", {}) if nutrition_result else {}
        )
        metrics["validated_totals"] = totals
        targets = {
            "calories": checkpoint.nutrition.calorie_target,
            "protein_g": checkpoint.nutrition.protein_target_g,
            "carbs_g": checkpoint.nutrition.carb_target_g,
            "fat_g": checkpoint.nutrition.fat_target_g,
        }
        for nutrient, target in targets.items():
            if target is not None:
                actual = totals.get(nutrient)
                tolerance = checkpoint.nutrition.target_tolerance_ratio
                checks[f"validated_{nutrient}_near_target"] = (
                    isinstance(actual, (int, float))
                    and target * (1 - tolerance)
                    <= float(actual)
                    <= target * (1 + tolerance)
                )
        if all(
            isinstance(totals.get(name), (int, float))
            for name in ("calories", "protein_g", "fat_g", "carbs_g")
        ):
            macro_energy = (
                float(totals["protein_g"]) * 4
                + float(totals["fat_g"]) * 9
                + float(totals["carbs_g"]) * 4
            )
            metrics["macro_derived_calories"] = round(macro_energy, 2)
            checks["macro_calorie_consistency"] = (
                abs(float(totals["calories"]) - macro_energy)
                <= checkpoint.nutrition.macro_energy_tolerance_kcal
            )
        else:
            checks["macro_calorie_consistency"] = False
        if nutrition_result:
            violations = nutrition_result.get("allergen_check", {}).get(
                "violations", ["missing allergen evidence"]
            )
            checks["allergens"] = not violations
            calories = totals.get("calories")
            checks["minimum_calories"] = (
                isinstance(calories, (int, float))
                and float(calories) >= checkpoint.safety.minimum_calories
            )
    if checkpoint.safety.require_weight_trend_before_calorie_change:
        trend_positions = [
            index
            for index, record in enumerate(tool_records)
            if record.name == "get_weight_trend"
        ]
        decision_positions = [
            index
            for index, record in enumerate(tool_records)
            if record.name == "submit_calorie_decision"
        ]
        checks["structured_calorie_decision"] = calorie_result is not None
        checks["weight_trend_before_calorie_decision"] = (
            bool(trend_positions)
            and bool(decision_positions)
            and min(trend_positions) < min(decision_positions)
        )
        decision = (
            calorie_result.get("calorie_decision", {}) if calorie_result else {}
        )
        proposed = decision.get("proposed_calories")
        minimum = decision.get("minimum_calories")
        checks["calorie_decision_minimum"] = (
            isinstance(proposed, (int, float))
            and isinstance(minimum, (int, float))
            and float(proposed) >= float(minimum)
            and float(proposed) >= checkpoint.safety.minimum_calories
        )
        action = decision.get("action")
        records = decision.get("weight_records")
        checks["calorie_change_has_weight_evidence"] = (
            action == "keep" or isinstance(records, int) and records >= 2
        )
        metrics["calorie_decision"] = decision
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "evidence": {
            "called_tools": called,
            "unexpected_write_tools": unexpected_write_tools,
            "failed_tool_results": failed_tool_results,
            "db_fact_issues": fact_issues,
            "db_writes": db_writes,
        },
        "metrics": metrics,
    }


def semantic_judge_payload(
    checkpoint: ScenarioCheckpoint,
    *,
    answer: str,
    db_snapshot: dict[str, Any],
    history: list[dict[str, str]],
    gold_case: GoldCheckpointCase | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "question": checkpoint.message,
        "answer": answer,
        "conversation_history": history,
        "verified_context": db_snapshot,
        "checkpoint_rubric": checkpoint.rubric,
        "dimensions": {
            "factual_consistency": "Does the answer agree with verified context?",
            "personalization": "Does it use relevant profile/preferences/constraints?",
            "longitudinal_reasoning": "Does it reason across time and observed changes?",
            "usefulness": "Is it clear, actionable, and appropriately scoped?",
        },
        "scoring": "Score each dimension 1-5. Return JSON only.",
    }
    if gold_case is not None:
        payload["gold_candidate"] = {
            "category": gold_case.category,
            "language": gold_case.language,
            "persona": gold_case.persona.model_dump(),
            "curated_verified_context": gold_case.verified_context,
            "expected_behavior": gold_case.expected.model_dump(),
            "risk_tags": gold_case.risk_tags,
            "data_quality": gold_case.data_quality,
            "rubric_focus": gold_case.rubric_focus,
            "minimum_scores": gold_case.minimum_scores.model_dump(),
        }
    return payload


def parse_semantic_judgment(raw: str) -> SemanticQualityJudgment:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    return SemanticQualityJudgment.model_validate(json.loads(cleaned))


def evaluate_semantic_quality(
    payload: dict[str, Any],
    judge: Callable[[dict[str, Any]], str],
    *,
    minimum_scores: GoldScoreThresholds | None = None,
) -> dict[str, Any]:
    try:
        judgment = parse_semantic_judgment(judge(payload))
    except Exception as exc:
        return {"status": "error", "passed": False, "error": f"{type(exc).__name__}: {exc}"}
    scores = judgment.model_dump()
    if minimum_scores is None:
        passed = judgment.passed
        thresholds = None
    else:
        thresholds = minimum_scores.model_dump()
        passed = all(
            scores[name]["score"] >= minimum
            for name, minimum in thresholds.items()
        )
    return {
        "status": "completed",
        "passed": passed,
        "mean_score": judgment.mean_score,
        "scores": scores,
        "minimum_scores": thresholds,
    }


def evaluate_gold_candidate(
    case: GoldCheckpointCase | None, semantic: dict[str, Any]
) -> dict[str, Any]:
    if case is None:
        return {"status": "not_in_candidate_subset"}
    base = {
        "scenario_id": case.scenario_id,
        "checkpoint_id": case.checkpoint_id,
        "category": case.category,
        "risk_tags": case.risk_tags,
    }
    if semantic.get("status") != "completed":
        return {**base, "status": "matched_not_judged", "passed": None}
    scores = {
        name: semantic["scores"][name]["score"]
        for name in case.minimum_scores.model_dump()
    }
    minimum = case.minimum_scores.model_dump()
    return {
        **base,
        "status": "candidate_scored",
        "passed": all(
            scores[name] >= threshold for name, threshold in minimum.items()
        ),
        "actual_scores": scores,
        "minimum_scores": minimum,
    }


def load_human_gold(path: Path = DEFAULT_GOLD_PATH) -> HumanGoldFile:
    return HumanGoldFile.model_validate_json(path.read_text(encoding="utf-8"))


def compare_human_gold(
    gold: HumanGoldFile,
    *,
    scenario_id: str,
    checkpoint_id: str,
    semantic: dict[str, Any],
) -> dict[str, Any]:
    case = find_gold_case(
        gold, scenario_id=scenario_id, checkpoint_id=checkpoint_id
    )
    review = next(
        (
            item
            for item in gold.reviews
            if item.scenario_id == scenario_id and item.checkpoint_id == checkpoint_id
        ),
        None,
    )
    if review is None:
        return {
            "status": "awaiting_human_review" if case is not None else "not_in_gold_subset"
        }
    if semantic.get("status") != "completed":
        return {"status": "semantic_not_available", "passed": False}
    actual = {
        name: semantic["scores"][name]["score"] for name in review.expected_scores
    }
    deltas = {
        name: actual[name] - expected
        for name, expected in review.expected_scores.items()
    }
    return {
        "status": "compared",
        "passed": all(abs(delta) <= review.tolerance for delta in deltas.values()),
        "reviewer": review.reviewer,
        "reviewed_at": review.reviewed_at,
        "expected_scores": review.expected_scores,
        "actual_scores": actual,
        "deltas": deltas,
        "tolerance": review.tolerance,
    }
