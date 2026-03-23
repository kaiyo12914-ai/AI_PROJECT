from __future__ import annotations

import io
import os
import re
import json
import logging
import platform
import unicodedata
from urllib.parse import quote
from typing import Optional, List, Dict, Any

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect

from webapps.portal.decorators import require_node
from webapps.llm.llm_factory import get_chat_model


# ---------------------------
# Paths / constants
# ---------------------------
BASE_DIR = getattr(settings, "BASE_DIR", None) or os.getcwd()
PPTX_TEMPLATE_DIR = os.path.join(BASE_DIR, "webapps", "text2pptx", "pptx_templates")

MAX_BULLETS_PER_SLIDE = 7
TITLE_FONT_PT = 34
BODY_FONT_PT = 20
SUBTITLE_FONT_PT = 18
MAX_INPUT_CHARS = int(getattr(settings, "TEXT2PPTX_MAX_CHARS", 20000))
MAX_TEMPLATE_UPLOAD_MB = int(getattr(settings, "TEXT2PPTX_TEMPLATE_MAX_MB", 20))
DEFAULT_TEMPLATE_NAME = "預設範本.pptx"
DEFAULT_MAIN_TITLE = "簡報"
DEFAULT_MAIN_SUBTITLE = "文字內容自動生成簡報"
VALID_SLIDE_TYPES = {"content", "section", "two_content", "comparison"}
MARKER_TO_SLIDE_TYPE = {
    "cover": "cover",
    "section": "section",
    "content": "content",
    "two_content": "two_content",
    "comparison": "comparison",
    "標題投影片": "cover",
    "章節標題": "section",
    "內容頁": "content",
    "雙欄必較頁": "two_content",
}
LAYOUT_NAME_KEYS = {
    "cover": ["title slide", "標題投影片"],
    "content": ["title and content", "內容頁"],
    "section": ["section header", "章節標題"],
    "two_content": ["two content", "雙欄必較頁"],
}
TITLE_PLACEHOLDER_TYPES = {1, 3}
SUBTITLE_PLACEHOLDER_TYPES = {4}
CONTENT_PLACEHOLDER_TYPES = {2, 7}

logger = logging.getLogger(__name__)


def _select_font_names() -> tuple[str, str]:
    forced_ea = (getattr(settings, "TEXT2PPTX_FONT_EAST_ASIAN", "") or "").strip()
    forced_ascii = (getattr(settings, "TEXT2PPTX_FONT_ASCII", "") or "").strip()
    if forced_ea and forced_ascii:
        return forced_ea, forced_ascii

    system = platform.system().lower()
    if "windows" in system:
        return forced_ea or "Microsoft JhengHei", forced_ascii or "Times New Roman"
    if "darwin" in system:
        return forced_ea or "PingFang TC", forced_ascii or "Helvetica Neue"
    return forced_ea or "Noto Sans CJK TC", forced_ascii or "DejaVu Sans"


FONT_NAME_EAST_ASIAN, FONT_NAME_ASCII = _select_font_names()


def _placeholder_type_id(ph) -> int | None:
    try:
        return int(ph.placeholder_format.type)
    except Exception:
        return None


def _is_title_placeholder_type(v: int | None) -> bool:
    return v in TITLE_PLACEHOLDER_TYPES


def _is_subtitle_placeholder_type(v: int | None) -> bool:
    return v in SUBTITLE_PLACEHOLDER_TYPES


def _is_content_placeholder_type(v: int | None) -> bool:
    return v in CONTENT_PLACEHOLDER_TYPES


def _list_pptx_templates() -> List[str]:
    if not os.path.isdir(PPTX_TEMPLATE_DIR):
        return []
    files = []
    for fn in os.listdir(PPTX_TEMPLATE_DIR):
        if fn.lower().endswith(".pptx"):
            full = os.path.join(PPTX_TEMPLATE_DIR, fn)
            if os.path.isfile(full):
                files.append(fn)
    files.sort()
    return files


def _normalize_template_name(name: str) -> str:
    return unicodedata.normalize("NFC", str(name or "")).strip()


def _template_name_key(name: str) -> str:
    return _normalize_template_name(name).casefold()


def _list_ignored_template_files() -> List[str]:
    if not os.path.isdir(PPTX_TEMPLATE_DIR):
        return []
    ignored: List[str] = []
    for fn in os.listdir(PPTX_TEMPLATE_DIR):
        full = os.path.join(PPTX_TEMPLATE_DIR, fn)
        if not os.path.isfile(full):
            continue
        lower = fn.lower()
        if lower.endswith(".pptx"):
            continue
        if lower.endswith(".potx") or lower.startswith("~$"):
            ignored.append(fn)
    ignored.sort()
    return ignored


def _safe_select_template(tpl_name: str) -> Optional[str]:
    tpl_name = _normalize_template_name(tpl_name)
    if not tpl_name:
        return None
    wanted_key = _template_name_key(tpl_name)
    for fn in _list_pptx_templates():
        if _template_name_key(fn) == wanted_key:
            return os.path.join(PPTX_TEMPLATE_DIR, fn)
    return None


def _pick_layout_adaptive(prs, layout_type: str):
    # PowerPoint 2016 class mapping:
    # comparison and two_content both map to "Two Content（雙欄必較頁）".
    if layout_type == "comparison":
        layout_type = "two_content"

    keys = LAYOUT_NAME_KEYS.get(layout_type, [])
    
    for layout in prs.slide_layouts:
        name = (getattr(layout, "name", "") or "").lower()
        for k in keys:
            if k in name:
                return layout

    if layout_type == "cover":
        return prs.slide_layouts[0]
    
    if layout_type == "content":
        for layout in prs.slide_layouts:
            ph_types = [_placeholder_type_id(p) for p in layout.placeholders]
            has_title = any(_is_title_placeholder_type(t) for t in ph_types)
            has_content = any(_is_content_placeholder_type(t) for t in ph_types)
            if has_title and has_content:
                return layout
        return prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]

    if layout_type in ("two_content", "comparison"):
        for layout in prs.slide_layouts:
            ph_types = [_placeholder_type_id(p) for p in layout.placeholders]
            content_count = sum(1 for t in ph_types if _is_content_placeholder_type(t))
            has_title = any(_is_title_placeholder_type(t) for t in ph_types)
            if has_title and content_count >= 2:
                return layout
        return _pick_layout_adaptive(prs, "content")

    if layout_type == "section":
        return _pick_layout_adaptive(prs, "cover")

    return prs.slide_layouts[0]


def _clear_all_slides(prs):
    """
    Keep masters/layouts from template, but remove existing content slides.
    """
    try:
        sld_id_list = prs.slides._sldIdLst  # pylint: disable=protected-access
        for sld_id in list(sld_id_list):
            r_id = sld_id.rId
            prs.part.drop_rel(r_id)
            sld_id_list.remove(sld_id)
    except Exception as e:
        logger.warning("Failed to clear template slides: %s", e)


def _layout_has_title(layout) -> bool:
    ph_types = [_placeholder_type_id(p) for p in layout.placeholders]
    return any(_is_title_placeholder_type(t) for t in ph_types)


def _layout_content_count(layout) -> int:
    ph_types = [_placeholder_type_id(p) for p in layout.placeholders]
    return sum(1 for t in ph_types if _is_content_placeholder_type(t))


def _layout_has_subtitle_or_textbox(layout) -> bool:
    ph_types = [_placeholder_type_id(p) for p in layout.placeholders]
    if any(_is_subtitle_placeholder_type(t) for t in ph_types):
        return True
    if any(_is_content_placeholder_type(t) for t in ph_types):
        return True
    for shape in layout.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if getattr(shape, "is_placeholder", False):
            t = _placeholder_type_id(shape)
            if _is_title_placeholder_type(t):
                continue
        return True
    return False


def _validate_layout_for_type(layout, layout_type: str) -> bool:
    if layout_type == "cover":
        return _layout_has_title(layout) and _layout_has_subtitle_or_textbox(layout)
    if layout_type == "content":
        return _layout_has_title(layout) and _layout_content_count(layout) >= 1
    if layout_type in ("two_content", "comparison"):
        return _layout_has_title(layout) and _layout_content_count(layout) >= 2
    if layout_type == "section":
        return _layout_has_title(layout) and _layout_has_subtitle_or_textbox(layout)
    return False


def _find_layout_for_import_validation(prs, layout_type: str):
    # PowerPoint 2016 class mapping:
    # comparison and two_content both map to "Two Content（雙欄必較頁）".
    if layout_type == "comparison":
        layout_type = "two_content"

    keys = LAYOUT_NAME_KEYS.get(layout_type, [])
    for layout in prs.slide_layouts:
        name = (getattr(layout, "name", "") or "").lower()
        if keys and not any(k in name for k in keys):
            continue
        if _validate_layout_for_type(layout, layout_type):
            return layout
    # Fallback: allow non-default localized layout names if structure is valid.
    for layout in prs.slide_layouts:
        if _validate_layout_for_type(layout, layout_type):
            return layout
    return None


def _audit_template_bytes(raw: bytes) -> Dict[str, Any]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(raw))
    # Required layouts follow PowerPoint 2016 default categories only.
    required = ["cover", "section", "content", "two_content"]
    labels = {
        "cover": "標題投影片（Title Slide）",
        "section": "章節標題（Section Header）",
        "content": "內容頁（Title and Content）",
        "two_content": "雙欄必較頁（Two Content）",
    }
    found: Dict[str, str] = {}
    missing: List[str] = []
    for t in required:
        layout = _find_layout_for_import_validation(prs, t)
        if layout is None:
            missing.append(labels[t])
        else:
            found[t] = getattr(layout, "name", "") or "(unnamed)"
    return {"ok": len(missing) == 0, "missing": missing, "found": found}


def _save_template_bytes(filename: str, raw: bytes) -> str:
    os.makedirs(PPTX_TEMPLATE_DIR, exist_ok=True)
    filename = _normalize_template_name(filename)
    base, ext = os.path.splitext(filename)
    base = _safe_filename(base, default="template")
    ext = ext if ext else ".pptx"
    candidate = f"{base}{ext}"
    existing_keys = set()
    for fn in os.listdir(PPTX_TEMPLATE_DIR):
        full = os.path.join(PPTX_TEMPLATE_DIR, fn)
        if os.path.isfile(full):
            existing_keys.add(_template_name_key(fn))
    idx = 1
    while (
        _template_name_key(candidate) in existing_keys
        or os.path.exists(os.path.join(PPTX_TEMPLATE_DIR, candidate))
    ):
        candidate = f"{base}_{idx}{ext}"
        idx += 1
    with open(os.path.join(PPTX_TEMPLATE_DIR, candidate), "wb") as f:
        f.write(raw)
    return candidate


def _find_largest_text_frame(slide, exclude_shape=None):
    best_shape = None
    best_area = -1
    
    for shape in slide.shapes:
        if exclude_shape is not None and shape == exclude_shape:
            continue
        if getattr(shape, "is_placeholder", False):
            if _is_content_placeholder_type(_placeholder_type_id(shape)):
                return shape.text_frame

    for shape in slide.shapes:
        if exclude_shape is not None and shape == exclude_shape:
            continue
        if not getattr(shape, "has_text_frame", False):
            continue
        try:
            area = int(shape.width) * int(shape.height)
        except Exception:
            area = 0
        if area > best_area:
            best_area = area
            best_shape = shape
            
    return best_shape.text_frame if best_shape else None


def _find_title_shape(slide):
    title_shape = slide.shapes.title if slide.shapes.title else None
    if title_shape:
        return title_shape
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        if getattr(shape, "is_placeholder", False) and _is_title_placeholder_type(_placeholder_type_id(shape)):
            return shape
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        name = (getattr(shape, "name", "") or "").lower()
        if "title" in name or "標題" in name:
            return shape
    return None


def _find_subtitle_text_frame(slide, exclude_shape=None):
    for shape in slide.shapes:
        if exclude_shape is not None and shape == exclude_shape:
            continue
        if not getattr(shape, "has_text_frame", False):
            continue
        if getattr(shape, "is_placeholder", False) and _is_subtitle_placeholder_type(_placeholder_type_id(shape)):
            return shape.text_frame
    return _find_largest_text_frame(slide, exclude_shape=exclude_shape)


def _chunk_list(items: List[str], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _resolve_slide_type(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if value in VALID_SLIDE_TYPES:
        return value
    resolved = _resolve_marker(str(raw or "").strip())
    if resolved in VALID_SLIDE_TYPES:
        return resolved
    return "content"


def _resolve_marker(raw_marker: str) -> str | None:
    marker = (raw_marker or "").strip()
    if not marker:
        return None
    lower = marker.lower()
    if lower in MARKER_TO_SLIDE_TYPE:
        return MARKER_TO_SLIDE_TYPE[lower]
    return MARKER_TO_SLIDE_TYPE.get(marker)


def _parse_marked_text_structure(text: str) -> Dict[str, Any] | None:
    blocks = [s.strip() for s in text.split("===") if s.strip()]
    if not blocks:
        return None

    pattern = re.compile(r"^\[(?P<marker>[^\]]+)\]\s*(?P<title>.*)$")
    parsed = []
    has_any_marker = False
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        m = pattern.match(lines[0])
        if m:
            has_any_marker = True
            parsed.append(
                {
                    "marker": m.group("marker").strip(),
                    "title": (m.group("title") or "").strip(),
                    "lines": lines[1:],
                }
            )
        else:
            parsed.append({"marker": "", "title": lines[0], "lines": lines[1:]})

    if not has_any_marker:
        return None

    out = {
        "main_title": DEFAULT_MAIN_TITLE,
        "main_subtitle": DEFAULT_MAIN_SUBTITLE,
        "slides": [],
    }

    for idx, item in enumerate(parsed, start=1):
        marker_type = _resolve_marker(item.get("marker") or "")
        title = (item.get("title") or "").strip() or f"投影片 {idx}"
        lines = item.get("lines") or []

        if marker_type == "cover":
            out["main_title"] = title or DEFAULT_MAIN_TITLE
            if lines:
                out["main_subtitle"] = "｜".join(lines)
            continue

        if marker_type == "two_content":
            lower_title = title.lower()
            if (
                "comparison" in lower_title
                or "compare" in lower_title
                or "比較" in title
                or "對照" in title
            ):
                marker_type = "comparison"

        slide_type = marker_type if marker_type in VALID_SLIDE_TYPES else "content"
        out["slides"].append(
            {
                "title": title,
                "slide_type": slide_type,
                "left_title": "",
                "right_title": "",
                "bullets": [str(x).strip() for x in lines if str(x).strip()],
            }
        )

    if not out["slides"]:
        out = _fallback_from_raw_text(text)
    return out


def _find_content_text_frames(slide, exclude_shape=None) -> List[Any]:
    candidates = []
    for shape in slide.shapes:
        if exclude_shape is not None and shape == exclude_shape:
            continue
        if not getattr(shape, "has_text_frame", False):
            continue
        if getattr(shape, "is_placeholder", False):
            if not _is_content_placeholder_type(_placeholder_type_id(shape)):
                continue
        candidates.append((int(getattr(shape, "left", 0)), int(getattr(shape, "top", 0)), shape.text_frame))
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return [x[2] for x in candidates]
    tf = _find_largest_text_frame(slide, exclude_shape=exclude_shape)
    return [tf] if tf else []


def _fill_bullets(text_frame, items: List[str]):
    text_frame.clear()
    if not items:
        p = text_frame.paragraphs[0] if text_frame.paragraphs else text_frame.add_paragraph()
        p.text = "（無內容）"
        _apply_font_style(p, BODY_FONT_PT)
        return
    for idx, b in enumerate(items):
        p = text_frame.paragraphs[idx] if idx < len(text_frame.paragraphs) else text_frame.add_paragraph()
        p.text = b
        _apply_font_style(p, BODY_FONT_PT)


def _fill_column(text_frame, heading: str, items: List[str]):
    text_frame.clear()
    p0 = text_frame.paragraphs[0] if text_frame.paragraphs else text_frame.add_paragraph()
    p0.text = heading
    _apply_font_style(p0, SUBTITLE_FONT_PT, bold=True)
    if not items:
        p1 = text_frame.add_paragraph()
        p1.text = "（無內容）"
        _apply_font_style(p1, BODY_FONT_PT)
        return
    for item in items:
        p = text_frame.add_paragraph()
        p.text = item
        _apply_font_style(p, BODY_FONT_PT)


def _split_two_columns(slide_data: Dict[str, Any], bullets: List[str], slide_type: str) -> tuple[str, List[str], str, List[str]]:
    left_title = str(slide_data.get("left_title") or "").strip()
    right_title = str(slide_data.get("right_title") or "").strip()
    if not left_title:
        left_title = "重點 A" if slide_type == "comparison" else "欄位 A"
    if not right_title:
        right_title = "重點 B" if slide_type == "comparison" else "欄位 B"

    left_items: List[str] = []
    right_items: List[str] = []
    for idx, b in enumerate(bullets):
        if idx % 2 == 0:
            left_items.append(b)
        else:
            right_items.append(b)
    return left_title, left_items, right_title, right_items


def _apply_font_style(paragraph, size_pt: int, bold: bool = False):
    """
    Apply font style with broad python-pptx compatibility.
    """
    from pptx.util import Pt

    if not paragraph.runs:
        paragraph.add_run()

    for run in paragraph.runs:
        run.font.size = Pt(size_pt)
        run.font.bold = bold
        run.font.name = FONT_NAME_ASCII
        # Some python-pptx builds do not support get_or_add_rFonts(); avoid hard dependency.
        try:
            rPr = run._r.get_or_add_rPr()
            rPr.set("ea", FONT_NAME_EAST_ASIAN)
        except Exception:
            pass


def _safe_filename(name: str, default: str = "slides") -> str:
    name = (name or "").strip() or default
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or default


def _build_download_filename(raw_title: str, fallback: str = DEFAULT_MAIN_TITLE) -> str:
    base = (raw_title or "").strip() or fallback
    if base.lower().endswith(".pptx"):
        base = base[:-5]
    safe_base = _safe_filename(base, default=fallback)
    return f"{safe_base}.pptx"


def _coerce_llm_text_response(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return "\n".join(parts)
    return str(response)


def _extract_json_object(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    start = text.find("{")
    if start < 0:
        raise ValueError("LLM output does not contain JSON object start.")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("LLM output JSON object is incomplete.")


def _fallback_from_raw_text(text: str) -> Dict[str, Any]:
    blocks = [s.strip() for s in text.split("===") if s.strip()]
    if not blocks:
        blocks = [text.strip()]
    slides = []
    for i, block in enumerate(blocks, start=1):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        title = lines[0] if lines else f"投影片 {i}"
        bullets = lines[1:] if len(lines) > 1 else []
        slides.append({"title": title, "slide_type": "content", "bullets": bullets})
    return {
        "main_title": DEFAULT_MAIN_TITLE,
        "main_subtitle": DEFAULT_MAIN_SUBTITLE,
        "slides": slides,
    }


def _normalize_analysis_result(data: Dict[str, Any], *, source_text: str) -> Dict[str, Any]:
    title = str(data.get("main_title") or "").strip() or DEFAULT_MAIN_TITLE
    subtitle = str(data.get("main_subtitle") or "").strip() or DEFAULT_MAIN_SUBTITLE

    raw_slides = data.get("slides")
    if not isinstance(raw_slides, list):
        return _fallback_from_raw_text(source_text)

    slides = []
    for idx, s in enumerate(raw_slides, start=1):
        if not isinstance(s, dict):
            continue
        slide_title = str(s.get("title") or "").strip() or f"投影片 {idx}"
        slide_type = _resolve_slide_type(s.get("slide_type"))
        left_title = str(s.get("left_title") or "").strip()
        right_title = str(s.get("right_title") or "").strip()
        bullets_raw = s.get("bullets")
        bullets: List[str] = []
        if isinstance(bullets_raw, list):
            for b in bullets_raw:
                v = str(b).strip()
                if v:
                    bullets.append(v)
        elif bullets_raw is not None:
            v = str(bullets_raw).strip()
            if v:
                bullets.append(v)
        slides.append(
            {
                "title": slide_title,
                "slide_type": slide_type,
                "left_title": left_title,
                "right_title": right_title,
                "bullets": bullets,
            }
        )

    if not slides:
        return _fallback_from_raw_text(source_text)

    return {
        "main_title": title,
        "main_subtitle": subtitle,
        "slides": slides,
    }


def _analyze_text_with_llm(text: str) -> Dict[str, Any]:
    """
    Uses LLM to analyze raw text and structure it for presentation.
    Returns a dict with 'title', 'subtitle', and 'slides' (list of dicts with 'title', 'bullets').
    """
    llm = get_chat_model()
    prompt = f"""
    你是一個專業的簡報生成助手。請將以下文字內容轉換為結構化的簡報大綱。輸出必須是 JSON 格式。

    規則：
    1. 輸出 JSON 必須包含三個頂層鍵："main_title", "main_subtitle", "slides"。
    2. "main_title"：整份簡報的主要標題。
    3. "main_subtitle"：整份簡報的副標題。
    4. "slides"：一個列表，每個元素代表一張投影片。
    5. 每張投影片（slides 的每個元素）必須包含三個鍵："title"、"slide_type" 和 "bullets"。
    6. "title"：該投影片的標題。
    7. "slide_type"：限定為 "content"、"section"、"two_content"、"comparison" 其中之一。
    8. "bullets"：一個列表，包含該投影片的所有條列要點。如果沒有要點，則為空列表。
    9. 若 slide_type 為 "comparison" 或 "two_content"，可額外提供 "left_title" 與 "right_title"。
    10. 盡可能語義化地拆分內容到不同的投影片，每張投影片的條列要點數量不應超過 {MAX_BULLETS_PER_SLIDE} 點。
    11. 若原文沒有明確主標題，請自動生成一個簡潔相關的標題。
    12. 若原文沒有明確副標題，請使用「文字內容自動生成簡報」作為副標題。

    請分析以下文字內容：

    ```text
    {text}
    ```

    JSON 輸出範例：
    ```json
    {{
      "main_title": "專案進度報告",
      "main_subtitle": "2026年3月更新",
      "slides": [
        {{
          "title": "第一張：專案概述",
          "slide_type": "section",
          "bullets": ["目的：提升效率", "範圍：XXX"]
        }},
        {{
          "title": "第二張：時程規劃",
          "slide_type": "comparison",
          "left_title": "已完成",
          "right_title": "待完成",
          "bullets": ["W1：需求分析", "W2：開發階段", "W3：驗收與部署"]
        }}
      ]
    }}
    ```
    """

    try:
        response = llm.invoke(prompt)
        raw_text = _coerce_llm_text_response(response)
        json_text = _extract_json_object(raw_text)
        llm_output = json.loads(json_text)
        if not isinstance(llm_output, dict):
            raise ValueError("LLM JSON root must be object.")
        return _normalize_analysis_result(llm_output, source_text=text)
    except Exception as e:
        logger.warning("LLM text analysis failed for text2pptx: %s", e)
        return _fallback_from_raw_text(text)


def _build_template_context() -> Dict[str, Any]:
    templates = _list_pptx_templates()
    ignored_templates = _list_ignored_template_files()
    default_template_available = DEFAULT_TEMPLATE_NAME in templates
    return {
        "templates": templates,
        "template_count": len(templates),
        "ignored_templates": ignored_templates,
        "ignored_count": len(ignored_templates),
        "default_template_name": DEFAULT_TEMPLATE_NAME,
        "default_template_available": default_template_available,
    }


@require_node("pptx")
def index(request):
    return render(request, "text2pptx/index.html", _build_template_context())


@require_node("pptx")
def template_admin(request):
    return render(request, "text2pptx/template_admin.html", _build_template_context())


@require_node("pptx")
def import_template(request):
    if request.method != "POST":
        return redirect("pptx_template_admin")

    upload = request.FILES.get("template_file")
    if not upload:
        messages.error(request, "請選擇要匯入的 .pptx 範本檔。")
        return redirect("pptx_template_admin")

    filename = _normalize_template_name(upload.name or "")
    if not filename.lower().endswith(".pptx"):
        messages.error(request, "只支援匯入 .pptx 檔案。")
        return redirect("pptx_template_admin")

    if upload.size and upload.size > (MAX_TEMPLATE_UPLOAD_MB * 1024 * 1024):
        messages.error(request, f"範本檔案過大，請小於 {MAX_TEMPLATE_UPLOAD_MB} MB。")
        return redirect("pptx_template_admin")

    raw = upload.read()
    try:
        audit = _audit_template_bytes(raw)
    except Exception as e:
        messages.error(request, f"範本解析失敗：{e}")
        return redirect("pptx_template_admin")

    if not audit.get("ok"):
        missing = audit.get("missing") or []
        messages.error(request, "匯入失敗，缺少必要版型：" + "、".join(missing))
        return redirect("pptx_template_admin")

    saved_name = _save_template_bytes(filename, raw)
    found = audit.get("found") or {}
    messages.success(
        request,
        "匯入成功："
        f"{saved_name}。"
        f"標題投影片={found.get('cover')} / "
        f"章節標題={found.get('section')} / "
        f"內容頁={found.get('content')} / "
        f"雙欄必較頁={found.get('two_content')}",
    )
    return redirect("pptx_template_admin")


@require_node("pptx", api=True)
def generate_pptx(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    text = (request.POST.get("text") or "").strip()
    user_title = (request.POST.get("title") or "").strip()
    tpl_name = (request.POST.get("template") or "").strip() or DEFAULT_TEMPLATE_NAME

    if not text:
        return JsonResponse({"ok": False, "error": "請輸入文字內容"}, status=400)
    if len(text) > MAX_INPUT_CHARS:
        return JsonResponse({"ok": False, "error": f"文字內容超過上限 {MAX_INPUT_CHARS} 字"}, status=400)

    try:
        from pptx import Presentation
        from pptx.util import Inches
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"缺少 python-pptx 套件：{e}"}, status=500)

    try:
        # --- AI 結構化分析 ---
        marked_result = _parse_marked_text_structure(text)
        analysis_result = marked_result if marked_result is not None else _analyze_text_with_llm(text)
        main_title = user_title or analysis_result.get("main_title", DEFAULT_MAIN_TITLE)
        main_subtitle = analysis_result.get("main_subtitle", DEFAULT_MAIN_SUBTITLE)
        llm_slides = analysis_result.get("slides", [])
        
        tpl_path = _safe_select_template(tpl_name)
        prs = Presentation(tpl_path) if tpl_path else Presentation()
        if tpl_path:
            _clear_all_slides(prs)

        cover_layout = _pick_layout_adaptive(prs, "cover")

        # --- 封面製作 ---
        cover = prs.slides.add_slide(cover_layout)
        cover_title = _find_title_shape(cover)
        if not cover_title:
            tb = cover.shapes.add_textbox(Inches(0.5), Inches(1), Inches(9), Inches(1.5))
            cover_title = tb
        
        cover_title.text_frame.text = main_title # Use LLM-generated main title
        _apply_font_style(cover_title.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

        subtitle_tf = _find_subtitle_text_frame(cover, exclude_shape=cover_title)
        if subtitle_tf:
            subtitle_tf.clear()
            p = subtitle_tf.paragraphs[0] if subtitle_tf.paragraphs else subtitle_tf.add_paragraph()
            p.text = main_subtitle # Use LLM-generated main subtitle
            _apply_font_style(p, SUBTITLE_FONT_PT)

        # Use LLM-structured slides
        for i, slide_data in enumerate(llm_slides, start=1):
            slide_title = str(slide_data.get("title") or f"投影片 {i}")
            slide_type = _resolve_slide_type(slide_data.get("slide_type"))
            bullets = slide_data.get("bullets", [])
            if not isinstance(bullets, list):
                bullets = [str(bullets)]
            bullets = [str(b).strip() for b in bullets if str(b).strip()]

            if slide_type == "section":
                slide = prs.slides.add_slide(_pick_layout_adaptive(prs, "section"))
                title_shape = _find_title_shape(slide)
                if not title_shape:
                    title_shape = slide.shapes.add_textbox(Inches(0.8), Inches(1.2), Inches(8.5), Inches(1.6))
                title_shape.text_frame.text = slide_title
                _apply_font_style(title_shape.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

                section_tfs = _find_content_text_frames(slide, exclude_shape=title_shape)
                if section_tfs:
                    _fill_bullets(section_tfs[0], bullets)
                continue

            if slide_type in ("two_content", "comparison"):
                column_chunks = list(_chunk_list(bullets, MAX_BULLETS_PER_SLIDE * 2)) if bullets else [[]]
                for part_idx, chunk in enumerate(column_chunks):
                    slide = prs.slides.add_slide(_pick_layout_adaptive(prs, slide_type))
                    shown_title = slide_title if part_idx == 0 else f"{slide_title}（續）"
                    title_shape = _find_title_shape(slide)
                    if not title_shape:
                        title_shape = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(1))
                    title_shape.text_frame.text = shown_title
                    _apply_font_style(title_shape.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

                    content_tfs = _find_content_text_frames(slide, exclude_shape=title_shape)
                    if len(content_tfs) < 2:
                        content_tfs = [
                            slide.shapes.add_textbox(Inches(0.6), Inches(1.6), Inches(4.2), Inches(4.8)).text_frame,
                            slide.shapes.add_textbox(Inches(5.0), Inches(1.6), Inches(4.2), Inches(4.8)).text_frame,
                        ]

                    left_title, left_items, right_title, right_items = _split_two_columns(slide_data, chunk, slide_type)
                    _fill_column(content_tfs[0], left_title, left_items)
                    _fill_column(content_tfs[1], right_title, right_items)
                continue

            bullet_chunks = list(_chunk_list(bullets, MAX_BULLETS_PER_SLIDE)) if bullets else [[]]
            for part_idx, part in enumerate(bullet_chunks):
                slide = prs.slides.add_slide(_pick_layout_adaptive(prs, "content"))
                shown_title = slide_title if part_idx == 0 else f"{slide_title}（續）"
                title_shape = _find_title_shape(slide)
                if not title_shape:
                    title_shape = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(1))
                title_shape.text_frame.text = shown_title
                _apply_font_style(title_shape.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

                content_tfs = _find_content_text_frames(slide, exclude_shape=title_shape)
                if content_tfs:
                    _fill_bullets(content_tfs[0], part)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)

        filename = _build_download_filename(user_title or main_title, fallback=DEFAULT_MAIN_TITLE)
        ascii_fallback = _safe_filename(
            filename.encode("ascii", errors="ignore").decode("ascii"),
            default="slides",
        )
        if not ascii_fallback.lower().endswith(".pptx"):
            ascii_fallback = f"{ascii_fallback}.pptx"
        quoted_filename = quote(filename)
        resp = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        resp["Content-Disposition"] = (
            f"attachment; filename=\"{ascii_fallback}\"; "
            f"filename*=UTF-8''{quoted_filename}"
        )
        return resp

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
