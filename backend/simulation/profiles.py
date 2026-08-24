"""Validated profile anchors and deterministic synthetic-profile generation."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FIXTURES_DIR = Path(__file__).with_name("fixtures")
ANCHORS_PATH = FIXTURES_DIR / "profiles.json"


class SimulationProfile(BaseModel):
    """Canonical profile accepted by the longitudinal test contour."""

    persona_id: str
    source_persona_id: str
    source_row: int = Field(ge=2)
    start_at: str
    timezone: str = "Europe/Moscow"
    locale: str = "ru"
    age: int = Field(ge=18, le=90)
    sex: Literal["male", "female", "other"]
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=300)
    goal: Literal["lose_weight", "maintain", "gain_muscle", "recomp"]
    calorie_target: int = Field(ge=1_200, le=6_000)
    protein_target_g: int = Field(ge=40, le=350)
    carb_target_g: int = Field(ge=30, le=800)
    fat_target_g: int = Field(ge=20, le=250)
    allergies: list[str] = Field(default_factory=list)
    dietary_pattern: Literal["omnivore", "vegetarian", "vegan", "pescatarian"] = "omnivore"
    dietary_restrictions: list[Literal["halal", "kosher", "lactose_free", "gluten_free"]] = Field(
        default_factory=list
    )
    favorite_foods: list[str] = Field(default_factory=list)
    budget: Literal["low", "medium", "high"]
    cooking_skill: Literal["none", "basic", "intermediate", "advanced"]
    normalization_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_energy_budget(self) -> "SimulationProfile":
        macro_calories = self.protein_target_g * 4 + self.carb_target_g * 4 + self.fat_target_g * 9
        if abs(macro_calories - self.calorie_target) > 80:
            raise ValueError("macro targets must stay within 80 kcal of calorie_target")
        return self


def load_anchor_profiles(path: Path = ANCHORS_PATH) -> list[SimulationProfile]:
    """Load normalized workbook rows without mutating the source workbook."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SimulationProfile.model_validate(row) for row in payload["profiles"]]


def generate_profiles(
    count: int,
    *,
    seed: int = 20260823,
    anchors: list[SimulationProfile] | None = None,
) -> list[SimulationProfile]:
    """Generate reproducible variants around the workbook anchor profiles.

    The generator deliberately makes small perturbations. It is meant to widen
    test coverage, not to create medically representative population data.
    """
    if count < 1:
        raise ValueError("count must be positive")

    source_profiles = anchors or load_anchor_profiles()
    if not source_profiles:
        raise ValueError("at least one anchor profile is required")

    rng = random.Random(seed)
    generated: list[SimulationProfile] = []
    for index in range(count):
        anchor = source_profiles[index % len(source_profiles)]
        weight = round(anchor.weight_kg * rng.uniform(0.94, 1.06), 1)
        calories = max(1_200, round(anchor.calorie_target * rng.uniform(0.95, 1.05)))
        protein = max(40, round(anchor.protein_target_g * rng.uniform(0.96, 1.04)))
        fat, carbs = _derive_missing_macros(calories, protein, weight)
        generated.append(
            anchor.model_copy(
                update={
                    "persona_id": f"sim_{seed}_{index + 1:04d}",
                    "age": max(18, min(90, anchor.age + rng.randint(-3, 3))),
                    "height_cm": round(anchor.height_cm + rng.uniform(-3.0, 3.0), 1),
                    "weight_kg": weight,
                    "calorie_target": calories,
                    "protein_target_g": protein,
                    "fat_target_g": fat,
                    "carb_target_g": carbs,
                    "normalization_notes": [
                        *anchor.normalization_notes,
                        f"deterministic variant generated with seed {seed}",
                    ],
                }
            )
        )
    return generated


def _derive_missing_macros(
    calorie_target: int,
    protein_target_g: int,
    weight_kg: float,
) -> tuple[int, int]:
    """Derive required fat/carb fields absent from the source workbook."""
    fat_target_g = max(round(weight_kg * 0.7), round(calorie_target * 0.25 / 9))
    remaining = calorie_target - protein_target_g * 4 - fat_target_g * 9
    carb_target_g = max(30, round(remaining / 4))
    return fat_target_g, carb_target_g
