from __future__ import annotations

from typing import Dict

from webapps.text2pptx.pptx2schema.models.raw import PresentationRaw
from webapps.text2pptx.pptx2schema.models.template import FontToken


def extract_font_tokens(raw: PresentationRaw) -> Dict[str, FontToken]:
    tokens: Dict[str, FontToken] = {}
    for slide in raw.slides:
        for shape in slide.shapes:
            tf = shape.text_frame
            if tf is None:
                continue
            for para in tf.paragraphs:
                for run in para.runs:
                    style = run.style
                    family = style.font_family
                    if not family:
                        continue
                    if family in tokens:
                        continue
                    tokens[family] = FontToken(
                        family=family,
                        size=style.font_size,
                        bold=style.bold,
                        italic=style.italic,
                        color=(style.color.rgb if style.color else None),
                    )
    return tokens
