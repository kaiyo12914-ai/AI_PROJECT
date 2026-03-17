from __future__ import annotations

import io
import os
import re
from typing import Optional, List

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node


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
    title = (request.POST.get("title") or "簡報").strip()
    tpl_name = (request.POST.get("template") or "").strip()

    if not text:
        return JsonResponse({"ok": False, "error": "請輸入文字內容"}, status=400)

    try:
        from pptx import Presentation
        from pptx.util import Inches
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"缺少 python-pptx 套件：{e}"}, status=500)

    try:
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
        
        cover_title.text_frame.text = title
        _apply_font_style(cover_title.text_frame.paragraphs[0], TITLE_FONT_PT, bold=True)

        subtitle_tf = _find_largest_text_frame(cover, exclude_shape=cover_title)
        if subtitle_tf:
            subtitle_tf.clear()
            p = subtitle_tf.paragraphs[0] if subtitle_tf.paragraphs else subtitle_tf.add_paragraph()
            p.text = "Text → PPTX 自動產生"
            _apply_font_style(p, SUBTITLE_FONT_PT)

        slides_raw = [s.strip() for s in text.split("===") if s.strip()]

        for i, block in enumerate(slides_raw, start=1):
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            slide_title = lines[0] if lines else f"投影片 {i}"
            bullets = lines[1:] if len(lines) > 1 else []

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

        filename = f"{_safe_filename(title)}.pptx"
        resp = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}"
        return resp

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
