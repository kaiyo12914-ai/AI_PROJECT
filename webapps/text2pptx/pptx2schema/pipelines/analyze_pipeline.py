from __future__ import annotations

from pathlib import Path
from typing import List

from webapps.text2pptx.pptx2schema.analyzers.layout_classifier import classify_layout
from webapps.text2pptx.pptx2schema.analyzers.template_dna_extractor import extract_template_dna
from webapps.text2pptx.pptx2schema.models.bundle import PresentationBundle
from webapps.text2pptx.pptx2schema.models.semantic import SemanticBlock, SlideRoleContent, SlideSemantic
from webapps.text2pptx.pptx2schema.pipelines.extract_pipeline import run_extract


def _build_semantic_slides(raw) -> List[SlideSemantic]:
    out: List[SlideSemantic] = []
    for slide in raw.slides:
        layout_type, conf = classify_layout(slide)
        body_text: List[str] = []
        blocks: List[SemanticBlock] = []
        for shp in slide.shapes:
            if not shp.text_frame:
                continue
            plain = "\n".join([p.text for p in shp.text_frame.paragraphs if p.text.strip()]).strip()
            if not plain:
                continue
            blocks.append(SemanticBlock(shape_id=shp.shape_id, role="body", text=plain))
            body_text.append(plain)
        out.append(
            SlideSemantic(
                slide_index=slide.slide_index,
                layout_type=layout_type,
                confidence=conf,
                roles=SlideRoleContent(title=slide.title_text, body=body_text),
                blocks=blocks,
            )
        )
    return out


def run_analyze(input_path: str | Path) -> PresentationBundle:
    raw = run_extract(input_path, source_file=str(input_path))
    semantic = _build_semantic_slides(raw)
    dna = extract_template_dna(raw, semantic)
    return PresentationBundle(raw=raw, semantic_slides=semantic, template_dna=dna)
