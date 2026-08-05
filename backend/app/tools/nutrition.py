"""Инструменты питания: справочник продуктов, дневник, запись еды."""

from datetime import date as date_type
from typing import Any

from app.services.supabase import get_supabase


def search_food(query: str, limit: int = 5) -> dict[str, Any]:
    """Поиск продукта в справочнике по части названия.

    Ранжирование: точное совпадение → начинается с запроса → содержит.
    Внутри группы короткие названия выше — они обычно базовые продукты,
    а не составные блюда.
    """
    sb = get_supabase()
    result = (
        sb.table("food_nutrients")
        .select("food_name, category, calories_per_100g, protein_g, carbs_g, fat_g")
        .ilike("food_name", f"%{query}%")
        .limit(50)
        .execute()
    )

    if not result.data:
        return {
            "status": "not_found",
            "message": f"Продукт '{query}' не найден в справочнике",
        }

    q = query.lower().strip()

    def rank(item: dict) -> tuple[int, int]:
        name = (item.get("food_name") or "").lower()
        if name == q:
            group = 0
        elif name.startswith(q):
            group = 1
        else:
            group = 2
        return (group, len(name))

    ranked = sorted(result.data, key=rank)[:limit]
    return {"status": "ok", "count": len(ranked), "foods": ranked}


def get_daily_intake(user_id: str, day: str | None = None) -> dict[str, Any]:
    """Сводка съеденного за день: суммы КБЖУ и список приёмов пищи."""
    target_day = day or date_type.today().isoformat()

    sb = get_supabase()
    result = (
        sb.table("meal_logs")
        .select("name, meal_type, calories, protein_g, carbs_g, fat_g")
        .eq("user_id", user_id)
        .eq("date", target_day)
        .order("created_at")
        .execute()
    )

    meals = result.data or []
    totals = {
        "calories": sum(float(m["calories"] or 0) for m in meals),
        "protein_g": sum(float(m["protein_g"] or 0) for m in meals),
        "carbs_g": sum(float(m["carbs_g"] or 0) for m in meals),
        "fat_g": sum(float(m["fat_g"] or 0) for m in meals),
    }

    return {
        "status": "ok",
        "date": target_day,
        "meals_count": len(meals),
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "meals": meals,
    }


def log_meal(
    user_id: str,
    name: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    meal_type: str | None = None,
    day: str | None = None,
) -> dict[str, Any]:
    """Записывает приём пищи в дневник."""
    allowed = {"breakfast", "lunch", "dinner", "snack"}
    if meal_type is not None and meal_type not in allowed:
        return {
            "status": "error",
            "message": f"meal_type должен быть одним из {sorted(allowed)}",
        }

    if calories < 0 or protein_g < 0 or carbs_g < 0 or fat_g < 0:
        return {"status": "error", "message": "Значения КБЖУ не могут быть отрицательными"}

    sb = get_supabase()
    result = (
        sb.table("meal_logs")
        .insert({
            "user_id": user_id,
            "name": name,
            "meal_type": meal_type,
            "calories": calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "date": day or date_type.today().isoformat(),
        })
        .execute()
    )

    if not result.data:
        return {"status": "error", "message": "Не удалось сохранить запись"}
    return {"status": "ok", "logged": name, "calories": calories}