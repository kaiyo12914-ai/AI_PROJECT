from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class ColorSpec(BaseModel):
    rgb: Optional[str] = None
    theme_color: Optional[str] = None
    brightness: Optional[float] = None


class RunStyle(BaseModel):
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    color: Optional[ColorSpec] = None
    hyperlink: Optional[str] = None


class TextRun(BaseModel):
    text: str
    style: RunStyle = Field(default_factory=RunStyle)


class ParagraphStyle(BaseModel):
    alignment: Optional[str] = None
    level: Optional[int] = None
    bullet: Optional[bool] = None
    bullet_type: Optional[str] = None
    line_spacing: Optional[float] = None
    space_before: Optional[float] = None
    space_after: Optional[float] = None


class TextParagraph(BaseModel):
    text: str
    style: ParagraphStyle = Field(default_factory=ParagraphStyle)
    runs: List[TextRun] = Field(default_factory=list)


class TextFrameSpec(BaseModel):
    vertical_anchor: Optional[str] = None
    word_wrap: Optional[bool] = None
    auto_size: Optional[str] = None
    margin_left: Optional[float] = None
    margin_right: Optional[float] = None
    margin_top: Optional[float] = None
    margin_bottom: Optional[float] = None
    paragraphs: List[TextParagraph] = Field(default_factory=list)


class FillSpec(BaseModel):
    type: Optional[str] = None
    color: Optional[ColorSpec] = None


class LineSpec(BaseModel):
    color: Optional[ColorSpec] = None
    width: Optional[float] = None


class ShapeSpec(BaseModel):
    shape_id: str
    name: Optional[str] = None
    shape_type: str
    bbox: BBox
    rotation: Optional[float] = None
    z_index: Optional[int] = None
    placeholder_type: Optional[str] = None
    is_group: bool = False
    fill: Optional[FillSpec] = None
    line: Optional[LineSpec] = None
    text_frame: Optional[TextFrameSpec] = None


class SlideBackground(BaseModel):
    fill: Optional[FillSpec] = None


class SlideRaw(BaseModel):
    slide_index: int
    title_text: Optional[str] = None
    background: Optional[SlideBackground] = None
    shapes: List[ShapeSpec] = Field(default_factory=list)
    notes_text: Optional[str] = None


class ThemeFontScheme(BaseModel):
    major_latin: Optional[str] = None
    minor_latin: Optional[str] = None


class ThemeColorScheme(BaseModel):
    dk1: Optional[str] = None
    lt1: Optional[str] = None
    dk2: Optional[str] = None
    lt2: Optional[str] = None
    accent1: Optional[str] = None
    accent2: Optional[str] = None
    accent3: Optional[str] = None
    accent4: Optional[str] = None
    accent5: Optional[str] = None
    accent6: Optional[str] = None
    hlink: Optional[str] = None
    fol_hlink: Optional[str] = None


class PresentationMeta(BaseModel):
    source_file: Optional[str] = None
    slide_width: float
    slide_height: float
    slide_count: int


class ThemeSpec(BaseModel):
    font_scheme: ThemeFontScheme = Field(default_factory=ThemeFontScheme)
    color_scheme: ThemeColorScheme = Field(default_factory=ThemeColorScheme)


class PresentationRaw(BaseModel):
    meta: PresentationMeta
    theme: ThemeSpec = Field(default_factory=ThemeSpec)
    slides: List[SlideRaw] = Field(default_factory=list)
