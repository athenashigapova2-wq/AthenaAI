"""Проверка гипотезы: понимает ли модель эмбеддингов разные языки.

Если русский запрос не окажется ближе к нужному английскому продукту,
чем к постороннему — весь план с векторным поиском не сработает,
и лучше узнать это сейчас, а не после часа индексации.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embeddings import get_embeddings  # noqa: E402

# Кандидаты — реальные названия из твоей базы
CANDIDATES = [
    "chicken breast raw",
    "chicken meat raw",
    "chicken fat",
    "chicken soup",
    "white rice raw",
    "banana",
    "olive oil",
    "cheddar cheese",
]

# Запрос -> какой кандидат ДОЛЖЕН оказаться первым
CASES = [
    ("куриная грудка", "chicken breast raw"),
    ("курица", "chicken meat raw"),
    ("варёный рис", "white rice raw"),
    ("оливковое масло", "olive oil"),
    ("banane", "banana"),          # французский
    ("pollo", "chicken meat raw"),  # испанский
    ("鸡肉", "chicken meat raw"),    # китайский
]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Косинусная близость: 1.0 — одинаковый смысл, 0.0 — никак не связаны."""
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> None:
    emb = get_embeddings()

    print("Считаю векторы кандидатов...")
    cand_vectors = np.array(emb.embed_documents(CANDIDATES))
    print(f"РАЗМЕРНОСТЬ ВЕКТОРА: {cand_vectors.shape[1]}\n")

    hits = 0
    for query, expected in CASES:
        q_vector = np.array(emb.embed_query(query))
        scores = [(name, cosine(q_vector, vec))
                  for name, vec in zip(CANDIDATES, cand_vectors)]
        scores.sort(key=lambda pair: pair[1], reverse=True)

        top_name, top_score = scores[0]
        ok = top_name == expected
        hits += ok

        mark = "OK " if ok else "MISS"
        print(f"[{mark}] «{query}»")
        for name, score in scores[:3]:
            arrow = " <-- ожидался" if name == expected else ""
            print(f"        {score:.3f}  {name}{arrow}")
        print()

    print(f"ИТОГ: {hits} из {len(CASES)} запросов нашли нужный продукт первым")


if __name__ == "__main__":
    main()