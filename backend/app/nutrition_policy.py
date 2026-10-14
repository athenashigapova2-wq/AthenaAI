"""Shared deterministic policy for calories and macronutrients.

Every nutrition path may add narrower context-specific limits, but all paths
share these invariants: values are finite, non-negative numbers and macro
energy is calculated with the same 4/4/9 formula.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Annotated, Any

from pydantic import Field

PROTEIN_KCAL_PER_GRAM = 4.0
CARBS_KCAL_PER_GRAM = 4.0
FAT_KCAL_PER_GRAM = 9.0

NonNegativeFiniteFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
NonNegativeFiniteInt = Annotated[int, Field(ge=0)]


class NutritionPolicyError(ValueError):
    """Raised when nutrition values violate a universal invariant."""


def validate_non_negative(name: str, value: Any) -> float:
    """Normalize one scalar and enforce the universal nutrition invariant."""
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise NutritionPolicyError(f"{name} must be a number") from exc
    if not isfinite(normalized):
        raise NutritionPolicyError(f"{name} must be finite")
    if normalized < 0:
        raise NutritionPolicyError(f"{name} must be non-negative")
    return normalized


def calculate_macro_calories(
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> float:
    """Calculate macro-derived energy after applying universal validation."""
    protein = validate_non_negative("protein_g", protein_g)
    carbs = validate_non_negative("carbs_g", carbs_g)
    fat = validate_non_negative("fat_g", fat_g)
    return (
        protein * PROTEIN_KCAL_PER_GRAM
        + carbs * CARBS_KCAL_PER_GRAM
        + fat * FAT_KCAL_PER_GRAM
    )


@dataclass(frozen=True)
class NutritionValues:
    """Canonical validated calorie and macronutrient value object."""

    # Field order preserves the existing NutritionNumbers positional contract.
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float

    def __post_init__(self) -> None:
        for name in ("calories", "protein_g", "fat_g", "carbs_g"):
            object.__setattr__(self, name, validate_non_negative(name, getattr(self, name)))

    @property
    def macro_calories(self) -> float:
        return calculate_macro_calories(self.protein_g, self.carbs_g, self.fat_g)


def validate_nutrition_values(
    *,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> NutritionValues:
    """Validate values from any API, tool, database or calculation boundary."""
    return NutritionValues(
        calories=calories,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_g,
    )
