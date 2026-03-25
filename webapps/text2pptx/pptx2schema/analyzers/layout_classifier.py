from __future__ import annotations

from webapps.text2pptx.pptx2schema.models.raw import SlideRaw
from webapps.text2pptx.pptx2schema.types.enums import SlideLayoutType


def classify_layout(slide: SlideRaw) -> tuple[str, float]:
    placeholder_types = [str(s.placeholder_type or "") for s in slide.shapes]
    has_title = any("TITLE" in p for p in placeholder_types)
    body_count = sum(1 for p in placeholder_types if "BODY" in p or "CONTENT" in p)

    if slide.slide_index == 1 and has_title and body_count <= 1:
        return SlideLayoutType.COVER.value, 0.9
    if has_title and body_count >= 2:
        return SlideLayoutType.TWO_CONTENT.value, 0.8
    if has_title and body_count == 1:
        return SlideLayoutType.CONTENT.value, 0.75
    if has_title and body_count == 0:
        return SlideLayoutType.SECTION.value, 0.7
    return SlideLayoutType.CONTENT.value, 0.5
