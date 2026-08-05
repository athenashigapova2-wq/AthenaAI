"""Импорт справочника продуктов из датасета Kaggle Food Nutrition в Supabase.

ПРОБЛЕМА, КОТОРУЮ РЕШАЕТ СКРИПТ
--------------------------------
В исходных CSV значения даны НА ПОРЦИЮ, а не на 100 г, причём размер
порции у каждого продукта свой и в файле явно не указан. Прошлый импорт
записал их в колонки *_per_100g как есть — отсюда "гусиное мясо, 6077 ккал"
(это была порция в 1.6 кг, то есть целая тушка).

Массу порции восстанавливаем из состава: продукт состоит из воды, жира,
углеводов, белка и клетчатки. Сумма этих колонок и есть вес порции.
Проверено на известных продуктах — расхождение с реальными значениями 1-4%.

ЗАПУСК
------
    python scripts/import_food_data.py --csv-dir data/kaggle --dry-run
    python scripts/import_food_data.py --csv-dir data/kaggle

Сначала всегда с --dry-run: он ничего не пишет в базу, только показывает,
что получится.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.supabase import get_supabase  # noqa: E402

# Колонки массы, из которых складывается вес порции (граммы)
MASS_COLUMNS = ["Fat", "Carbohydrates", "Protein", "Water", "Dietary Fiber"]

# Минимальный вес порции. Ниже этого значения данные заведомо неполные:
# у таких строк Water = 0 и почти все нутриенты пустые.
MIN_SERVING_G = 5.0

# Физические границы. Максимум калорийности - чистый жир, 9 ккал/г = 900.
MAX_KCAL_PER_100G = 900.0
MAX_MACRO_SUM_G = 100.0


def load_csv_files(csv_dir: Path) -> pd.DataFrame:
    """Читает все FOOD-DATA-GROUP*.csv и склеивает в одну таблицу."""
    files = sorted(csv_dir.glob("FOOD-DATA-GROUP*.csv"))
    if not files:
        raise FileNotFoundError(
            f"В папке {csv_dir} не найдено файлов FOOD-DATA-GROUP*.csv"
        )

    frames = []
    for path in files:
        frame = pd.read_csv(path)
        print(f"  {path.name}: {len(frame)} строк")
        frames.append(frame)

    return pd.concat(frames, ignore_index=True)


def rescale_to_100g(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Пересчитывает значения с порции на 100 г и отбрасывает невосстановимое.

    Возвращает очищенную таблицу и статистику отбраковки.
    """
    stats: dict[str, int] = {"total": len(df)}

    df = df.copy()
    for column in MASS_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    df["serving_g"] = df[MASS_COLUMNS].sum(axis=1)

    # Отбраковка 1: вес порции слишком мал - состав не заполнен
    too_light = df["serving_g"] < MIN_SERVING_G
    stats["dropped_no_mass"] = int(too_light.sum())
    df = df[~too_light]

    # Пересчёт: значение на порцию -> значение на 100 г
    scalable = [
        "Caloric Value", "Fat", "Carbohydrates", "Protein",
        "Sugars", "Dietary Fiber",
    ]
    for column in scalable:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        df[column] = df[column] / df["serving_g"] * 100

    # Отбраковка 2: результат физически невозможен
    macro_sum = df["Fat"] + df["Carbohydrates"] + df["Protein"]
    impossible = (df["Caloric Value"] > MAX_KCAL_PER_100G) | (macro_sum > MAX_MACRO_SUM_G)
    stats["dropped_impossible"] = int(impossible.sum())
    df = df[~impossible]

    # Отбраковка 3: дубликаты названий - оставляем первое вхождение
    before = len(df)
    df = df.drop_duplicates(subset=["food"], keep="first")
    stats["dropped_duplicates"] = before - len(df)

    stats["kept"] = len(df)
    return df, stats


def classify(row: pd.Series) -> str:
    """Грубая категоризация по преобладающему макронутриенту.

    Нужна для колонки category в схеме БД. Точность здесь не критична:
    поиск идёт по названию, категория - вспомогательный фильтр.
    """
    protein_kcal = row["Protein"] * 4
    carb_kcal = row["Carbohydrates"] * 4
    fat_kcal = row["Fat"] * 9
    total = protein_kcal + carb_kcal + fat_kcal

    if total <= 0:
        return "mixed"
    if row.get("Dietary Fiber", 0) >= 6:
        return "fiber"

    shares = {
        "protein": protein_kcal / total,
        "carb": carb_kcal / total,
        "fat": fat_kcal / total,
    }
    top, share = max(shares.items(), key=lambda item: item[1])
    return top if share >= 0.5 else "mixed"


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Превращает строки таблицы в словари под схему food_nutrients."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "food_name": str(row["food"]).strip().lower(),
            "category": classify(row),
            "calories_per_100g": round(float(row["Caloric Value"]), 1),
            "protein_g": round(float(row["Protein"]), 1),
            "carbs_g": round(float(row["Carbohydrates"]), 1),
            "fat_g": round(float(row["Fat"]), 1),
            "sugar_g": round(float(row["Sugars"]), 1),
        })
    return records


def upload(records: list[dict[str, Any]], batch_size: int = 500) -> None:
    """Заливает записи в Supabase пачками.

    Пачками - потому что один запрос на 2000 строк упрётся в лимит
    размера тела запроса, а 2000 запросов по одной строке будут идти минуты.
    """
    supabase = get_supabase()

    print("\nОчищаю таблицу food_nutrients...")
    supabase.table("food_nutrients").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()

    total = len(records)
    for start in range(0, total, batch_size):
        batch = records[start:start + batch_size]
        supabase.table("food_nutrients").insert(batch).execute()
        print(f"  загружено {min(start + batch_size, total)} / {total}")


def preview(records: list[dict[str, Any]]) -> None:
    """Показывает контрольные продукты - проверка глазами перед заливкой."""
    checks = [
        "chicken breast raw", "banana", "white rice raw",
        "cheddar cheese", "goose meat raw", "olive oil",
    ]
    by_name = {r["food_name"]: r for r in records}

    print("\nКонтрольные значения (ккал / белок / углеводы / жир на 100 г):")
    for name in checks:
        record = by_name.get(name)
        if record is None:
            print(f"  {name:22s} - нет в датасете")
            continue
        print(
            f"  {name:22s} {record['calories_per_100g']:7.1f} "
            f"{record['protein_g']:6.1f} {record['carbs_g']:6.1f} {record['fat_g']:6.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv-dir", type=Path, default=Path("data/kaggle"),
        help="Папка с файлами FOOD-DATA-GROUP*.csv",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Только посчитать и показать, ничего не писать в базу",
    )
    args = parser.parse_args()

    print(f"Читаю CSV из {args.csv_dir}")
    raw = load_csv_files(args.csv_dir)

    print(f"\nВсего строк: {len(raw)}")
    cleaned, stats = rescale_to_100g(raw)

    print("\nОтбраковка:")
    print(f"  нет данных о составе : {stats['dropped_no_mass']}")
    print(f"  невозможные значения : {stats['dropped_impossible']}")
    print(f"  дубликаты названий   : {stats['dropped_duplicates']}")
    print(f"  ОСТАЛОСЬ             : {stats['kept']} из {stats['total']}")

    records = to_records(cleaned)
    preview(records)

    if args.dry_run:
        print("\n[dry-run] База не тронута. Убери --dry-run, чтобы залить.")
        return

    answer = input(f"\nЗаменить содержимое food_nutrients на {len(records)} записей? [y/N] ")
    if answer.strip().lower() != "y":
        print("Отменено.")
        return

    upload(records)
    print("\nГотово.")


if __name__ == "__main__":
    main()