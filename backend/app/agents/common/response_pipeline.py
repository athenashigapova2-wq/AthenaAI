"""Post-process specialist responses using server-owned facts and style rules."""

import re
from datetime import date
from typing import Any


def _weight_trend_dates(result: Any) -> tuple[date, date] | None:
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    weights = result.get("weights") or []
    if len(weights) < 2:
        return None
    try:
        first = date.fromisoformat(str(weights[0]["date"]))
        last = date.fromisoformat(str(weights[-1]["date"]))
    except (KeyError, TypeError, ValueError):
        return None
    return first, last


def _actual_progress_period(result: Any, locale: str) -> str:
    dates = _weight_trend_dates(result)
    if dates is None:
        return ""
    first, last = dates
    days = (last - first).days
    if locale == "ru":
        return (
            f"за период с {first.strftime('%d.%m.%Y')} по {last.strftime('%d.%m.%Y')} ({days} дн.)"
        )
    return f"from {first.isoformat()} to {last.isoformat()} ({days} days)"


def _remove_known_trend_contradictions(text: str, trend: Any, locale: str) -> str:
    """Remove only claims that progress data is absent when the server has a trend."""
    if _weight_trend_dates(trend) is None:
        return text
    denial_terms = (
        ("нет", "недостаточно", "отсутств", "не удалось", "невозможно")
        if locale == "ru"
        else ("no ", "not enough", "insufficient", "unavailable", "unable")
    )
    progress_terms = (
        ("прогресс", "динамик", "изменен", "тренд", "вес")
        if locale == "ru"
        else ("progress", "trend", "change", "weight")
    )
    data_terms = (
        ("информац", "данн", "запис") if locale == "ru" else ("information", "data", "record")
    )
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    kept = []
    for part in parts:
        lowered = part.lower()
        contradiction = (
            any(term in lowered for term in denial_terms)
            and any(term in lowered for term in progress_terms)
            and any(term in lowered for term in data_terms)
        )
        if part.strip() and not contradiction:
            kept.append(part.strip())
    return " ".join(kept)


def _normalize_progress_period(text: str, trend: Any, locale: str) -> str:
    period = _actual_progress_period(trend, locale)
    if not period:
        return text
    pattern = (
        r"(?:за|в\s+течение)\s+(?:последн\w+\s+)?(?:\d+\s+)?"
        r"(?:д(?:ень|ня|ней)|недел\w*|месяц\w*)"
        if locale == "ru"
        else r"(?:over|during|for)\s+the\s+(?:last|past)\s+(?:\d+\s+)?(?:days?|weeks?|months?)"
    )
    return re.sub(pattern, period, text, flags=re.IGNORECASE)


def _normalize_address_style(text: str, locale: str) -> str:
    if locale != "ru":
        return text
    replacements = {
        "ты": "вы",
        "тебя": "вас",
        "тебе": "вам",
        "тобой": "вами",
        "твой": "ваш",
        "твоя": "ваша",
        "твоё": "ваше",
        "твое": "ваше",
        "твои": "ваши",
        "твоего": "вашего",
        "твоей": "вашей",
        "твоему": "вашему",
        "твоим": "вашим",
        "твоих": "ваших",
    }
    pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, replacements)) + r")\b",
        re.IGNORECASE,
    )
    normalized = pattern.sub(lambda match: replacements[match.group(0).lower()], text)
    informal_imperatives = {
        "продолжай": "продолжайте",
        "попробуй": "попробуйте",
        "добавь": "добавьте",
        "убери": "уберите",
        "замени": "замените",
        "следи": "следите",
        "сохраняй": "сохраняйте",
        "обратись": "обратитесь",
        "учти": "учтите",
        "помни": "помните",
    }
    imperative_pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, informal_imperatives)) + r")\b",
        re.IGNORECASE,
    )
    return imperative_pattern.sub(
        lambda match: informal_imperatives[match.group(0).lower()],
        normalized,
    )


def _sanitize_internal_notation(text: str, locale: str) -> str:
    cleaned = re.sub(
        r"\[(?:food_nutrients|matched_food|reference_food)\s*:[^\]]*\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    database_label = "проверенная база продуктов" if locale == "ru" else "verified food database"
    cleaned = re.sub(r"\bfood_nutrients\b", database_label, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:matched_food|reference_food)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bserver[- ]fetched\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return re.sub(r"\s+([,.;:])", r"\1", cleaned).strip()


def _finalize_answer(text: Any, locale: str, trend: Any = None) -> str:
    answer = _sanitize_internal_notation(str(text), locale)
    answer = _remove_known_trend_contradictions(answer, trend, locale)
    answer = _normalize_progress_period(answer, trend, locale)
    return _normalize_address_style(answer, locale).strip()


def _weight_trend_evidence(result: Any, locale: str) -> str:
    """Render the server-fetched trend so a calorie decision always shows its evidence."""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return ""
    weights = result.get("weights") or []
    delta = result.get("delta_kg")
    if len(weights) < 2 or delta is None:
        if locale == "ru":
            return (
                "Данных о динамике веса пока недостаточно; без такого тренда менять "
                "целевую калорийность не следует."
            )
        return (
            "There is not enough weight-trend data yet; the calorie target should not "
            "be changed without it."
        )
    first = weights[0]
    last = weights[-1]
    first_weight = float(first["weight_kg"])
    last_weight = float(last["weight_kg"])
    if locale == "ru":
        return (
            f"Проверенный прогресс {_actual_progress_period(result, locale)}: "
            f"вес {first_weight:g} кг ({first.get('date')}) → "
            f"{last_weight:g} кг ({last.get('date')}), изменение {float(delta):+g} кг."
        )
    return (
        f"Verified progress {_actual_progress_period(result, locale)}: "
        f"weight {first_weight:g} kg ({first.get('date')}) → "
        f"{last_weight:g} kg ({last.get('date')}), change {float(delta):+g} kg."
    )
