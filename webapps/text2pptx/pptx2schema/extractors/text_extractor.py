from __future__ import annotations

from typing import Any, List, Optional

from webapps.text2pptx.pptx2schema.models.raw import (
    ColorSpec,
    ParagraphStyle,
    RunStyle,
    TextParagraph,
    TextRun,
    TextFrameSpec,
)


def _safe_font_size(font: Any) -> Optional[float]:
    try:
        if getattr(font, "size", None) is None:
            return None
        return float(font.size.pt)
    except Exception:
        return None


def _extract_run_color(font: Any) -> Optional[ColorSpec]:
    try:
        color = getattr(font, "color", None)
        if color is None:
            return None
        rgb = str(getattr(color, "rgb", "") or "") or None
        theme = str(getattr(getattr(color, "theme_color", None), "name", "") or "") or None
        brightness = getattr(color, "brightness", None)
        if rgb is None and theme is None and brightness is None:
            return None
        return ColorSpec(rgb=rgb, theme_color=theme, brightness=brightness)
    except Exception:
        return None


def _extract_run_style(run: Any) -> RunStyle:
    font = getattr(run, "font", None)
    if font is None:
        return RunStyle()
    hyperlink = None
    try:
        address = getattr(getattr(run, "hyperlink", None), "address", None)
        hyperlink = str(address).strip() if address else None
    except Exception:
        hyperlink = None
    return RunStyle(
        font_family=str(getattr(font, "name", "") or "") or None,
        font_size=_safe_font_size(font),
        bold=getattr(font, "bold", None),
        italic=getattr(font, "italic", None),
        underline=getattr(font, "underline", None),
        color=_extract_run_color(font),
        hyperlink=hyperlink,
    )


def _extract_paragraph_style(paragraph: Any) -> ParagraphStyle:
    align = getattr(getattr(paragraph, "alignment", None), "name", None)
    return ParagraphStyle(
        alignment=str(align) if align else None,
        level=getattr(paragraph, "level", None),
        bullet=None,
        bullet_type=None,
        line_spacing=getattr(paragraph, "line_spacing", None),
        space_before=getattr(paragraph, "space_before", None),
        space_after=getattr(paragraph, "space_after", None),
    )


def extract_text_frame(text_frame: Any) -> TextFrameSpec:
    paragraphs: List[TextParagraph] = []
    for para in getattr(text_frame, "paragraphs", []):
        runs: List[TextRun] = []
        for run in getattr(para, "runs", []):
            runs.append(TextRun(text=str(getattr(run, "text", "") or ""), style=_extract_run_style(run)))
        paragraphs.append(
            TextParagraph(
                text=str(getattr(para, "text", "") or ""),
                style=_extract_paragraph_style(para),
                runs=runs,
            )
        )
    return TextFrameSpec(
        vertical_anchor=str(getattr(getattr(text_frame, "vertical_anchor", None), "name", "") or "") or None,
        word_wrap=getattr(text_frame, "word_wrap", None),
        auto_size=str(getattr(getattr(text_frame, "auto_size", None), "name", "") or "") or None,
        margin_left=float(getattr(text_frame, "margin_left", 0) or 0) if getattr(text_frame, "margin_left", None) is not None else None,
        margin_right=float(getattr(text_frame, "margin_right", 0) or 0) if getattr(text_frame, "margin_right", None) is not None else None,
        margin_top=float(getattr(text_frame, "margin_top", 0) or 0) if getattr(text_frame, "margin_top", None) is not None else None,
        margin_bottom=float(getattr(text_frame, "margin_bottom", 0) or 0) if getattr(text_frame, "margin_bottom", None) is not None else None,
        paragraphs=paragraphs,
    )
