from __future__ import annotations

from typing import Dict

from webapps.text2pptx.pptx2schema.models.raw import PresentationRaw


def extract_color_tokens(raw: PresentationRaw) -> Dict[str, str]:
    out: Dict[str, str] = {}
    idx = 1
    for slide in raw.slides:
        for shape in slide.shapes:
            if shape.fill and shape.fill.color and shape.fill.color.rgb:
                rgb = shape.fill.color.rgb
                if rgb not in out.values():
                    out[f"shape_fill_{idx}"] = rgb
                    idx += 1
            if shape.line and shape.line.color and shape.line.color.rgb:
                rgb = shape.line.color.rgb
                if rgb not in out.values():
                    out[f"shape_line_{idx}"] = rgb
                    idx += 1
    return out
