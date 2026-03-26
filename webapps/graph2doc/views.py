from __future__ import annotations

import json
import os
import uuid
from typing import List

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from langchain_core.prompts import ChatPromptTemplate

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node


ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_MB = 10


def _norm_base(path: str) -> str:
    s = (path or "").strip()
    if not s:
        return ""
    if not s.startswith("/"):
        s = "/" + s
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return "" if s == "/" else s


def _calc_app_base_url(request) -> str:
    """
    Build app base for apiurl():
    - direct: /graph/... -> /graph
    - proxied: /djangoai/graph/... -> /djangoai/graph
    """
    script = _norm_base(getattr(request, "script_name", "") or request.META.get("SCRIPT_NAME", ""))
    return _norm_base((script + "/graph").replace("//", "/"))


def _resolve_tesseract_cmd() -> str:
    env_cmd = (os.environ.get("TESSERACT_CMD") or "").strip()
    if env_cmd and os.path.exists(env_cmd):
        return env_cmd

    default_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_cmd):
        return default_cmd
    return ""


def _resolve_tessdata_dir(tesseract_cmd: str) -> str:
    env_dir = (os.environ.get("TESSDATA_PREFIX") or "").strip()
    candidates: List[str] = []
    if env_dir:
        candidates.append(env_dir)
        if not env_dir.lower().endswith("tessdata"):
            candidates.append(os.path.join(env_dir, "tessdata"))

    if tesseract_cmd:
        candidates.append(os.path.join(os.path.dirname(tesseract_cmd), "tessdata"))

    candidates.append(r"C:\Program Files\Tesseract-OCR\tessdata")

    for d in candidates:
        if d and os.path.isdir(d):
            return d
    return ""


def _ocr_config(psm: int, tessdata_dir: str) -> str:
    base = f"--oem 3 --psm {psm}"
    if tessdata_dir:
        return f'{base} --tessdata-dir "{tessdata_dir}"'
    return base


@require_node("graph")
def graph_page(request):
    return render(request, "graph2doc/index.html", {"app_base_url": _calc_app_base_url(request)})


def _ocr_image_text(image_path: str, lang: str = "chi_tra+eng") -> str:
    import pytesseract
    from PIL import Image, ImageOps

    tcmd = _resolve_tesseract_cmd()
    if not tcmd:
        raise RuntimeError("找不到 tesseract.exe，請設定 TESSERACT_CMD 或確認安裝路徑")
    pytesseract.pytesseract.tesseract_cmd = tcmd

    tessdata_dir = _resolve_tessdata_dir(tcmd)
    if not tessdata_dir:
        raise RuntimeError("找不到 tessdata 目錄，請設定 TESSDATA_PREFIX 指向 tessdata")
    os.environ["TESSDATA_PREFIX"] = tessdata_dir

    with Image.open(image_path) as img:
        # Improve OCR quality for scanned documents.
        gray = ImageOps.grayscale(img)
        enhanced = ImageOps.autocontrast(gray)
        text1 = (
            pytesseract.image_to_string(
                enhanced,
                lang=lang,
                config=_ocr_config(6, tessdata_dir),
            )
            or ""
        ).strip()
        if len(text1) >= 40:
            return text1

        # Fallback pass for sparse/table-like content.
        text2 = (
            pytesseract.image_to_string(
                enhanced,
                lang=lang,
                config=_ocr_config(11, tessdata_dir),
            )
            or ""
        ).strip()
        return text2 if len(text2) >= len(text1) else text1


def _generate_ai_text(title: str, notes: str, has_image: bool, ocr_text: str) -> str:
    llm = get_chat_model(temperature=0.2, timeout=120)

    system = (
        "你是一位專業的圖文轉文字助手。"
        "請依照 OCR 結果產生可直接使用的結構化內容。"
        "請使用繁體中文，避免空泛語句。"
    )

    user = (
        "請輸出：\n"
        "1. 主題一句話\n"
        "2. 內容重點（3~8點）\n"
        "3. 若是表單或公文，請整理關鍵欄位\n\n"
        f"- 標題：{title or '未命名圖文'}\n"
        f"- 是否有圖片：{'是' if has_image else '否'}\n"
        f"- 補充說明：{notes or '未提供'}\n"
        f"- OCR 文字內容：\n{ocr_text or '（未擷取到文字）'}\n"
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("user", user),
        ]
    )
    resp = llm.invoke(prompt.format_messages())
    out = getattr(resp, "content", None) or str(resp)
    return (out or "").strip()


def _safe_filename(name: str) -> str:
    name = os.path.basename(name or "upload")
    cleaned = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    return ("".join(cleaned) or "upload").strip()


@csrf_exempt
@require_node("graph", api=True)
def graph_build_text(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    title = (request.POST.get("title") or "未命名圖文").strip()
    notes = (request.POST.get("notes") or "").strip()
    img = request.FILES.get("image")

    saved_img_path = None
    if img:
        if getattr(img, "size", 0) > MAX_IMAGE_MB * 1024 * 1024:
            return JsonResponse({"ok": False, "error": f"圖片大小不可超過 {MAX_IMAGE_MB}MB"}, status=400)

        orig = _safe_filename(getattr(img, "name", "image.png"))
        _, ext = os.path.splitext(orig.lower())
        if ext not in ALLOWED_IMAGE_EXTS:
            return JsonResponse(
                {"ok": False, "error": f"僅支援圖片格式：{', '.join(sorted(ALLOWED_IMAGE_EXTS))}"},
                status=400,
            )

        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        os.makedirs(upload_dir, exist_ok=True)

        img_name = f"{uuid.uuid4().hex}_{orig}"
        saved_img_path = os.path.join(upload_dir, img_name)
        with open(saved_img_path, "wb") as f:
            for chunk in img.chunks():
                f.write(chunk)

    ocr_lang = (request.POST.get("ocr_lang") or os.environ.get("OCR_LANG") or "chi_tra+eng").strip()
    ocr_text = ""
    ocr_error = ""
    if saved_img_path:
        try:
            ocr_text = _ocr_image_text(saved_img_path, lang=ocr_lang)
        except Exception as e:
            ocr_error = str(e)

    if saved_img_path and not ocr_text.strip():
        if ocr_error:
            return JsonResponse({"ok": False, "error": f"圖片 OCR 失敗：{ocr_error}"}, status=500)
        return JsonResponse(
            {"ok": False, "error": "未擷取到圖片文字，請提高圖片清晰度或改用 PDF→TXT/OCR。"},
            status=422,
        )

    try:
        text = _generate_ai_text(
            title=title,
            notes=notes,
            has_image=bool(saved_img_path),
            ocr_text=ocr_text,
        )
        if not text.strip():
            text = ocr_text.strip()
        return JsonResponse(
            {
                "ok": True,
                "text": text,
                "ocr_chars": len(ocr_text),
                "used_ocr": bool(ocr_text),
                "ocr_error": ocr_error,
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def _build_summary_prompt(doc_text: str) -> str:
    return f"""你是一位專業的文件分析與摘要專家，請根據以下文件內容，產出結構化重點摘要。

【任務要求】
1. 提取文件的核心主題與目的
2. 梳理關鍵重點（條列式）
3. 保留重要數據、結論與專有名詞
4. 避免冗長敘述，不要逐句改寫
5. 使用清晰、簡潔、專業的語言

【輸出格式】
請嚴格依照以下結構輸出：

一、文件主題：
（用一句話說明）

二、核心摘要：
（3～5句重點總結）

三、關鍵重點：
- 重點1
- 重點2
- 重點3
（視內容增加）

四、重要數據 / 結論：
- （列出關鍵數據或結論）

五、可行動建議（若適用）：
- （可執行的建議）

【文件內容】
{doc_text}
""".strip()


def _llm_to_text(resp) -> str:
    if resp is None:
        return ""
    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: List[str] = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                out.append(str(part.get("text") or part.get("content") or ""))
        return "".join(out).strip()
    return str(resp).strip()


def _local_summary_fallback(doc_text: str) -> str:
    lines = [ln.strip() for ln in doc_text.splitlines() if ln.strip()]
    topic = lines[0] if lines else "未能判定主題"
    key_points = lines[:6]
    data_points = [ln for ln in lines if any(ch.isdigit() for ch in ln)][:5]

    return (
        "一、文件主題：\n"
        f"{topic}\n\n"
        "二、核心摘要：\n"
        f"文件主要圍繞「{topic}」說明。\n"
        "內容已完成初步摘要整理，建議人工覆核細節。\n"
        "可優先檢視關鍵重點與數據欄位。\n\n"
        "三、關鍵重點：\n"
        + ("\n".join([f"- {p}" for p in key_points]) if key_points else "- （無可擷取重點）")
        + "\n\n四、重要數據 / 結論：\n"
        + ("\n".join([f"- {d}" for d in data_points]) if data_points else "- （未檢出明確數據）")
        + "\n\n五、可行動建議（若適用）：\n"
        "- 先確認摘要內容與原文目的是否一致。\n"
        "- 對關鍵數據進行人工覆核後再引用。"
    )


@csrf_exempt
@require_node("graph", api=True)
def graph_summary(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    text = ""
    if request.content_type and "application/json" in request.content_type.lower():
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
            text = str(body.get("text") or "").strip()
        except Exception:
            text = ""
    else:
        text = (request.POST.get("text") or "").strip()

    if not text:
        return JsonResponse({"ok": False, "error": "請先提供文件內容"}, status=400)

    max_chars = int(os.environ.get("GRAPH_SUMMARY_MAX_CHARS", "12000") or 12000)
    if len(text) > max_chars:
        text = text[:max_chars]

    try:
        llm = get_chat_model(temperature=0.2, timeout=120)
        summary = _llm_to_text(llm.invoke(_build_summary_prompt(text)))
        if not summary:
            summary = _local_summary_fallback(text)
            return JsonResponse({"ok": True, "summary": summary, "fallback": True}, status=200)
        return JsonResponse({"ok": True, "summary": summary, "fallback": False}, status=200)
    except Exception:
        summary = _local_summary_fallback(text)
        return JsonResponse({"ok": True, "summary": summary, "fallback": True}, status=200)
