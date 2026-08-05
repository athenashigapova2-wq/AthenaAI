"""Считает векторы для всех названий продуктов и сохраняет в базу.

Запускается один раз после импорта справочника. При смене модели
эмбеддингов нужно перезапустить — векторы разных моделей несравнимы.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embeddings import get_embeddings  # noqa: E402
from app.services.supabase import get_supabase  # noqa: E402

BATCH_SIZE = 100


def fetch_all_foods(supabase) -> list[dict]:
    """Читает все продукты постранично.

    Supabase отдаёт максимум 1000 строк за запрос, поэтому нужна
    пагинация — иначе молча получишь только первую тысячу.
    """
    rows: list[dict] = []
    page_size = 1000
    start = 0

    while True:
        result = (
            supabase.table("food_nutrients")
            .select("id, food_name")
            .order("id")
            .range(start, start + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        rows.extend(result.data)
        if len(result.data) < page_size:
            break
        start += page_size

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    supabase = get_supabase()
    foods = fetch_all_foods(supabase)
    print(f"Продуктов в базе: {len(foods)}")

    if args.dry_run:
        print("[dry-run] Первые 5 названий:")
        for food in foods[:5]:
            print(f"  {food['food_name']}")
        return

    print("Загружаю модель эмбеддингов...")
    embedder = get_embeddings()

    started = time.time()
    for start in range(0, len(foods), BATCH_SIZE):
        batch = foods[start:start + BATCH_SIZE]
        names = [food["food_name"] for food in batch]

        vectors = embedder.embed_documents(names)

        for food, vector in zip(batch, vectors):
            supabase.table("food_nutrients").update(
                {"embedding": vector}
            ).eq("id", food["id"]).execute()

        done = min(start + BATCH_SIZE, len(foods))
        elapsed = time.time() - started
        speed = done / elapsed if elapsed else 0
        remaining = (len(foods) - done) / speed if speed else 0
        print(f"  {done} / {len(foods)}   осталось ~{remaining:.0f} сек")

    print(f"\nГотово за {time.time() - started:.0f} сек")


if __name__ == "__main__":
    main()