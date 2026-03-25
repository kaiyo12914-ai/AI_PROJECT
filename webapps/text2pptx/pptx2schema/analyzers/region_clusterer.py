from __future__ import annotations

from typing import List

from webapps.text2pptx.pptx2schema.models.raw import SlideRaw
from webapps.text2pptx.pptx2schema.models.template import LayoutTemplate, RegionSpec


def layout_regions_from_slide(slide: SlideRaw, *, layout_type: str) -> LayoutTemplate:
    title_region = None
    body_regions: List[RegionSpec] = []
    for shape in slide.shapes:
        bbox = RegionSpec(x=shape.bbox.x, y=shape.bbox.y, w=shape.bbox.w, h=shape.bbox.h)
        ptype = str(shape.placeholder_type or "")
        if title_region is None and "TITLE" in ptype:
            title_region = bbox
            continue
        if "BODY" in ptype or "CONTENT" in ptype:
            body_regions.append(bbox)
    return LayoutTemplate(layout_type=layout_type, title_region=title_region, body_regions=body_regions)
