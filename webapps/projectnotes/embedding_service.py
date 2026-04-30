from __future__ import annotations

import math
from typing import List

from webapps.llm.llm_factory import get_embedding_model


def mock_embedding(text: str, dim: int = 1536) -> List[float]:
    """
    Deterministic placeholder embedding.

    Phase 3 should replace this adapter with the real AI_TOOLS embedding provider.
    Keeping it isolated prevents view code from owning embedding behavior.
    """
    vec = [0.0] * dim
    words = (text or "").split()
    if not words:
        words = ["empty"]
    for w in words:
        idx = abs(hash(w)) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-9:
        return vec
    return [x / norm for x in vec]


def get_embedding(text: str) -> List[float]:
    """
    Get real embedding for the text using configured provider.
    Automatically pads or truncates to 1536 dimensions to match the DB schema.
    """
    if not text or not text.strip():
        text = "empty"
    embedder = get_embedding_model()
    vec = embedder.embed_query(text)
    
    target_dim = 1536
    current_dim = len(vec)
    
    if current_dim < target_dim:
        vec.extend([0.0] * (target_dim - current_dim))
    elif current_dim > target_dim:
        vec = vec[:target_dim]
        # Renormalize if truncated
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            vec = [x / norm for x in vec]
            
    return vec

