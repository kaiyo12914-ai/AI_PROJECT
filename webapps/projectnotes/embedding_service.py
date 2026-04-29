from __future__ import annotations

import math
from typing import List


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

