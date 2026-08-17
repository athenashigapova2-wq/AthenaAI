"""Модель эмбеддингов — превращает текст в вектор чисел.

Работает локально, без обращения к внешнему API: у GigaChat эндпоинт
/embeddings не входит в бесплатный тариф (402 Payment Required).

Модель multilingual-e5-small обучена на 100+ языках, поэтому русский
запрос и английское название одного и того же продукта дают близкие
векторы. Это ровно то, что нужно для пяти языков поверх
англоязычного справочника.
"""

from threading import Lock

from langchain_core.embeddings import Embeddings

MODEL_NAME = "intfloat/multilingual-e5-base"
EMBEDDING_DIM = 768


class LocalEmbeddings(Embeddings):
    """Обёртка над sentence-transformers в интерфейсе LangChain."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Векторы для списка текстов, которые кладём в базу."""
        prefixed = [f"passage: {text}" for text in texts]
        vectors = self._model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Вектор для поискового запроса пользователя."""
        vector = self._model.encode(
            f"query: {text}",
            normalize_embeddings=True,
        )
        return vector.tolist()


_embeddings: Embeddings | None = None
_embeddings_lock = Lock()


def get_embeddings() -> Embeddings:
    """Load the model once, even when several worker threads arrive together."""
    global _embeddings
    if _embeddings is None:
        with _embeddings_lock:
            if _embeddings is None:
                _embeddings = LocalEmbeddings()
    return _embeddings
