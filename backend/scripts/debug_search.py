"""Сравнивает: что считает Python и что возвращает база на тот же вектор."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embeddings import get_embeddings  # noqa: E402
from app.services.supabase import get_supabase  # noqa: E402

QUERY = "куриная грудка"

emb = get_embeddings()
sb = get_supabase()

q_vec = emb.embed_query(QUERY)
literal = "[" + ",".join(str(x) for x in q_vec) + "]"

print(f"Длина вектора: {len(q_vec)}")
print(f"Первые 3 числа: {q_vec[:3]}")
print(f"Начало литерала: {literal[:80]}")
print(f"Длина литерала: {len(literal)} символов\n")

print("--- Что вернула база ---")
rows = sb.rpc(
    "match_foods", {"query_embedding": literal, "match_count": 5}
).execute().data
for row in rows:
    print(f"  {row['similarity']:.4f}  {row['food_name']}")

print("\n--- Что считает Python на тех же данных ---")
sample = (
    sb.table("food_nutrients")
    .select("food_name, embedding")
    .in_("food_name", [
        "chicken breast raw", "soybean curd cheese",
        "potato gratin", "sauerkraut canned",
    ])
    .execute()
).data

qv = np.array(q_vec)
for row in sample:
    vec = row["embedding"]
    if isinstance(vec, str):
        vec = json.loads(vec)
    print(f"  {float(qv @ np.array(vec)):.4f}  {row['food_name']}")