from __future__ import annotations

from .pptx_reader import load_presentation
from .slide_extractor import extract_slide
from .shape_extractor import extract_shape
from .text_extractor import extract_text_frame
from .theme_extractor import extract_theme_from_presentation

__all__ = [
    "load_presentation",
    "extract_slide",
    "extract_shape",
    "extract_text_frame",
    "extract_theme_from_presentation",
]
