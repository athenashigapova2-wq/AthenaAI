"""Retrieval-backed meal estimation application service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai_execution import ai_execution_service
from app.agents.nutrition_validation import display_name_from_matched_food
from app.services.supabase import get_supabase


Locale = Literal["ru", "en", "fr", "es", "zh"]


class ParsedMealDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    english_term: str = Field(min_length=2, max_length=120)
    quantity_g: float = Field(gt=0, le=5_000)


class CandidateChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    food_name: str = Field(min_length=1, max_length=240)


class FoodCandidate(BaseModel):
    food_name: str
    calories_per_100g: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)


class MealEstimate(BaseModel):
    matched: Literal[True] = True
    name: str
    matched_food: str
    quantity_g: float
    calories: int = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)


StructuredInvoker = Callable[..., BaseModel]


class MealEstimationService:
    """Parse, retrieve, rerank and deterministically calculate one meal."""

    def __init__(
        self,
        *,
        structured_invoker: StructuredInvoker = ai_execution_service.invoke_structured,
    ) -> None:
        self._invoke_structured = structured_invoker

    def parse_description(
        self,
        description: str,
        locale: Locale,
    ) -> ParsedMealDescription:
        return ParsedMealDescription.model_validate(
            self._invoke_structured(
                response_model=ParsedMealDescription,
                node_name="meal_estimation",
                purpose="parse_description",
                system_prompt=(
                    "Extract a short core English food name suitable for a nutrition "
                    "database search and its quantity in grams. Ignore brands and "
                    "decorative adjectives. If quantity is absent, choose one realistic "
                    "household portion."
                ),
                input_payload={"description": description, "locale": locale},
            )
        )

    def retrieve_candidates(
        self,
        parsed: ParsedMealDescription,
        *,
        limit: int = 15,
    ) -> list[FoodCandidate]:
        response = get_supabase().rpc(
            "search_food_nutrients",
            {"search_term": parsed.english_term, "match_limit": limit},
        ).execute()
        return [FoodCandidate.model_validate(row) for row in (response.data or [])]

    def rerank_candidates(
        self,
        *,
        description: str,
        candidates: list[FoodCandidate],
        locale: Locale,
    ) -> FoodCandidate | None:
        if not candidates:
            return None
        choice = CandidateChoice.model_validate(
            self._invoke_structured(
                response_model=CandidateChoice,
                node_name="meal_estimation",
                purpose="rerank_candidates",
                system_prompt=(
                    "Choose the single genuinely best database candidate for the user "
                    "description. Return its exact food_name, or NONE when none match."
                ),
                input_payload={
                    "description": description,
                    "locale": locale,
                    "candidates": [candidate.food_name for candidate in candidates],
                },
            )
        )
        if choice.food_name == "NONE":
            return None
        return next(
            (candidate for candidate in candidates if candidate.food_name == choice.food_name),
            None,
        )

    @staticmethod
    def calculate_macros(
        matched_food: FoodCandidate,
        *,
        quantity_g: float,
        locale: Locale,
    ) -> MealEstimate:
        factor = quantity_g / 100.0
        return MealEstimate(
            name=display_name_from_matched_food(matched_food.food_name, locale),
            matched_food=matched_food.food_name,
            quantity_g=round(quantity_g, 1),
            calories=round(matched_food.calories_per_100g * factor),
            protein_g=round(matched_food.protein_g * factor, 1),
            carbs_g=round(matched_food.carbs_g * factor, 1),
            fat_g=round(matched_food.fat_g * factor, 1),
        )

    def estimate(self, description: str, locale: Locale) -> MealEstimate | None:
        parsed = self.parse_description(description, locale)
        candidates = self.retrieve_candidates(parsed)
        matched = self.rerank_candidates(
            description=description,
            candidates=candidates,
            locale=locale,
        )
        if matched is None:
            return None
        return self.calculate_macros(matched, quantity_g=parsed.quantity_g, locale=locale)
