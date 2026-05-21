from functools import lru_cache

from django.conf import settings
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_embedding_model():
    return SentenceTransformer(settings.DIGITAL_TWIN_KB_EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    vector = get_embedding_model().encode(text or "", normalize_embeddings=True)
    return vector.astype(float).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = get_embedding_model().encode(texts, normalize_embeddings=True)
    return [v.astype(float).tolist() for v in vectors]
