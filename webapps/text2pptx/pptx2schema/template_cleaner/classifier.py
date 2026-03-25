from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .models import CleanStrategy, CleanerConfig, ShapeCategory


@dataclass
class ObservedShape:
    is_placeholder: bool
    has_text: bool
    is_picture: bool
    repeated_count: int
    area_ratio: float
    y_ratio: float
    shape_type: str


DECORATIVE_TYPES = {
    "AUTO_SHAPE",
    "FREEFORM",
    "LINE",
    "CONNECTOR",
    "TEXT_BOX",
}


def classify_shape(
    observed: ObservedShape,
    *,
    config: CleanerConfig,
) -> Tuple[ShapeCategory, CleanStrategy, List[str]]:
    reasons: List[str] = []

    if observed.is_placeholder:
        reasons.append("placeholder_keep_structure")
        return "structural", "clear_text_keep_shape", reasons

    if observed.is_picture:
        if (
            observed.repeated_count >= config.repeat_as_template_min_count
            and observed.area_ratio >= config.brand_background_min_area_ratio
        ):
            reasons.append("repeated_large_picture_brand_background")
            return "decorative", "keep_all", reasons
        reasons.append("picture_default_remove")
        return "content", "remove_shape", reasons

    footer_like = observed.y_ratio >= config.footer_y_min_ratio and observed.area_ratio <= config.footer_max_area_ratio
    if observed.has_text:
        if observed.repeated_count >= config.repeat_as_template_min_count and footer_like:
            reasons.append("repeated_footer_like_text")
            return "structural", "clear_text_keep_shape", reasons
        if observed.repeated_count >= config.repeat_as_template_min_count and observed.area_ratio <= 0.35:
            reasons.append("repeated_text_candidate")
            return "ambiguous", "clear_text_keep_shape", reasons
        reasons.append("single_or_large_text_content")
        return "content", "remove_shape", reasons

    if observed.repeated_count >= config.repeat_as_template_min_count:
        reasons.append("repeated_non_text_shape")
        return "decorative", "keep_all", reasons

    if observed.shape_type in DECORATIVE_TYPES and observed.area_ratio <= 0.25:
        reasons.append("small_decorative_shape")
        return "decorative", "keep_all", reasons

    reasons.append("non_placeholder_unknown")
    return "ambiguous", "clear_text_keep_shape", reasons

