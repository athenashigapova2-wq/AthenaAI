"""Deterministic, server-owned assignment for evaluation experiments."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import BACKEND_DIR, settings


class ExperimentVariant(BaseModel):
    """One immutable behavior and pricing snapshot inside an experiment."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    weight: int = Field(gt=0, le=10_000)
    model_tier: Literal["small", "main"] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    input_cost_per_million_usd: float | None = Field(default=None, ge=0.0)
    output_cost_per_million_usd: float | None = Field(default=None, ge=0.0)


class ExperimentDefinition(BaseModel):
    """Version-controlled definition used for deterministic assignment."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    salt: str = Field(min_length=16, max_length=200)
    enabled: bool = False
    allocation_percent: float = Field(default=100.0, gt=0.0, le=100.0)
    assignment_unit: Literal["user"] = "user"
    variants: list[ExperimentVariant] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def unique_variants(self) -> "ExperimentDefinition":
        ids = [variant.variant_id for variant in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("experiment variant_id values must be unique")
        return self

    def config_hash(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExperimentRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    experiments: list[ExperimentDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_experiments(self) -> "ExperimentRegistry":
        ids = [experiment.experiment_id for experiment in self.experiments]
        if len(ids) != len(set(ids)):
            raise ValueError("experiment_id values must be unique")
        return self


class ExperimentAssignment(BaseModel):
    """Auditable assignment propagated with one trace."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    variant_id: str
    assignment_bucket: int = Field(ge=0, lt=10_000)
    config_hash: str = Field(min_length=64, max_length=64)
    model_tier: Literal["small", "main"] | None = None
    temperature: float | None = None
    input_cost_per_million_usd: float | None = None
    output_cost_per_million_usd: float | None = None

    def estimated_cost_usd(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.input_cost_per_million_usd is None or self.output_cost_per_million_usd is None:
            return None
        cost = (
            input_tokens * self.input_cost_per_million_usd
            + output_tokens * self.output_cost_per_million_usd
        ) / 1_000_000
        return round(cost, 9)


_current_assignment: ContextVar[ExperimentAssignment | None] = ContextVar(
    "evaluation_experiment_assignment",
    default=None,
)


def _bucket(*parts: str) -> int:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 10_000


def assign_experiment(
    definition: ExperimentDefinition,
    actor_id: str,
) -> ExperimentAssignment | None:
    """Assign one actor reproducibly, independent of request order or process."""
    enrollment_bucket = _bucket(
        definition.salt,
        definition.experiment_id,
        actor_id,
        "enrollment",
    )
    if enrollment_bucket >= round(definition.allocation_percent * 100):
        return None

    variant_bucket = _bucket(
        definition.salt,
        definition.experiment_id,
        actor_id,
        "variant",
    )
    total_weight = sum(variant.weight for variant in definition.variants)
    point = variant_bucket % total_weight
    cumulative = 0
    selected = definition.variants[-1]
    for variant in definition.variants:
        cumulative += variant.weight
        if point < cumulative:
            selected = variant
            break
    return ExperimentAssignment(
        experiment_id=definition.experiment_id,
        variant_id=selected.variant_id,
        assignment_bucket=variant_bucket,
        config_hash=definition.config_hash(),
        model_tier=selected.model_tier,
        temperature=selected.temperature,
        input_cost_per_million_usd=selected.input_cost_per_million_usd,
        output_cost_per_million_usd=selected.output_cost_per_million_usd,
    )


def _config_path() -> Path | None:
    configured = settings.evaluation_experiment_config_file.strip()
    if not configured:
        return None
    path = Path(configured)
    return path if path.is_absolute() else BACKEND_DIR / path


@lru_cache(maxsize=1)
def load_registry() -> ExperimentRegistry:
    path = _config_path()
    if path is None:
        return ExperimentRegistry()
    return ExperimentRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def active_definition() -> ExperimentDefinition | None:
    active_id = settings.evaluation_experiment_id.strip()
    if not active_id:
        return None
    for definition in load_registry().experiments:
        if definition.experiment_id == active_id and definition.enabled:
            return definition
    return None


def assign_active_experiment(actor_id: str) -> ExperimentAssignment | None:
    definition = active_definition()
    return assign_experiment(definition, actor_id) if definition is not None else None


def resolve_assignment(
    *,
    actor_id: str,
    experiment_id: str | None,
    variant_id: str | None,
) -> ExperimentAssignment | None:
    """Reconstruct and verify the API assignment inside the Celery worker."""
    if experiment_id is None and variant_id is None:
        return None
    definition = active_definition()
    if definition is None or definition.experiment_id != experiment_id:
        raise RuntimeError("Queued evaluation experiment is no longer active")
    assignment = assign_experiment(definition, actor_id)
    if assignment is None or assignment.variant_id != variant_id:
        raise RuntimeError("Queued evaluation experiment assignment is inconsistent")
    return assignment


@contextmanager
def experiment_context(assignment: ExperimentAssignment | None) -> Iterator[None]:
    token = _current_assignment.set(assignment)
    try:
        yield
    finally:
        _current_assignment.reset(token)


def current_experiment() -> ExperimentAssignment | None:
    return _current_assignment.get()
