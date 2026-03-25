from __future__ import annotations

from typing import Dict


def rough_similarity_score(*, base_slide_count: int, candidate_slide_count: int) -> Dict[str, float]:
    if base_slide_count <= 0:
        return {"slide_count_ratio": 0.0, "overall": 0.0}
    ratio = min(base_slide_count, candidate_slide_count) / max(base_slide_count, candidate_slide_count)
    return {"slide_count_ratio": ratio, "overall": ratio}
