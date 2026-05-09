"""Ленивая загрузка sentence-transformers и кодирование текстов в эмбеддинги."""
from functools import lru_cache

import numpy as np

MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def encode_texts(texts: list[str]) -> np.ndarray:
    """Возвращает матрицу (n, dim) L2-нормированных эмбеддингов."""
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return np.zeros((0, 384), dtype=np.float64)
    model = _model()
    vectors = model.encode(
        cleaned,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float64)


def encode_text(text: str) -> np.ndarray:
    """Один вектор формы (dim,)."""
    matrix = encode_texts([text or ''])
    if matrix.size == 0:
        return np.zeros(384, dtype=np.float64)
    return matrix[0]


def to_list(vector: np.ndarray) -> list[float]:
    return [float(x) for x in np.asarray(vector, dtype=np.float64).ravel()]
