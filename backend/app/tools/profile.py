"""Инструменты работы с профилем пользователя.

Важно: user_id НЕ является параметром инструмента. Он подставляется
сервером из проверенного JWT. Если бы модель могла его задавать,
prompt injection в тексте пользователя давал бы доступ к чужим данным.
"""

from typing import Any

from app.services.supabase import get_supabase


def get_profile(user_id: str) -> dict[str, Any]:
    """Возвращает профиль пользователя: параметры тела, цель, целевые КБЖУ."""
    sb = get_supabase()
    result = (
        sb.table("user_profiles")
        .select(
            "age, sex, height_cm, weight_kg, goal, "
            "calorie_target, protein_target_g, carb_target_g, fat_target_g, "
            "allergies, disliked_foods, favorite_foods, "
            "budget, cooking_skill, onboarding_complete"
        )
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return {"status": "not_found", "message": "Профиль не заполнен"}

    profile = result.data[0]
    return {"status": "ok", "profile": profile}