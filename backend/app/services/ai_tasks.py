"""Server-owned narrow AI tasks exposed through authenticated FastAPI."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai_execution import ai_execution_service
from app.services import agent_traces


Locale = Literal["ru", "en", "fr", "es", "zh"]
Goal = Literal["lose_weight", "maintain", "gain_muscle", "recomp"]
DietaryPattern = Literal["omnivore", "vegetarian", "vegan", "pescatarian"]
DietaryRestriction = Literal["halal", "kosher", "lactose_free", "gluten_free"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MacroBlock(StrictModel):
    calories: float = Field(ge=0, le=10_000)
    protein: float = Field(ge=0, le=1_000)
    carbs: float = Field(ge=0, le=1_500)
    fat: float = Field(ge=0, le=500)


class DietaryContext(StrictModel):
    dietary_pattern: DietaryPattern = "omnivore"
    dietary_restrictions: list[DietaryRestriction] = Field(default_factory=list, max_length=20)
    allergies: list[str] = Field(default_factory=list, max_length=20)
    disliked_foods: list[str] = Field(default_factory=list, max_length=20)


class DailyTipInput(DietaryContext):
    remaining: MacroBlock
    goal: Goal
    language: Locale = "en"


class TextResult(StrictModel):
    text: str = Field(min_length=1, max_length=1_200)


class MealRecommendationsInput(DietaryContext):
    remaining: MacroBlock
    goal: Goal
    budget: Literal["low", "medium", "high"] = "medium"
    cooking_skill: Literal["none", "basic", "intermediate", "advanced"] = "basic"
    favorite_foods: list[str] = Field(default_factory=list, max_length=20)
    meals_eaten: list[str] = Field(default_factory=list, max_length=20)
    language: Locale = "en"


class MealRecommendation(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    calories: float = Field(ge=0, le=5_000)
    protein_g: float = Field(ge=0, le=500)
    carbs_g: float = Field(ge=0, le=800)
    fat_g: float = Field(ge=0, le=300)
    prep_time: str = Field(min_length=1, max_length=80)
    estimated_price_rub: float = Field(ge=0, le=100_000)
    ingredients: list[str] = Field(min_length=1, max_length=40)


class MealRecommendationsResult(StrictModel):
    meals: list[MealRecommendation] = Field(min_length=3, max_length=3)


class WorkoutPlanInput(StrictModel):
    setting: Literal["commercial_gym", "home", "outdoor", "hotel_gym"]
    focus: Literal[
        "upper_body", "lower_body", "push", "pull", "legs", "full_body", "conditioning"
    ]
    intensity: Literal["light", "moderate", "heavy"]
    language: Locale = "en"


class Exercise(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    sets: str = Field(min_length=1, max_length=40)
    reps: str = Field(min_length=1, max_length=80)


class RecoveryAdvice(StrictModel):
    steps: str = Field(min_length=1, max_length=300)
    eat: str = Field(min_length=1, max_length=300)
    sleep: str = Field(min_length=1, max_length=300)
    stretch: str = Field(min_length=1, max_length=300)


class WorkoutPlanResult(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    exercises: list[Exercise] = Field(min_length=1, max_length=30)
    calories_burned: float = Field(ge=0, le=5_000)
    duration_min: float = Field(gt=0, le=600)
    recovery: RecoveryAdvice


class HealthMacroAdjustmentInput(StrictModel):
    baseline_tdee: float = Field(ge=800, le=7_000)
    sex: Literal["male", "female", "other"]
    age: float = Field(ge=18, le=100)
    weight_kg: float = Field(ge=30, le=350)
    height_cm: float = Field(ge=120, le=230)
    activity: Literal["sedentary", "light", "moderate", "active", "very"]
    health_issues: str = Field(min_length=1, max_length=500)
    language: Locale = "en"


class HealthMacroAdjustmentResult(StrictModel):
    adjusted_calories: float = Field(ge=1_000, le=6_000)
    protein_g: float = Field(ge=20, le=400)
    carb_g: float = Field(ge=20, le=1_000)
    fat_g: float = Field(ge=20, le=250)
    note: str = Field(min_length=1, max_length=1_200)
    disclaimer: str = Field(min_length=1, max_length=1_200)

    @model_validator(mode="after")
    def macros_approximately_match_calories(self) -> "HealthMacroAdjustmentResult":
        macro_calories = self.protein_g * 4 + self.carb_g * 4 + self.fat_g * 9
        if abs(macro_calories - self.adjusted_calories) / self.adjusted_calories > 0.25:
            raise ValueError("macro calories must be within 25% of adjusted_calories")
        return self


_TASK_INPUTS: dict[str, type[StrictModel]] = {
    "daily_tip": DailyTipInput,
    "meal_recommendations": MealRecommendationsInput,
    "workout_plan": WorkoutPlanInput,
    "health_macro_adjustment": HealthMacroAdjustmentInput,
}


class UnsupportedAITaskError(ValueError):
    pass


class AITaskService:
    """Validate a named use case and execute only its server-owned prompt."""

    def execute(
        self,
        use_case: str,
        raw_input: dict[str, Any],
        *,
        user_id: str,
    ) -> BaseModel:
        input_model = _TASK_INPUTS.get(use_case)
        if input_model is None:
            raise UnsupportedAITaskError(f"Unsupported AI task: {use_case}")
        validated = input_model.model_validate(raw_input)
        started_at = perf_counter()
        run_id = agent_traces.create_agent_run(
            user_id,
            json.dumps(
                {"use_case": use_case, "input": validated.model_dump(mode="json")},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        handlers = {
            "daily_tip": self._daily_tip,
            "meal_recommendations": self._meal_recommendations,
            "workout_plan": self._workout_plan,
            "health_macro_adjustment": self._health_macro_adjustment,
        }
        try:
            result = handlers[use_case](validated, run_id=run_id)
        except Exception as exc:
            agent_traces.fail_agent_run(
                run_id,
                user_id,
                exc,
                agent_traces.elapsed_ms(started_at),
            )
            raise
        agent_traces.succeed_agent_run(
            run_id,
            user_id,
            route="general",
            output_text=result.model_dump_json(),
            latency_ms=agent_traces.elapsed_ms(started_at),
            resolution_mode="main_llm",
        )
        return result

    @staticmethod
    def _invoke(
        *,
        response_model: type[StrictModel],
        purpose: str,
        prompt: str,
        value: StrictModel,
        run_id: str,
    ) -> StrictModel:
        return ai_execution_service.invoke_structured(
            response_model=response_model,
            node_name="ai_task",
            purpose=purpose,
            system_prompt=prompt,
            input_payload=value.model_dump(mode="json"),
            run_id=run_id,
        )

    def _daily_tip(self, value: StrictModel, *, run_id: str) -> TextResult:
        return TextResult.model_validate(
            self._invoke(
                response_model=TextResult,
                purpose="daily_tip",
                prompt=(
                    "Write one warm, concrete nutrition tip in at most two short "
                    "sentences. Prioritize the largest remaining macro gap and respect "
                    "every dietary constraint. Use the requested language."
                ),
                value=value,
                run_id=run_id,
            )
        )

    def _meal_recommendations(
        self,
        value: StrictModel,
        *,
        run_id: str,
    ) -> MealRecommendationsResult:
        return MealRecommendationsResult.model_validate(
            self._invoke(
                response_model=MealRecommendationsResult,
                purpose="meal_recommendations",
                prompt=(
                    "Generate exactly three distinct meals: one under 10 minutes, one "
                    "cooked, and one bought or ordered. Respect all dietary constraints, "
                    "avoid meals already eaten, use feasible household portions, move "
                    "toward remaining macros, and use the requested language."
                ),
                value=value,
                run_id=run_id,
            )
        )

    def _workout_plan(self, value: StrictModel, *, run_id: str) -> WorkoutPlanResult:
        return WorkoutPlanResult.model_validate(
            self._invoke(
                response_model=WorkoutPlanResult,
                purpose="workout_plan",
                prompt=(
                    "Build one safe workout session for the supplied setting, focus and "
                    "intensity. Give realistic duration, calorie estimate and recovery "
                    "steps. Use the requested language."
                ),
                value=value,
                run_id=run_id,
            )
        )

    def _health_macro_adjustment(
        self,
        value: StrictModel,
        *,
        run_id: str,
    ) -> HealthMacroAdjustmentResult:
        return HealthMacroAdjustmentResult.model_validate(
            self._invoke(
                response_model=HealthMacroAdjustmentResult,
                purpose="health_macro_adjustment",
                prompt=(
                    "Suggest only a conservative calorie and macro adjustment based on "
                    "the server-calculated baseline. Do not diagnose or prescribe. "
                    "Include a clear medical disclaimer in the requested language."
                ),
                value=value,
                run_id=run_id,
            )
        )
