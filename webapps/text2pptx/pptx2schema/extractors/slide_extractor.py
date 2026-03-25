from __future__ import annotations

from typing import Any, List

from webapps.text2pptx.pptx2schema.extractors.shape_extractor import extract_shape
from webapps.text2pptx.pptx2schema.models.raw import SlideRaw


def _extract_notes_text(slide: Any) -> str | None:
    try:
        notes_slide = getattr(slide, "notes_slide", None)
        if notes_slide is None:
            return None
        text = str(getattr(notes_slide.notes_text_frame, "text", "") or "").strip()
        return text or None
    except Exception:
        return None


def _extract_title_text(slide: Any) -> str | None:
    try:
        title_shape = slide.shapes.title
        if title_shape is None:
            return None
        text = str(getattr(title_shape, "text", "") or "").strip()
        return text or None
    except Exception:
        return None


def extract_slide(slide: Any, *, slide_index: int) -> SlideRaw:
    shapes: List[Any] = list(getattr(slide, "shapes", []))
    shape_specs = [extract_shape(shape, z_index=i) for i, shape in enumerate(shapes)]
    return SlideRaw(
        slide_index=slide_index,
        title_text=_extract_title_text(slide),
        shapes=shape_specs,
        notes_text=_extract_notes_text(slide),
    )
