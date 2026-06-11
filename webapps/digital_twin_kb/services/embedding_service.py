from functools import lru_cache
import math

from django.conf import settings
from webapps.llm.embedding_factory import get_shared_embedding_model


def _zero_vector() -> list[float]:
    return [0.0] * int(getattr(settings, "DIGITAL_TWIN_KB_EMBEDDING_DIMENSIONS", 1024))


def _sanitize_vector(values) -> list[float]:
    cleaned: list[float] = []
    for v in values:
        try:
            f = float(v)
        except Exception:
            f = 0.0
        if not math.isfinite(f):
            f = 0.0
        cleaned.append(f)
    return cleaned


@lru_cache(maxsize=1)
def get_embedding_model():
    if not bool(getattr(settings, "DIGITAL_TWIN_KB_ENABLE_EMBEDDING", True)):
        return None
    return get_shared_embedding_model()


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    if model is None:
        return _zero_vector()
    vector = model.embed_query(text or "")
    return _sanitize_vector(vector)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    if model is None:
        zv = _zero_vector()
        return [zv.copy() for _ in texts]
    vectors = model.embed_documents(texts)
    return [_sanitize_vector(v) for v in vectors]
