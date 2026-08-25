"""Замер качества поиска: Recall@1 и Recall@5 на 30 запросах.

Три режима сравнения на одном наборе запросов:
  trigram   — pg_trgm, поиск по буквенным фрагментам
  vector    — эмбеддинги, поиск по смыслу
  translate — перевод запроса на английский, затем векторный поиск
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.supabase import get_supabase  # noqa: E402
from app.tools.nutrition import search_food  # noqa: E402

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "search_cases.json"


def search_trigram(query: str, limit: int = 5) -> dict:
    """Старый поиск через pg_trgm — базовая точка отсчёта."""
    sb = get_supabase()
    result = sb.rpc(
        "search_food_nutrients",
        {"search_term": query, "match_limit": limit},
    ).execute()
    if not result.data:
        return {"status": "not_found", "foods": []}
    return {"status": "ok", "foods": result.data}


def search_translated(query: str, limit: int = 5) -> dict:
    """Перевод запроса на английский, затем векторный поиск."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.ai_execution import ai_execution_service

    response = ai_execution_service.invoke(
        messages=[
            SystemMessage(content=(
                "Translate the food name to English. "
                "If it is already English, return it unchanged. "
                "Reply with ONLY the English name, 1-2 words, no explanation."
            )),
            HumanMessage(content=query),
        ],
        node_name="search_eval",
        purpose="food_translation",
        default_tier="small",
        temperature=0.0,
    )
    english = response.content.strip().strip('."')
    print(f"       {query} -> {english}")
    return search_food(english, limit=limit)


def validate_expectations(cases: list[dict]) -> None:
    """Проверяет, что ожидаемые названия вообще есть в базе."""
    sb = get_supabase()
    wanted = {name for case in cases for name in case["expect"]}
    found = {
        row["food_name"]
        for row in sb.table("food_nutrients")
        .select("food_name")
        .in_("food_name", sorted(wanted))
        .execute()
        .data
    }
    missing = wanted - found
    if missing:
        print("ВНИМАНИЕ: этих названий нет в базе, случаи будут провальными:")
        for name in sorted(missing):
            print(f"  {name}")
        print()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "vector"

    if mode == "trigram":
        searcher = search_trigram
    elif mode == "translate":
        searcher = search_translated
    else:
        searcher = search_food

    print(f"Режим: {mode}\n")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    validate_expectations(cases)

    hit1 = hit5 = 0
    misses = []

    for case in cases:
        result = searcher(case["query"], limit=5)
        names = [f["food_name"] for f in result.get("foods", [])]
        expected = set(case["expect"])

        in_top1 = bool(names[:1]) and names[0] in expected
        in_top5 = bool(expected & set(names))

        hit1 += in_top1
        hit5 += in_top5

        mark = "OK " if in_top5 else "MISS"
        print(f"[{mark}] {case['query']:20s} -> {names[0] if names else '-'}")
        if not in_top5:
            misses.append((case["query"], names))

    total = len(cases)
    print(f"\nRecall@1: {hit1}/{total} = {hit1 / total:.0%}")
    print(f"Recall@5: {hit5}/{total} = {hit5 / total:.0%}")

    if misses:
        print("\nПромахи подробно:")
        for query, names in misses:
            print(f"  {query}: {names}")


if __name__ == "__main__":
    main()
