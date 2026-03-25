from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from webapps.text2pptx.pptx2schema.models.raw import BBox
from webapps.text2pptx.pptx2schema.models.template import FontToken

ShapeCategory = Literal["structural", "decorative", "content", "ambiguous"]
CleanStrategy = Literal["keep_all", "clear_text_keep_shape", "remove_shape"]


class CleanerConfig(BaseModel):
    repeat_position_round_digits: int = 2
    repeat_as_template_min_count: int = 2
    brand_background_min_area_ratio: float = 0.35
    footer_y_min_ratio: float = 0.82
    footer_max_area_ratio: float = 0.20


class PlaceholderAsset(BaseModel):
    placeholder_type: Optional[str] = None
    placeholder_idx: Optional[int] = None
    bbox: BBox


class LayoutAsset(BaseModel):
    master_name: str
    layout_name: str
    layout_type: str
    placeholders: List[PlaceholderAsset] = Field(default_factory=list)
    title_regions: List[BBox] = Field(default_factory=list)
    body_regions: List[BBox] = Field(default_factory=list)
    caption_regions: List[BBox] = Field(default_factory=list)


class MasterAsset(BaseModel):
    master_name: str
    layout_names: List[str] = Field(default_factory=list)


class ThemeAssets(BaseModel):
    theme_part: Optional[str] = None
    font_scheme: Dict[str, str] = Field(default_factory=dict)
    color_scheme: Dict[str, str] = Field(default_factory=dict)


class ShapeDecision(BaseModel):
    slide_index: int
    shape_id: str
    name: Optional[str] = None
    shape_type: str
    placeholder_type: Optional[str] = None
    bbox: BBox
    has_text: bool = False
    is_picture: bool = False
    repeated_count: int = 1
    category: ShapeCategory
    strategy: CleanStrategy
    reasons: List[str] = Field(default_factory=list)


class KeepRemovePolicySummary(BaseModel):
    total_shapes: int = 0
    kept_shapes: int = 0
    cleared_text_shapes: int = 0
    removed_shapes: int = 0
    by_category: Dict[str, int] = Field(default_factory=dict)
    by_strategy: Dict[str, int] = Field(default_factory=dict)


class TemplateCleanerSchema(BaseModel):
    source_file: Optional[str] = None
    cleaned_template_file: str
    extracted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    theme: ThemeAssets = Field(default_factory=ThemeAssets)
    slide_masters: List[MasterAsset] = Field(default_factory=list)
    layouts: List[LayoutAsset] = Field(default_factory=list)
    font_tokens: Dict[str, FontToken] = Field(default_factory=dict)
    color_tokens: Dict[str, str] = Field(default_factory=dict)
    spacing_rules: Dict[str, float] = Field(default_factory=dict)
    keep_remove_policy_summary: KeepRemovePolicySummary = Field(default_factory=KeepRemovePolicySummary)
    shape_decisions: List[ShapeDecision] = Field(default_factory=list)

