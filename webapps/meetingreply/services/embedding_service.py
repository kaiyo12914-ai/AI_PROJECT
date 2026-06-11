from __future__ import annotations

import math
import requests

from django.conf import settings
from webapps.llm.embedding_factory import (
    get_shared_embedding_base_url,
    get_shared_embedding_model,
    get_shared_embedding_model_name,
)


def embedding_enabled() -> bool:
    return bool(getattr(settings, "MEETINGREPLY_ENABLE_EMBEDDING", True))


def expected_dimension() -> int:
    return int(getattr(settings, "MEETINGREPLY_EMBEDDING_DIMENSION", 1024) or 1024)


def embedding_model_name() -> str:
    return str(
        getattr(settings, "MEETINGREPLY_EMBEDDING_MODEL", get_shared_embedding_model_name())
        or get_shared_embedding_model_name()
    )


def get_embedding_model():
    if not embedding_enabled():
        return None
    return get_shared_embedding_model()


def _ollama_http_embed(texts: list[str]) -> list[list[float]]:
    base_url = get_shared_embedding_base_url().rstrip("/")
    payload = {
        "model": embedding_model_name(),
        "input": texts,
    }
    response = requests.post(f"{base_url}/api/embed", json=payload, timeout=120)
    response.raise_for_status()
    data = response.json() if response.content else {}
    vectors = data.get("embeddings") or []
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise RuntimeError("ollama_embed_invalid_response")
    return [_sanitize_vector(v) for v in vectors]


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


def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    if model is None:
        return [0.0] * expected_dimension()
    try:
        vector = model.embed_query(text or "")
        return _sanitize_vector(vector)
    except Exception:
        return _ollama_http_embed([text or ""])[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    if model is None:
        zero = [0.0] * expected_dimension()
        return [zero.copy() for _ in texts]
    try:
        vectors = model.embed_documents(texts)
        return [_sanitize_vector(v) for v in vectors]
    except Exception:
        return _ollama_http_embed(texts)
