from functools import lru_cache
import math

from django.conf import settings


def _import_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. "
            "Embedding features are disabled. "
            "Install with: pip install sentence-transformers"
        ) from exc
    return SentenceTransformer


def _zero_vector() -> list[float]:
    return [0.0] * int(getattr(settings, "DIGITAL_TWIN_KB_EMBEDDING_DIMENSIONS", 384))


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
    sentence_transformer_cls = _import_sentence_transformer()
    return sentence_transformer_cls(settings.DIGITAL_TWIN_KB_EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    if model is None:
        return _zero_vector()
    vector = model.encode(text or "", normalize_embeddings=True)
    return _sanitize_vector(vector.astype(float).tolist())


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    if model is None:
        zv = _zero_vector()
        return [zv.copy() for _ in texts]
    vectors = model.encode(texts, normalize_embeddings=True)
    return [_sanitize_vector(v.astype(float).tolist()) for v in vectors]
