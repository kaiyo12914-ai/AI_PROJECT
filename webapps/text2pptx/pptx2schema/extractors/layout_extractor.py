from __future__ import annotations

from typing import Any, Dict, List


def extract_layout_links(presentation: Any) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    for idx, slide in enumerate(getattr(presentation, "slides", []), start=1):
        layout_name = ""
        try:
            layout_name = str(getattr(getattr(slide, "slide_layout", None), "name", "") or "")
        except Exception:
            layout_name = ""
        links.append(
            {
                "slide_index": str(idx),
                "layout_name": layout_name,
            }
        )
    return links
