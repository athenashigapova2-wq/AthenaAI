"""Инструменты питания: справочник продуктов, дневник, запись еды."""

from datetime import date as date_type
from difflib import SequenceMatcher
import re
from typing import Any

from app.services.supabase import get_supabase


_FOOD_NUTRIENT_COLUMNS = (
    "food_name, calories_per_100g, protein_g, carbs_g, fat_g"
)

# Exact names verified against the imported food_nutrients dataset. Full-day plans
# deliberately use a small auditable catalogue: a model may choose foods and grams,
# but it may not invent a fuzzy database match.
PLAN_FOOD_REFERENCE_NAMES = (
    "oats",
    "egg raw",
    "greek yogurt",
    "yogurt",
    "banana",
    "cottage cheese nonfat",
    "chicken breast raw",
    "turkey breast roasted",
    "beef tenderloin steak cooked",
    "cod cooked",
    "salmon raw",
    "white rice cooked",
    "white rice raw",
    "buckwheat raw",
    "potato raw",
    "cucumber",
    "carrots raw",
    "broccoli cooked",
    "spinach raw",
    "vegetable salad",
    "olive oil",
)


def _normalized_food_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def lookup_food_reference(query: str) -> dict[str, Any]:
    """Resolve one exact English food name and return DB values per 100 g.

    Fuzzy results are suggestions only. Nutritionally different foods must never be
    silently substituted (for example ``beef raw`` -> ``beets raw`` or ``tomato`` ->
    ``tomato soup``).
    """
    # Import locally so longitudinal tests can replace the user's diary client
    # without accidentally replacing the shared read-only food reference DB.
    from app.services.supabase import get_supabase as get_food_database

    normalized = _normalized_food_name(query)
    if len(normalized) < 2:
        raise ValueError("food reference is empty")

    sb = get_food_database()
    exact = (
        sb.table("food_nutrients")
        .select(_FOOD_NUTRIENT_COLUMNS)
        .eq("food_name", normalized)
        .limit(1)
        .execute()
    )
    rows = exact.data or []
    if not rows:
        fuzzy = sb.rpc(
            "search_food_nutrients",
            {"search_term": normalized, "match_limit": 5},
        ).execute()
        suggestions = sorted(
            {
                str(row.get("food_name", "")).strip()
                for row in (fuzzy.data or [])
                if row.get("food_name")
            },
            key=lambda name: SequenceMatcher(
                None,
                normalized,
                _normalized_food_name(name),
            ).ratio(),
            reverse=True,
        )[:3]
        hint = f"; exact suggestions: {', '.join(suggestions)}" if suggestions else ""
        raise LookupError(f"exact food not found: {query}{hint}")

    best = rows[0]
    matched = _normalized_food_name(str(best.get("food_name", "")))
    if matched != normalized:
        raise LookupError(f"food name is not an exact match: {query} -> {matched}")

    return {
        "food_name": str(best["food_name"]),
        "calories_per_100g": float(best["calories_per_100g"] or 0),
        "protein_g": float(best["protein_g"] or 0),
        "carbs_g": float(best["carbs_g"] or 0),
        "fat_g": float(best["fat_g"] or 0),
    }


def _translate_to_english(query: str) -> str:
    """Переводит запрос на язык справочника.

    Справочник англоязычный, а пользователи пишут на пяти языках.
    Кросс-языковые эмбеддинги на кириллице и иероглифах работают плохо
    (Recall@5 = 37%), предварительный перевод поднимает до 93%.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.ai_execution import ai_execution_service

    try:
        response = ai_execution_service.invoke(
            messages=[
                SystemMessage(content=(
                    "Translate the food name to English. "
                    "If it is already English, return it unchanged. "
                    "Reply with ONLY the English name, 1-2 words, no explanation."
                )),
                HumanMessage(content=query),
            ],
            node_name="nutrition",
            purpose="food_translation",
            run_id=None,
            default_tier="small",
            temperature=0.0,
        )
        translated = response.content.strip().strip('."')
        return translated or query
    except Exception:
        return query


def search_food(query: str, limit: int = 5) -> dict[str, Any]:
    """Семантический поиск продукта в справочнике.

    Запрос переводится на английский, затем ищется по косинусной близости
    векторов. Работает с запросами на любом из поддерживаемых языков.
    """
    from app.embeddings import get_embeddings

    english_query = _translate_to_english(query)
    query_vector = get_embeddings().embed_query(english_query)
    vector_literal = "[" + ",".join(str(x) for x in query_vector) + "]"

    sb = get_supabase()
    result = sb.rpc(
        "match_foods",
        {"query_embedding": vector_literal, "match_count": limit},
    ).execute()

    if not result.data:
        return {
            "status": "not_found",
            "message": f"Продукт '{query}' не найден в справочнике",
        }

    foods = [
        {k: v for k, v in row.items() if k != "similarity"}
        for row in result.data
    ]
    return {"status": "ok", "count": len(foods), "foods": foods}

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
