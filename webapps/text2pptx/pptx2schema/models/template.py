from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FontToken(BaseModel):
    family: Optional[str] = None
    size: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    color: Optional[str] = None


class RegionSpec(BaseModel):
    x: float
    y: float
    w: float
    h: float


class LayoutTemplate(BaseModel):
    layout_type: str
    title_region: Optional[RegionSpec] = None
    subtitle_region: Optional[RegionSpec] = None
    body_regions: List[RegionSpec] = Field(default_factory=list)
    caption_regions: List[RegionSpec] = Field(default_factory=list)


class TemplateDNA(BaseModel):
    font_tokens: Dict[str, FontToken] = Field(default_factory=dict)
    color_tokens: Dict[str, str] = Field(default_factory=dict)
    layouts: List[LayoutTemplate] = Field(default_factory=list)
    spacing_rules: Dict[str, float] = Field(default_factory=dict)
    alignment_rules: Dict[str, str] = Field(default_factory=dict)
    preferred_layouts: List[str] = Field(default_factory=list)
