from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from webapps.text2pptx.pptx2schema.extractors.shape_extractor import extract_shape


def _safe_name(obj: Any, fallback: str) -> str:
    text = str(getattr(obj, "name", "") or "").strip()
    return text or fallback


def extract_template_structure(prs: Any, keep_layout_parts: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    Extract slide-master / slide-layout structure with textbox formatting preserved.

    The returned payload is JSON-serializable and keeps shape geometry and text
    frame styles so downstream rendering can reconstruct relative position and
    typography more faithfully.
    """

    masters: List[Dict[str, Any]] = []
    layout_seq = 1
    for master_index, master in enumerate(getattr(prs, "slide_masters", []), start=1):
        layouts: List[Dict[str, Any]] = []
        for layout_index, layout in enumerate(getattr(master, "slide_layouts", []), start=1):
            try:
                partname = str(getattr(layout.part, "partname", "") or "").strip().lstrip("/")
            except Exception:
                partname = ""
            if keep_layout_parts is not None and (not partname or partname not in keep_layout_parts):
                continue
            shapes = []
            for shape_index, shape in enumerate(getattr(layout, "shapes", [])):
                try:
                    shapes.append(extract_shape(shape, z_index=shape_index).model_dump())
                except Exception:
                    continue
            display_name = f"版型{layout_seq}"
            layout_seq += 1
            layouts.append(
                {
                    "layout_index": layout_index,
                    "name": display_name,
                    "source_name": _safe_name(layout, f"layout_{layout_index}"),
                    "partname": partname,
                    "shape_count": len(shapes),
                    "shapes": shapes,
                }
            )

        if layouts or keep_layout_parts is None:
            masters.append(
                {
                    "master_index": master_index,
                    "name": _safe_name(master, f"master_{master_index}"),
                    "layout_count": len(layouts),
                    "layouts": layouts,
                }
            )

    return {"slide_masters": masters}
