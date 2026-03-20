from __future__ import annotations

import io
import os
import re
import json # Import json for parsing LLM output
from typing import Optional, List, Dict, Any

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.llm.llm_factory import get_chat_model # Import LLM factory


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

# ✅ 字體規範
FONT_NAME_EAST_ASIAN = "DFKai-SB"      # 標楷體 (Windows)
FONT_NAME_ASCII = "Times New Roman"    # Times New Roman (英文)


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


def _safe_select_template(tpl_name: str) -> Optional[str]:
    tpl_name = (tpl_name or "").strip()
    if not tpl_name:
        return None
    allowed = set(_list_pptx_templates())
    if tpl_name not in allowed:
        return None
    return os.path.join(PPTX_TEMPLATE_DIR, tpl_name)


def _pick_layout_adaptive(prs, layout_type: str):
    type_keys = {
        "cover": ["cover", "title slide", "標題投影片", "title only"],
        "content": ["content", "title and content", "標題及內容", "body", "slide", "投影片"]
    }
    keys = type_keys.get(layout_type, [])
    
    for layout in prs.slide_layouts:
        name = (getattr(layout, "name", "") or "").lower()
        for k in keys:
            if k in name:
                return layout

    if layout_type == "cover":
        return prs.slide_layouts[0]
    
    if layout_type == "content":
        for layout in prs.slide_layouts:
            ph_types = [p.placeholder_format.type for p in layout.placeholders]
            if 1 in ph_types and 2 in ph_types:
                return layout
        return prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]

    return prs.slide_layouts[0]


def _find_largest_text_frame(slide, exclude_shape=None):
    best_shape = None
    best_area = -1
    
    for shape in slide.shapes:
        if exclude_shape is not None and shape == exclude_shape:
            continue
        if getattr(shape, "is_placeholder", False):
            if shape.placeholder_format.type in (2, 7):
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


def _chunk_list(items: List[str], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]


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
    5. 每張投影片（slides 的每個元素）必須包含兩個鍵："title" 和 "bullets"。
    6. "title"：該投影片的標題。
    7. "bullets"：一個列表，包含該投影片的所有條列要點。如果沒有要點，則為空列表。
    8. 盡可能語義化地拆分內容到不同的投影片，每張投影片的條列要點數量不應超過 {MAX_BULLETS_PER_SLIDE} 點。
    9. 若原文沒有明確主標題，請自動生成一個簡潔相關的標題。
    10. 若原文沒有明確副標題，請使用「文字內容自動生成簡報」作為副標題。

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
          "bullets": ["目的：提升效率", "範圍：XXX"]
        }},
        {{
          "title": "第二張：時程規劃",
          "bullets": ["W1：需求分析", "W2：開發階段", "W3：驗收與部署"]
        }}
      ]
    }}
    ```
    """

    try:
        response = llm.invoke(prompt)
        llm_output = json.loads(response)
        return llm_output
    except Exception as e:
        print(f"LLM text analysis failed: {e}")
        # Fallback to original splitting if LLM fails
        return {
            "main_title": "簡報",
            "main_subtitle": "文字內容自動生成簡報",
            "slides": [
                {"title": s.splitlines()[0] if s.splitlines() else "", "bullets": s.splitlines()[1:]}
                for s in text.split("===") if s.strip()
            ]
        }


@require_node("pptx")
def index(request):
    templates = _list_pptx_templates()
    return render(request, "text2pptx/index.html", {"templates": templates})


@csrf_exempt
@require_node("pptx", api=True)
def generate_pptx(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    text = (request.POST.get("text") or "").strip()
    # title = (request.POST.get("title") or "簡報").strip() # Now derived from LLM
    tpl_name = (request.POST.get("template") or "").strip()

    if not text:
        return JsonResponse({"ok": False, "error": "請輸入文字內容"}, status=400)

    try:
        from pptx import Presentation
        from pptx.util import Inches
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"缺少 python-pptx 套件：{e}"}, status=500)

    try:
        # --- AI 結構化分析 ---
        analysis_result = _analyze_text_with_llm(text)
        main_title = analysis_result.get("main_title", "簡報")
        main_subtitle = analysis_result.get("main_subtitle", "文字內容自動生成簡報")
        llm_slides = analysis_result.get("slides", [])
        
        tpl_path = _safe_select_template(tpl_name)
        prs = Presentation(tpl_path) if tpl_path else Presentation()

        cover_layout = _pick_layout_adaptive(prs, "cover")
        content_layout = _pick_layout_adaptive(prs, "content")

        # --- 封面製作 ---
        cover = prs.slides.add_slide(cover_layout)
        cover_title = cover.shapes.title if cover.shapes.title else None
        if not cover_title:
            tb = cover.shapes.add_textbox(Inches(0.5), Inches(1), Inches(9), Inches(1.5))
            cover_title = tb
        
        cover_title.text_frame.text = main_title # Use LLM-generated main title
        _apply_font_style(cover_title.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

        subtitle_tf = _find_largest_text_frame(cover, exclude_shape=cover_title)
        if subtitle_tf:
            subtitle_tf.clear()
            p = subtitle_tf.paragraphs[0] if subtitle_tf.paragraphs else subtitle_tf.add_paragraph()
            p.text = main_subtitle # Use LLM-generated main subtitle
            _apply_font_style(p, SUBTITLE_FONT_PT)

        # Use LLM-structured slides
        for i, slide_data in enumerate(llm_slides, start=1):
            slide_title = slide_data.get("title", f"投影片 {i}")
            bullets = slide_data.get("bullets", [])

            # LLM should handle chunking, but keep fallback just in case or for future adjustments
            # Here we assume LLM already chunked per MAX_BULLETS_PER_SLIDE rule
            bullet_chunks = list(_chunk_list(bullets, MAX_BULLETS_PER_SLIDE)) if bullets else [[]]

            for part_idx, part in enumerate(bullet_chunks):
                slide = prs.slides.add_slide(content_layout)
                shown_title = slide_title if part_idx == 0 else f"{slide_title}（續）"
                
                title_shape = slide.shapes.title if slide.shapes.title else None
                if not title_shape:
                    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(1))
                    title_shape = tb
                
                title_shape.text_frame.text = shown_title
                _apply_font_style(title_shape.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

                content_tf = _find_largest_text_frame(slide, exclude_shape=title_shape)
                if content_tf:
                    content_tf.clear()
                    if part:
                        for idx, b in enumerate(part):
                            p = content_tf.paragraphs[idx] if idx < len(content_tf.paragraphs) else content_tf.add_paragraph()
                            p.text = b
                            _apply_font_style(p, BODY_FONT_PT)
                    else:
                        p = content_tf.paragraphs[0] if content_tf.paragraphs else content_tf.add_paragraph()
                        p.text = "（無內容）"
                        _apply_font_style(p, BODY_FONT_PT)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)

        filename = f"{_safe_filename(main_title)}.pptx" # Use LLM-generated main title for filename
        resp = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
        return resp

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
