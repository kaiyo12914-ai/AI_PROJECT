from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SlideRoleContent(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    body: List[str] = Field(default_factory=list)
    captions: List[str] = Field(default_factory=list)
    callouts: List[str] = Field(default_factory=list)


class SemanticBlock(BaseModel):
    shape_id: str
    role: str
    text: Optional[str] = None
    bbox_ref: Optional[str] = None


class SlideSemantic(BaseModel):
    slide_index: int
    layout_type: str
    confidence: float
    roles: SlideRoleContent = Field(default_factory=SlideRoleContent)
    blocks: List[SemanticBlock] = Field(default_factory=list)
