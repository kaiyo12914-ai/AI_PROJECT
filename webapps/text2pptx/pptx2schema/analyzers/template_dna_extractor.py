from __future__ import annotations

from typing import Dict, List

from webapps.text2pptx.pptx2schema.analyzers.color_tokenizer import extract_color_tokens
from webapps.text2pptx.pptx2schema.analyzers.region_clusterer import layout_regions_from_slide
from webapps.text2pptx.pptx2schema.analyzers.typography_analyzer import extract_font_tokens
from webapps.text2pptx.pptx2schema.models.raw import PresentationRaw
from webapps.text2pptx.pptx2schema.models.semantic import SlideSemantic
from webapps.text2pptx.pptx2schema.models.template import LayoutTemplate, TemplateDNA


def extract_template_dna(raw: PresentationRaw, semantic_slides: List[SlideSemantic]) -> TemplateDNA:
    font_tokens = extract_font_tokens(raw)
    color_tokens = extract_color_tokens(raw)

    layout_map: Dict[str, LayoutTemplate] = {}
    semantic_by_idx = {s.slide_index: s for s in semantic_slides}
    for slide in raw.slides:
        semantic = semantic_by_idx.get(slide.slide_index)
        if semantic is None:
            continue
        layout_type = semantic.layout_type
        if layout_type in layout_map:
            continue
        layout_map[layout_type] = layout_regions_from_slide(slide, layout_type=layout_type)

    preferred = [x.layout_type for x in semantic_slides]
    return TemplateDNA(
        font_tokens=font_tokens,
        color_tokens=color_tokens,
        layouts=list(layout_map.values()),
        preferred_layouts=preferred,
    )
