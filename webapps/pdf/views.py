from __future__ import annotations

import io
import json
import os
from datetime import datetime
from typing import List, Tuple

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node

# Windows default Tesseract location. Can be overridden by env TESSERACT_CMD.
os.environ.setdefault("TESSDATA_PREFIX", r"C:\Program Files\Tesseract-OCR")


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
    Return app base for apiurl():
    - direct: /pdf/... -> /pdf
    - proxied: /djangoai/pdf/... -> /djangoai/pdf
    """
    script = _norm_base(getattr(request, "script_name", "") or request.META.get("SCRIPT_NAME", ""))
    return _norm_base((script + "/pdf").replace("//", "/"))


@require_node("pdf")
def index(request):
    return render(request, "pdf/index.html", {"app_base_url": _calc_app_base_url(request)})


def _safe_filename_base(name: str) -> str:
    base = os.path.splitext(os.path.basename(name or "document"))[0]
    for ch in ['"', "'", "\\", "/", ":", "*", "?", "<", ">", "|", "\r", "\n", "\t"]:
        base = base.replace(ch, "_")
    return base or "document"


def _get_uploaded_pdf(request):
    f = request.FILES.get("pdf")
    if not f:
        return None, JsonResponse({"ok": False, "error": "請先上傳 PDF"}, status=400)
    if not f.name.lower().endswith(".pdf"):
        return None, JsonResponse({"ok": False, "error": "僅支援 .pdf 檔案"}, status=400)

    max_mb = int(os.environ.get("PDF_MAX_MB", "50") or 50)
    if f.size > max_mb * 1024 * 1024:
        return None, JsonResponse({"ok": False, "error": f"檔案大小超過上限 {max_mb}MB"}, status=400)

    return f, None


def _extract_pdf_text_pypdf(file_obj) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_obj)
    parts: List[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"[第 {i} 頁]\n{text}")
    return "\n\n".join(parts).strip()


def _ocr_pdf_text(file_bytes: bytes, lang: str = "chi_tra+eng") -> str:
    import pypdfium2 as pdfium
    import pytesseract

    tcmd = os.environ.get("TESSERACT_CMD", "").strip()
    if tcmd:
        pytesseract.pytesseract.tesseract_cmd = tcmd

    pdf = pdfium.PdfDocument(file_bytes)
    parts: List[str] = []
    for i in range(len(pdf)):
        page = pdf.get_page(i)
        pil_img = page.render(scale=2.5).to_pil()
        text = (pytesseract.image_to_string(pil_img, lang=lang) or "").strip()
        if text:
            parts.append(f"[第 {i + 1} 頁 OCR]\n{text}")
        else:
            parts.append(f"[第 {i + 1} 頁 OCR]\n（未擷取到文字）")
        page.close()
    return "\n\n".join(parts).strip()


def _extract_pdf_text_auto(file_obj, ocr_lang: str = "chi_tra+eng", min_chars: int = 40) -> Tuple[str, bool]:
    """
    Returns: (text, used_ocr)
    """
    file_bytes = file_obj.read()

    pypdf_text = ""
    try:
        pypdf_text = _extract_pdf_text_pypdf(io.BytesIO(file_bytes))
    except Exception:
        pypdf_text = ""

    if pypdf_text and len(pypdf_text) >= min_chars:
        return pypdf_text, False

    try:
        ocr_text = _ocr_pdf_text(file_bytes, lang=ocr_lang)
        return (ocr_text or "").strip(), True
    except Exception as e:
        # OCR can fail on malformed/encrypted PDFs; fallback to pypdf if available.
        if pypdf_text and pypdf_text.strip():
            return pypdf_text.strip(), False
        raise RuntimeError(f"PDF OCR 失敗：{e}")


@csrf_exempt
@require_node("pdf", api=True)
def api_extract_text(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    f, err = _get_uploaded_pdf(request)
    if err:
        return err

    ocr_lang = (request.POST.get("ocr_lang") or os.environ.get("OCR_LANG") or "chi_tra+eng").strip()
    try:
        text, used_ocr = _extract_pdf_text_auto(f, ocr_lang=ocr_lang)
        return JsonResponse(
            {
                "ok": True,
                "filename": f.name,
                "chars": len(text),
                "text": text,
                "used_ocr": used_ocr,
            },
            status=200,
        )
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@csrf_exempt
@require_node("pdf", api=True)
def api_download_txt(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    f, err = _get_uploaded_pdf(request)
    if err:
        return err

    ocr_lang = (request.POST.get("ocr_lang") or os.environ.get("OCR_LANG") or "chi_tra+eng").strip()
    try:
        text, used_ocr = _extract_pdf_text_auto(f, ocr_lang=ocr_lang)
        base = _safe_filename_base(f.name)
        stamp = datetime.now().strftime("%Y%m%d")
        filename = f"{base}_{stamp}.txt"
        header = f"[OCR 模式] lang={ocr_lang}\n\n" if used_ocr else ""
        resp = HttpResponse(header + (text or ""), content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@csrf_exempt
@require_node("pdf", api=True)
def api_download_docx(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    f, err = _get_uploaded_pdf(request)
    if err:
        return err

    ocr_lang = (request.POST.get("ocr_lang") or os.environ.get("OCR_LANG") or "chi_tra+eng").strip()
    try:
        from docx import Document

        text, used_ocr = _extract_pdf_text_auto(f, ocr_lang=ocr_lang)

        doc = Document()
        doc.add_heading("PDF 擷取結果", level=1)
        if used_ocr:
            doc.add_paragraph(f"OCR 模式：lang={ocr_lang}")

        if text:
            for block in text.split("\n\n"):
                b = (block or "").strip()
                if b:
                    doc.add_paragraph(b)
        else:
            doc.add_paragraph("未擷取到文字")

        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)

        base = _safe_filename_base(f.name)
        stamp = datetime.now().strftime("%Y%m%d")
        filename = f"{base}_{stamp}.docx"
        resp = HttpResponse(
            bio.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
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
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        return "".join(parts).strip()

    return str(resp).strip()


def _local_summary_fallback(doc_text: str) -> str:
    """
    Fallback summary when LLM is unavailable.
    """
    lines = [ln.strip() for ln in doc_text.splitlines() if ln.strip()]
    topic = lines[0] if lines else "未能判定主題"
    key_points = lines[:6]
    top_data = [ln for ln in lines if any(ch.isdigit() for ch in ln)][:5]

    summary_lines = []
    if lines:
        summary_lines.append(f"文件主要圍繞「{topic}」展開。")
        summary_lines.append("內容已完成初步結構化整理，可進一步人工確認細節。")
        summary_lines.append("建議針對條列重點與數據欄位進行二次校對。")
    else:
        summary_lines.append("原始內容過短，無法形成完整摘要。")

    kps = "\n".join([f"- {p}" for p in key_points]) if key_points else "- （無可擷取重點）"
    datas = "\n".join([f"- {d}" for d in top_data]) if top_data else "- （未檢出明確數據）"

    return (
        "一、文件主題：\n"
        f"{topic}\n\n"
        "二、核心摘要：\n"
        + "\n".join(summary_lines[:5])
        + "\n\n三、關鍵重點：\n"
        + kps
        + "\n\n四、重要數據 / 結論：\n"
        + datas
        + "\n\n五、可行動建議（若適用）：\n"
        "- 先確認摘要中的主題與關鍵點是否符合原文目的。\n"
        "- 對重要數據進行人工覆核後再對外使用。"
    )


@csrf_exempt
@require_node("pdf", api=True)
def api_summary(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    doc_text = ""
    if request.content_type and "application/json" in request.content_type.lower():
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
            doc_text = str(body.get("text") or "").strip()
        except Exception:
            doc_text = ""
    else:
        doc_text = (request.POST.get("text") or "").strip()

    if not doc_text:
        return JsonResponse({"ok": False, "error": "請先提供文件內容"}, status=400)

    max_chars = int(os.environ.get("PDF_SUMMARY_MAX_CHARS", "12000") or 12000)
    if len(doc_text) > max_chars:
        doc_text = doc_text[:max_chars]

    try:
        llm = get_chat_model(temperature=0.2, timeout=120)
        summary = _llm_to_text(llm.invoke(_build_summary_prompt(doc_text)))
        if not summary:
            summary = _local_summary_fallback(doc_text)
        return JsonResponse({"ok": True, "summary": summary, "fallback": False}, status=200)
    except Exception:
        summary = _local_summary_fallback(doc_text)
        return JsonResponse({"ok": True, "summary": summary, "fallback": True}, status=200)
