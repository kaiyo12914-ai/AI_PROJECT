from __future__ import annotations

from pathlib import Path
from typing import Union

from webapps.text2pptx.pptx2schema.extractors.pptx_reader import InputLike, load_presentation
from webapps.text2pptx.pptx2schema.extractors.slide_extractor import extract_slide
from webapps.text2pptx.pptx2schema.extractors.theme_extractor import extract_theme_from_presentation
from webapps.text2pptx.pptx2schema.models.raw import PresentationMeta, PresentationRaw


def run_extract(input_data: InputLike, *, source_file: str | None = None) -> PresentationRaw:
    prs = load_presentation(input_data)
    slides = [extract_slide(slide, slide_index=i) for i, slide in enumerate(prs.slides, start=1)]
    meta = PresentationMeta(
        source_file=source_file or (str(input_data) if isinstance(input_data, (str, Path)) else None),
        slide_width=float(prs.slide_width),
        slide_height=float(prs.slide_height),
        slide_count=len(prs.slides),
    )
    return PresentationRaw(
        meta=meta,
        theme=extract_theme_from_presentation(prs),
        slides=slides,
    )
