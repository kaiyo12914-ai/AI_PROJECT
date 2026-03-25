from __future__ import annotations

from enum import Enum


class SlideLayoutType(str, Enum):
    COVER = "cover"
    SECTION = "section"
    CONTENT = "content"
    TWO_CONTENT = "two_content"
    COMPARISON = "comparison"


class ShapeKind(str, Enum):
    AUTO_SHAPE = "AUTO_SHAPE"
    PLACEHOLDER = "PLACEHOLDER"
    TEXT_BOX = "TEXT_BOX"
    PICTURE = "PICTURE"
    TABLE = "TABLE"
    GROUP = "GROUP"
    OTHER = "OTHER"
