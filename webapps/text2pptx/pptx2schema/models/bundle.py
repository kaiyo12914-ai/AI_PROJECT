from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .raw import PresentationRaw
from .semantic import SlideSemantic
from .template import TemplateDNA


class PresentationBundle(BaseModel):
    raw: PresentationRaw
    semantic_slides: List[SlideSemantic] = Field(default_factory=list)
    template_dna: TemplateDNA = Field(default_factory=TemplateDNA)
