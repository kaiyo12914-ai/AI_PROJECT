from __future__ import annotations

from typing import Any, Optional

from webapps.text2pptx.pptx2schema.models.raw import (
    BBox,
    ColorSpec,
    FillSpec,
    LineSpec,
    ShapeSpec,
)
from webapps.text2pptx.pptx2schema.extractors.text_extractor import extract_text_frame


def _shape_bbox(shape: Any) -> BBox:
    return BBox(
        x=float(getattr(shape, "left", 0) or 0),
        y=float(getattr(shape, "top", 0) or 0),
        w=float(getattr(shape, "width", 0) or 0),
        h=float(getattr(shape, "height", 0) or 0),
    )


def _extract_color(color_obj: Any) -> Optional[ColorSpec]:
    if color_obj is None:
        return None
    try:
        rgb = str(getattr(color_obj, "rgb", "") or "") or None
        theme = str(getattr(getattr(color_obj, "theme_color", None), "name", "") or "") or None
        bright = getattr(color_obj, "brightness", None)
        if rgb is None and theme is None and bright is None:
            return None
        return ColorSpec(rgb=rgb, theme_color=theme, brightness=bright)
    except Exception:
        return None


def _extract_fill(shape: Any) -> Optional[FillSpec]:
    try:
        fill = getattr(shape, "fill", None)
        if fill is None:
            return None
        fill_type = str(getattr(getattr(fill, "type", None), "name", "") or "") or None
        color = _extract_color(getattr(getattr(fill, "fore_color", None), "_color", getattr(fill, "fore_color", None)))
        if fill_type is None and color is None:
            return None
        return FillSpec(type=fill_type, color=color)
    except Exception:
        return None


def _extract_line(shape: Any) -> Optional[LineSpec]:
    try:
        line = getattr(shape, "line", None)
        if line is None:
            return None
        color = _extract_color(getattr(line, "color", None))
        width = float(getattr(line, "width", 0) or 0) if getattr(line, "width", None) is not None else None
        if color is None and width is None:
            return None
        return LineSpec(color=color, width=width)
    except Exception:
        return None


def extract_shape(shape: Any, *, z_index: int) -> ShapeSpec:
    shape_type = str(getattr(getattr(shape, "shape_type", None), "name", "") or "OTHER")
    placeholder_type = None
    try:
        if getattr(shape, "is_placeholder", False):
            placeholder_type = str(getattr(shape.placeholder_format.type, "name", "") or "") or None
    except Exception:
        placeholder_type = None

    text_frame = None
    if getattr(shape, "has_text_frame", False):
        try:
            text_frame = extract_text_frame(shape.text_frame)
        except Exception:
            text_frame = None

    return ShapeSpec(
        shape_id=str(getattr(shape, "shape_id", "")),
        name=str(getattr(shape, "name", "") or "") or None,
        shape_type=shape_type,
        bbox=_shape_bbox(shape),
        rotation=float(getattr(shape, "rotation", 0) or 0) if getattr(shape, "rotation", None) is not None else None,
        z_index=z_index,
        placeholder_type=placeholder_type,
        is_group=(shape_type == "GROUP"),
        fill=_extract_fill(shape),
        line=_extract_line(shape),
        text_frame=text_frame,
    )
