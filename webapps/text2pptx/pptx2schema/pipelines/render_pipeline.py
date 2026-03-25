from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from webapps.text2pptx.pptx2schema.models.bundle import PresentationBundle
from webapps.text2pptx.pptx2schema.renderers.schema_to_pptx import render_bundle_to_pptx


def run_render(schema_path: str, content_path: str, output_path: str) -> None:
    schema_raw = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    content_raw: Dict[str, Any] = json.loads(Path(content_path).read_text(encoding="utf-8"))
    bundle = PresentationBundle.model_validate(schema_raw)
    render_bundle_to_pptx(bundle, content_raw, output_path)
