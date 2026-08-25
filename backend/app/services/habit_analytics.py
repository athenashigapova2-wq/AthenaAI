"""Deterministic habit analytics followed by a canonical LLM insight."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai_execution import ai_execution_service
from app.services.supabase import get_supabase


Locale = Literal["ru", "en", "fr", "es", "zh"]


class DailyMacroAverage(BaseModel):
    calories: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)


class HabitAnalytics(BaseModel):
    period_start: date
    period_end: date
    meal_count: int = Field(ge=0)
    day_count: int = Field(ge=0)
    frequent_foods: list[str]
    average_daily: DailyMacroAverage
    macro_gap: str | None = None


class HabitInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: str = Field(min_length=1, max_length=1_200)


class HabitInsightResult(BaseModel):
    insufficient_data: bool = False
    analytics: HabitAnalytics | None = None
    suggestion: str | None = None


def _normalize_food_name(name: str) -> str:
    without_amounts = re.sub(
        r"\d+(?:[.,]\d+)?\s*(?:г|гр|g|ml|мл|kg|кг)?",
        "",
        name.casefold(),
    )
    return re.sub(r"\s+", " ", without_amounts).strip()


class HabitAnalyticsService:
    """Read owner-scoped history and calculate reproducible aggregates."""

    def analyze(self, user_id: str, *, today: date | None = None) -> HabitAnalytics | None:
        period_end = today or date.today()
        period_start = period_end - timedelta(days=13)
        client = get_supabase()
        meals_response = (
            client.table("meal_logs")
            .select("name,date,calories,protein_g,carbs_g,fat_g")
            .eq("user_id", user_id)
            .gte("date", period_start.isoformat())
            .lte("date", period_end.isoformat())
            .execute()
        )
        meals = meals_response.data or []
        if len(meals) < 3:
            return None

        profile_response = (
            client.table("user_profiles")
            .select("protein_target_g,carb_target_g,fat_target_g")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        profile = (profile_response.data or [None])[0]

        counts = Counter(
            normalized
            for meal in meals
            if (normalized := _normalize_food_name(str(meal.get("name") or "")))
        )
        frequent_foods = [name for name, _ in counts.most_common(5)]

        by_day: dict[str, dict[str, float]] = defaultdict(
            lambda: {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        )
        for meal in meals:
            values = by_day[str(meal["date"])]
            for field in values:
                values[field] += float(meal.get(field) or 0)
        day_count = len(by_day)
        average = DailyMacroAverage(
            **{
                field: round(sum(day[field] for day in by_day.values()) / day_count, 1)
                for field in ("calories", "protein_g", "carbs_g", "fat_g")
            }
        )
        return HabitAnalytics(
            period_start=period_start,
            period_end=period_end,
            meal_count=len(meals),
            day_count=day_count,
            frequent_foods=frequent_foods,
            average_daily=average,
            macro_gap=self._macro_gap(average, profile),
        )

    @staticmethod
    def _macro_gap(average: DailyMacroAverage, profile: dict[str, Any] | None) -> str | None:
        if not profile:
            return None
        gaps = []
        for macro, average_field, target_field in (
            ("protein", "protein_g", "protein_target_g"),
            ("carbs", "carbs_g", "carb_target_g"),
            ("fat", "fat_g", "fat_target_g"),
        ):
            target = float(profile.get(target_field) or 0)
            if target <= 0:
                continue
            relative = (getattr(average, average_field) - target) / target
            gaps.append((abs(relative), macro, relative))
        if not gaps:
            return None
        magnitude, macro, relative = max(gaps)
        if magnitude <= 0.1:
            return None
        return f"{macro}:{'over' if relative > 0 else 'under'}"


class HabitInsightGenerator:
    def generate(self, analytics: HabitAnalytics, locale: Locale) -> str:
        insight = ai_execution_service.invoke_structured(
            response_model=HabitInsight,
            node_name="habit_insight",
            purpose="generate_suggestion",
            system_prompt=(
                "Write one short, warm, concrete nutrition suggestion of at most two "
                "sentences. Ground it only in the supplied deterministic analytics, "
                "reference a frequent food when useful, and use the requested locale."
            ),
            input_payload={"locale": locale, "analytics": analytics.model_dump(mode="json")},
        )
        return insight.suggestion.strip()


class HabitInsightService:
    def __init__(
        self,
        *,
        analytics: HabitAnalyticsService | None = None,
        generator: HabitInsightGenerator | None = None,
    ) -> None:
        self._analytics = analytics or HabitAnalyticsService()
        self._generator = generator or HabitInsightGenerator()

    def generate(self, user_id: str, locale: Locale) -> HabitInsightResult:
        analytics = self._analytics.analyze(user_id)
        if analytics is None:
            return HabitInsightResult(insufficient_data=True)
        suggestion = self._generator.generate(analytics, locale)
        now = datetime.now(UTC).isoformat()
        response = (
            get_supabase().table("agent_memory")
            .upsert(
                {
                    "user_id": user_id,
                    "frequent_foods": analytics.frequent_foods,
                    "macro_gap": analytics.macro_gap,
                    "suggestion": suggestion,
                    "suggestion_generated_at": now,
                    "updated_at": now,
                },
                on_conflict="user_id",
            )
            .execute()
        )
        if response.data is None:
            raise RuntimeError("Supabase did not persist the habit insight")
        return HabitInsightResult(analytics=analytics, suggestion=suggestion)
