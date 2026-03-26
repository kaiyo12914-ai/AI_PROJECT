from __future__ import annotations

import io
import os
from datetime import datetime
# ✅ 一定要在 pytesseract / OCR 之前設定
os.environ["TESSDATA_PREFIX"] = r"C:\Program Files\Tesseract-OCR"
# Linux 範例：
# os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/4.00"

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node


def _norm_base(p: str) -> str:
    s = (p or "").strip()
    if not s:
        return ""
    if not s.startswith("/"):
        s = "/" + s
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return "" if s == "/" else s


def _calc_app_base_url(request) -> str:
    """
    Compute app base url for apiurl():
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
        return None, JsonResponse({"ok": False, "error": "未收到檔案欄位 pdf"}, status=400)
    if not f.name.lower().endswith(".pdf"):
        return None, JsonResponse({"ok": False, "error": "檔案必須為 .pdf"}, status=400)
    if f.size > 20 * 1024 * 1024:
        return None, JsonResponse({"ok": False, "error": "檔案過大（上限 20MB）"}, status=400)
    return f, None


def _extract_pdf_text_pypdf(file_obj) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_obj)
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        t = (page.extract_text() or "").strip()
        if t:
            parts.append(f"【第 {i} 頁】\n{t}")
    return "\n\n".join(parts).strip()


def _ocr_pdf_text(file_bytes: bytes, lang: str = "chi_tra+eng") -> str:
    import pytesseract
    import pypdfium2 as pdfium

    tcmd = os.environ.get("TESSERACT_CMD", "").strip()
    if tcmd:
        pytesseract.pytesseract.tesseract_cmd = tcmd

    pdf = pdfium.PdfDocument(file_bytes)
    parts = []
    for i in range(len(pdf)):
        page = pdf.get_page(i)
        pil_img = page.render(scale=2.5).to_pil()
        text = (pytesseract.image_to_string(pil_img, lang=lang) or "").strip()
        if text:
            parts.append(f"【第 {i+1} 頁 OCR】\n{text}")
        else:
            parts.append(f"【第 {i+1} 頁 OCR】\n（此頁未辨識到文字）")
        page.close()

    return "\n\n".join(parts).strip()


def _extract_pdf_text_auto(file_obj, ocr_lang: str = "chi_tra+eng", min_chars: int = 40):
    file_bytes = file_obj.read()

    text = ""
    try:
        import io as _io
        text = _extract_pdf_text_pypdf(_io.BytesIO(file_bytes))
    except Exception:
        text = ""

    if text and len(text) >= min_chars:
        return text, False

    ocr_text = _ocr_pdf_text(file_bytes, lang=ocr_lang)
    return (ocr_text or "").strip(), True


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
            {"ok": True, "filename": f.name, "chars": len(text), "text": text, "used_ocr": used_ocr},
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
        doc.add_heading("PDF 轉換內容", level=1)
        if used_ocr:
            doc.add_paragraph(f"OCR 模式：lang={ocr_lang}")

        if text:
            for block in text.split("\n\n"):
                t = (block or "").strip()
                if t:
                    doc.add_paragraph(t)
        else:
            doc.add_paragraph("（未擷取到可用文字）")

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
