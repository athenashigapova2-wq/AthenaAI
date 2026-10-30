"""Deterministic fallback and policy checks for meal recommendations."""

from __future__ import annotations

from itertools import cycle
from typing import Any

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "chicken": "chicken breast",
        "salmon": "salmon",
        "tuna": "tuna",
        "egg": "eggs",
        "lentils": "lentils",
        "chickpeas": "chickpeas",
        "tofu": "tofu",
        "beans": "beans",
        "rice": "rice",
        "buckwheat": "buckwheat",
        "potato": "potatoes",
        "quinoa": "quinoa",
        "vegetables": "mixed vegetables",
        "oil": "olive oil",
    },
    "ru": {
        "chicken": "куриная грудка",
        "salmon": "лосось",
        "tuna": "тунец",
        "egg": "яйца",
        "lentils": "чечевица",
        "chickpeas": "нут",
        "tofu": "тофу",
        "beans": "фасоль",
        "rice": "рис",
        "buckwheat": "гречка",
        "potato": "картофель",
        "quinoa": "киноа",
        "vegetables": "овощи",
        "oil": "оливковое масло",
    },
    "fr": {
        "chicken": "blanc de poulet",
        "salmon": "saumon",
        "tuna": "thon",
        "egg": "oeufs",
        "lentils": "lentilles",
        "chickpeas": "pois chiches",
        "tofu": "tofu",
        "beans": "haricots",
        "rice": "riz",
        "buckwheat": "sarrasin",
        "potato": "pommes de terre",
        "quinoa": "quinoa",
        "vegetables": "légumes variés",
        "oil": "huile d'olive",
    },
    "es": {
        "chicken": "pechuga de pollo",
        "salmon": "salmón",
        "tuna": "atún",
        "egg": "huevos",
        "lentils": "lentejas",
        "chickpeas": "garbanzos",
        "tofu": "tofu",
        "beans": "frijoles",
        "rice": "arroz",
        "buckwheat": "trigo sarraceno",
        "potato": "patatas",
        "quinoa": "quinoa",
        "vegetables": "verduras variadas",
        "oil": "aceite de oliva",
    },
    "zh": {
        "chicken": "鸡胸肉",
        "salmon": "三文鱼",
        "tuna": "金枪鱼",
        "egg": "鸡蛋",
        "lentils": "扁豆",
        "chickpeas": "鹰嘴豆",
        "tofu": "豆腐",
        "beans": "豆类",
        "rice": "米饭",
        "buckwheat": "荞麦",
        "potato": "土豆",
        "quinoa": "藜麦",
        "vegetables": "混合蔬菜",
        "oil": "橄榄油",
    },
}

_PROTEINS_BY_PATTERN: dict[str, tuple[str, ...]] = {
    "omnivore": ("chicken", "salmon", "tuna", "egg", "lentils", "chickpeas", "tofu", "beans"),
    "pescatarian": ("salmon", "tuna", "egg", "lentils", "chickpeas", "tofu", "beans"),
    "vegetarian": ("egg", "lentils", "chickpeas", "tofu", "beans"),
    "vegan": ("lentils", "chickpeas", "tofu", "beans"),
}
_CARBS = ("rice", "buckwheat", "potato", "quinoa")
_TAGS: dict[str, set[str]] = {
    "chicken": {"meat", "poultry"},
    "salmon": {"fish"},
    "tuna": {"fish"},
    "egg": {"egg"},
    "lentils": {"legume"},
    "chickpeas": {"legume"},
    "tofu": {"soy"},
    "beans": {"legume"},
}
_TAG_ALIASES: dict[str, tuple[str, ...]] = {
    "dairy": ("milk", "dairy", "lactose", "cheese", "yogurt", "молок", "лактоз", "сыр", "творог", "йогурт"),
    "fish": ("fish", "salmon", "tuna", "рыб", "лосос", "тунец"),
    "egg": ("egg", "яйц"),
    "soy": ("soy", "tofu", "соя", "тофу"),
    "legume": ("legume", "lentil", "chickpea", "bean", "бобов", "чечев", "нут", "фасол"),
    "poultry": ("chicken", "poultry", "куриц"),
    "gluten": ("gluten", "wheat", "bread", "pasta", "глютен", "пшен", "хлеб", "макарон"),
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _blocked_tags(values: list[str]) -> set[str]:
    normalized = " | ".join(_normalize(value) for value in values)
    return {
        tag
        for tag, aliases in _TAG_ALIASES.items()
        if any(alias in normalized for alias in aliases)
    }


def _is_directly_blocked(key: str, blocked_values: list[str]) -> bool:
    labels = {_normalize(key)}
    labels.update(_normalize(locale_labels[key]) for locale_labels in _LABELS.values())
    for value in blocked_values:
        blocked = _normalize(value)
        if blocked and any(blocked in label or label in blocked for label in labels):
            return True
    return False


def _macro_numbers(remaining: dict[str, Any], factor: float) -> dict[str, float]:
    remaining_calories = max(float(remaining.get("calories") or 0), 0)
    target_calories = min(max(remaining_calories or 450.0, 250.0), 750.0) * factor
    weights = (
        max(float(remaining.get("protein") or 0), 0) * 4,
        max(float(remaining.get("carbs") or 0), 0) * 4,
        max(float(remaining.get("fat") or 0), 0) * 9,
    )
    total = sum(weights)
    raw_ratios = (0.30, 0.40, 0.30) if total <= 0 else tuple(value / total for value in weights)
    # A missing macro should influence prioritization, but must not produce an
    # impossible meal such as 150 g protein with zero carbohydrate and fat.
    protein_ratio = min(max(raw_ratios[0], 0.20), 0.40)
    fat_ratio = min(max(raw_ratios[2], 0.20), 0.35)
    carb_ratio = 1 - protein_ratio - fat_ratio
    protein = round(target_calories * protein_ratio / 4, 1)
    carbs = round(target_calories * carb_ratio / 4, 1)
    fat = round(target_calories * fat_ratio / 9, 1)
    calories = round(protein * 4 + carbs * 4 + fat * 9, 1)
    return {"calories": calories, "protein_g": protein, "carbs_g": carbs, "fat_g": fat}


def _copy(locale: str, style: str, protein: str, carb: str) -> tuple[str, str, str]:
    p = _LABELS[locale][protein]
    c = _LABELS[locale][carb]
    templates = {
        "en": {
            "quick": (f"Quick {p} bowl", f"A quick bowl with {p}, {c} and vegetables.", "5–10 min"),
            "cooked": (f"{p.title()} with {c}", f"A cooked serving of {p}, {c} and vegetables.", "25–35 min"),
            "bought": (
                f"Order-ready {p} bowl",
                f"Order a bowl with {p}, {c} and vegetables; ask for sauce separately.",
                "ready-made",
            ),
        },
        "ru": {
            "quick": (f"Быстрый боул: {p}", f"Быстрый боул: {p}, {c} и овощи.", "5–10 мин"),
            "cooked": (f"{p.capitalize()} с {c}", f"Горячая порция: {p}, {c} и овощи.", "25–35 мин"),
            "bought": (f"Боул на заказ: {p}", f"Закажите боул: {p}, {c} и овощи; соус отдельно.", "готовое блюдо"),
        },
    }
    if locale in templates:
        return templates[locale][style]
    fallback_name, _, prep_time = templates["en"][style]
    descriptions = {
        "fr": f"Un repas simple avec {p}, {c} et des légumes.",
        "es": f"Una comida sencilla con {p}, {c} y verduras.",
        "zh": f"一份包含{p}、{c}和蔬菜的简单餐食。",
    }
    return fallback_name.replace(_LABELS["en"][protein], p), descriptions[locale], prep_time


def build_fallback_recommendations(context: dict[str, Any]) -> dict[str, Any]:
    """Return three profile-safe alternatives without consulting shopping state."""
    locale = str(context.get("language") or "en")
    if locale not in _LABELS:
        locale = "en"
    pattern = str(context.get("dietary_pattern") or "omnivore")
    if pattern not in _PROTEINS_BY_PATTERN:
        pattern = "omnivore"
    restrictions = {_normalize(item) for item in context.get("dietary_restrictions") or []}
    blocked_values = [
        str(item)
        for item in [*(context.get("allergies") or []), *(context.get("disliked_foods") or [])]
        if str(item).strip()
    ]
    tags = _blocked_tags(blocked_values)
    if "lactose_free" in restrictions:
        tags.add("dairy")
    if "gluten_free" in restrictions:
        tags.add("gluten")

    proteins = [
        key
        for key in _PROTEINS_BY_PATTERN[pattern]
        if not (_TAGS.get(key, set()) & tags) and not _is_directly_blocked(key, blocked_values)
    ]
    if "halal" in restrictions or "kosher" in restrictions:
        proteins = [key for key in proteins if key != "chicken"]
    carbs = [key for key in _CARBS if not _is_directly_blocked(key, blocked_values)]
    if not proteins or not carbs:
        raise ValueError("No deterministic meal fallback satisfies the supplied food constraints")

    protein_cycle = cycle(proteins)
    carb_cycle = cycle(carbs)
    remaining = dict(context.get("remaining") or {})
    prices = {"low": (180, 260, 350), "medium": (260, 420, 550), "high": (420, 650, 850)}
    budget = str(context.get("budget") or "medium")
    price_values = prices.get(budget, prices["medium"])
    meals: list[dict[str, Any]] = []
    for index, (style, factor) in enumerate((("quick", 0.85), ("cooked", 1.0), ("bought", 0.95))):
        protein = next(protein_cycle)
        carb = next(carb_cycle)
        name, description, prep_time = _copy(locale, style, protein, carb)
        meals.append(
            {
                "name": name,
                "description": description,
                **_macro_numbers(remaining, factor),
                "prep_time": prep_time,
                "estimated_price_rub": price_values[index],
                "ingredients": [
                    _LABELS[locale][protein],
                    _LABELS[locale][carb],
                    _LABELS[locale]["vegetables"],
                    _LABELS[locale]["oil"],
                ],
            }
        )
    return {"meals": meals}


def recommendation_policy_issues(payload: dict[str, Any], context: dict[str, Any]) -> list[str]:
    """Check hard dietary constraints on provider-generated recommendations."""
    text = _normalize(payload)
    issues: list[str] = []
    pattern = str(context.get("dietary_pattern") or "omnivore")
    forbidden_by_pattern = {
        "vegan": (
            "meat",
            "chicken",
            "fish",
            "salmon",
            "tuna",
            "egg",
            "milk",
            "cheese",
            "yogurt",
            "мяс",
            "куриц",
            "рыб",
            "яйц",
            "молок",
            "сыр",
        ),
        "vegetarian": ("meat", "chicken", "fish", "salmon", "tuna", "мяс", "куриц", "рыб"),
        "pescatarian": ("meat", "chicken", "beef", "pork", "мяс", "куриц", "говяд", "свин"),
    }
    if any(term in text for term in forbidden_by_pattern.get(pattern, ())):
        issues.append(f"dietary_pattern:{pattern}")
    restrictions = {_normalize(item) for item in context.get("dietary_restrictions") or []}
    if "lactose_free" in restrictions and any(alias in text for alias in _TAG_ALIASES["dairy"]):
        issues.append("dietary_restriction:lactose_free")
    if "gluten_free" in restrictions and any(alias in text for alias in _TAG_ALIASES["gluten"]):
        issues.append("dietary_restriction:gluten_free")
    if "halal" in restrictions and any(term in text for term in ("pork", "alcohol", "свин", "алкогол")):
        issues.append("dietary_restriction:halal")
    if "kosher" in restrictions and any(term in text for term in ("pork", "shellfish", "shrimp", "свин", "кревет")):
        issues.append("dietary_restriction:kosher")
    blocked_values = [
        str(value)
        for value in [*(context.get("allergies") or []), *(context.get("disliked_foods") or [])]
        if str(value).strip()
    ]
    for tag in sorted(_blocked_tags(blocked_values) & _blocked_tags([text])):
        issues.append(f"blocked_food_tag:{tag}")
    for value in blocked_values:
        normalized = _normalize(value)
        if normalized and normalized in text:
            issues.append(f"blocked_food:{normalized}")
    return list(dict.fromkeys(issues))
