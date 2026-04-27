from __future__ import annotations

import io
import json
import re
import time
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node

from .models import DocumentFormalizeLog

MODE_CONFIG: dict[str, dict[str, str]] = {
    "general": {"label": "一般正式", "style": "正式、精簡、客觀"},
    "official_sign": {"label": "公文簽辦", "style": "簽辦語氣，條理分點，可供簽核"},
    "meeting": {"label": "會議紀錄", "style": "會議紀錄語氣，重點與決議清楚"},
    "report": {"label": "工作報告", "style": "工作報告語氣，進度與結果明確"},
    "external_letter": {"label": "對外函文", "style": "對外正式函文語氣，禮貌中性"},
}

DEFAULT_OPTIONS: dict[str, Any] = {
    "fixTypos": True,
    "concise": False,
    "enhanceStructure": True,
    "politeTone": False,
    "keepParagraphs": False,
}


@require_node("formalize")
def page_index(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "document_formalize/index.html",
        {
            "mode_options": [
                {"value": k, "label": v["label"]}
                for k, v in MODE_CONFIG.items()
            ]
        },
    )


def _safe_text(v: Any) -> str:
    return "" if v is None else str(v)


def _mask_sensitive(text: str) -> str:
    s = text or ""
    patterns = [
        (r"\b[A-Z][12]\d{8}\b", "[ID]"),
        (r"\b09\d{2}[- ]?\d{3}[- ]?\d{3}\b", "[PHONE]"),
        (r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[EMAIL]"),
    ]
    for pat, rep in patterns:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    return s


def _normalize_text(text: str) -> str:
    s = _safe_text(text).replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    # punctuation normalize
    s = (
        s.replace(",", "，")
        .replace(";", "；")
        .replace(":", "：")
        .replace("?", "？")
        .replace("!", "！")
    )
    return s.strip()


def _basic_typo_fix(text: str) -> str:
    # Conservative corrections only.
    fix_map = {
        "因該": "應該",
        "在來": "再來",
        "必需": "必須",
    }
    out = text
    for k, v in fix_map.items():
        out = out.replace(k, v)
    return out


def _split_sentences(text: str) -> list[str]:
    s = _safe_text(text).strip()
    if not s:
        return []
    parts = re.split(r"(?<=[。！？；])\s*", s)
    return [p.strip() for p in parts if p and p.strip()]


def _fallback_formal_tone(text: str, polite_tone: bool) -> str:
    out = _safe_text(text)
    # Conservative replacements only; avoid changing facts.
    repl = {
        "這次": "本次",
        "這項": "本項",
        "現在": "目前",
        "只能": "僅能",
        "為了": "為",
        "以及": "及",
        "還有": "及",
        "有建置": "已建置",
        "沒有建置": "尚未建置",
    }
    for k, v in repl.items():
        out = out.replace(k, v)

    if polite_tone:
        polite_repl = {
            "請儘速": "敬請儘速",
            "請協助": "敬請協助",
            "請辦理": "敬請辦理",
            "請確認": "敬請確認",
        }
        for k, v in polite_repl.items():
            out = out.replace(k, v)

    return out


def _fallback_structure(text: str, mode: str, enhance_structure: bool) -> str:
    s = _safe_text(text).strip()
    if not s:
        return s
    if not enhance_structure:
        return s

    sentences = _split_sentences(s)
    if len(sentences) <= 1:
        return s

    cn_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    items: list[str] = []
    for i, sentence in enumerate(sentences):
        no = cn_nums[i] if i < len(cn_nums) else str(i + 1)
        items.append(f"{no}、{sentence}")

    title_map = {
        "general": "",
        "official_sign": "擬辦說明如下：",
        "meeting": "會議重點如下：",
        "report": "辦理情形如下：",
        "external_letter": "說明如下：",
    }
    title = title_map.get(mode, "")
    if title:
        return title + "\n" + "\n".join(items)
    return "\n".join(items)


def _build_prompt(text: str, mode: str, options: dict[str, Any]) -> str:
    cfg = MODE_CONFIG.get(mode, MODE_CONFIG["general"])
    mode_label = cfg["label"]
    mode_style = cfg["style"]

    option_lines = [
        f"- 修正錯字：{'是' if options.get('fixTypos') else '否'}",
        f"- 精簡語句：{'是' if options.get('concise') else '否'}",
        f"- 強化條理：{'是' if options.get('enhanceStructure') else '否'}",
        f"- 調整委婉語氣：{'是' if options.get('politeTone') else '否'}",
        f"- 保留原段落：{'是' if options.get('keepParagraphs') else '否'}",
    ]

    return (
        "你是公文改寫助理。請將輸入內容改寫為繁體中文正式書面語。\n"
        "必須遵守：\n"
        "1. 不可新增原文未提及之事實。\n"
        "2. 不可改變事件責任歸屬。\n"
        "3. 不可扭曲原意。\n"
        "4. 可修正語病、冗詞與口語詞。\n"
        "5. 若資訊不足，保守整理，不可腦補。\n\n"
        f"模式：{mode_label}\n"
        f"風格：{mode_style}\n"
        "參數：\n"
        + "\n".join(option_lines)
        + "\n\n輸出格式固定如下：\n"
        "【公文化結果】\n"
        "<改寫後全文>\n\n"
        "【修改重點】\n"
        "1. ...\n"
        "2. ...\n"
        "3. ...\n\n"
        "原文如下：\n"
        f"{text}"
    )


def _extract_llm_result(raw: str) -> tuple[str, list[str]]:
    s = _safe_text(raw).strip()
    result = s
    summary: list[str] = []

    m_result = re.search(
        r"【公文化結果】\s*(.*?)\s*(?:【修改重點】|$)",
        s,
        flags=re.DOTALL,
    )
    if m_result:
        result = m_result.group(1).strip()

    m_summary = re.search(r"【修改重點】\s*(.*)$", s, flags=re.DOTALL)
    if m_summary:
        lines = [x.strip() for x in m_summary.group(1).splitlines() if x.strip()]
        for line in lines:
            line = re.sub(r"^\d+[\.、]\s*", "", line).strip()
            if line:
                summary.append(line)

    if not summary:
        summary = ["調整為正式、客觀之書面語氣。", "保留原文核心意旨。"]

    return result, summary[:8]


def _fallback_formalize(text: str, mode: str, options: dict[str, Any]) -> tuple[str, list[str]]:
    out = text
    if options.get("fixTypos"):
        out = _basic_typo_fix(out)

    out = _fallback_formal_tone(out, polite_tone=bool(options.get("politeTone")))

    if options.get("concise"):
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"[，、]{2,}", "，", out)
        out = re.sub(r"(。){2,}", "。", out)

    if options.get("keepParagraphs"):
        # Keep user paragraphs; do not auto split into generated bullet sections.
        paras = [p.strip() for p in re.split(r"\n{2,}", out) if p.strip()]
        out = "\n\n".join(paras).strip()
    else:
        # Single paragraph output; no automatic sentence splitting.
        out = re.sub(r"\n+", " ", out).strip()

    summary = [
        "AI 服務異常，已使用保守規則進行正式語氣重寫。",
        "已進行語句整理，不啟用自動分段。",
        "未新增任何原文以外資訊。",
    ]
    return out, summary


def _error(code: str, message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"status": "error", "errorCode": code, "message": message}, status=status)


def _to_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


@csrf_exempt
@require_node("formalize", api=True)
def api_formalize(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _error("METHOD_NOT_ALLOWED", "method not allowed", 405)

    t0 = time.perf_counter()

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return _error("INVALID_JSON", "invalid json")

    text = _safe_text(body.get("text")).strip()
    mode = _safe_text(body.get("mode")).strip() or "general"
    options = body.get("options") or {}
    user_id = _safe_text(body.get("userId")).strip() or _safe_text(getattr(request, "login_user", ""))
    user_name = _safe_text(getattr(request, "login_user_name", ""))

    if not text:
        return _error("EMPTY_TEXT", "文字不可為空")
    if mode not in MODE_CONFIG:
        return _error("INVALID_MODE", "mode 無效")

    max_chars = _to_int(getattr(settings, "FORMALIZE_MAX_CHARS", 12000), 12000)
    if len(text) > max_chars:
        return _error("TEXT_TOO_LONG", f"字數超過上限 {max_chars}")

    normalized = _normalize_text(text)
    if options.get("fixTypos", DEFAULT_OPTIONS["fixTypos"]):
        normalized = _basic_typo_fix(normalized)

    merged_options = dict(DEFAULT_OPTIONS)
    if isinstance(options, dict):
        merged_options.update(options)

    prompt = _build_prompt(normalized, mode, merged_options)

    llm_error = ""
    formalized_text = ""
    summary: list[str] = []
    status_tag = "ok"

    try:
        llm = get_chat_model(temperature=0.15, timeout=90)
        llm_out = llm.invoke(prompt)
        raw = _safe_text(getattr(llm_out, "content", llm_out))
        formalized_text, summary = _extract_llm_result(raw)
    except Exception as e:
        llm_error = _safe_text(e)
        status_tag = "fallback"
        formalized_text, summary = _fallback_formalize(normalized, mode, merged_options)

    processing_ms = int((time.perf_counter() - t0) * 1000)

    try:
        DocumentFormalizeLog.objects.create(
            user_id=user_id,
            user_name=user_name,
            mode=mode,
            options_json=merged_options,
            input_chars=len(normalized),
            output_chars=len(formalized_text),
            processing_ms=processing_ms,
            status=status_tag,
            source_masked=_mask_sensitive(normalized[:2000]),
            result_masked=_mask_sensitive(formalized_text[:2000]),
        )
    except Exception:
        # Keep feature usable even if DB table is not migrated yet.
        pass

    return JsonResponse(
        {
            "status": "ok",
            "originalText": normalized,
            "formalizedText": formalized_text,
            "summaryOfChanges": summary,
            "tokenUsage": None,
            "processingTime": processing_ms,
            "mode": mode,
            "llmFallback": bool(llm_error),
            "llmError": llm_error[:300] if llm_error else "",
        },
        status=200,
    )


@require_node("formalize", api=True)
def api_history(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return _error("METHOD_NOT_ALLOWED", "method not allowed", 405)

    limit = _to_int(request.GET.get("limit"), 20)
    limit = max(1, min(limit, 100))
    user_id = _safe_text(request.GET.get("userId")).strip() or _safe_text(getattr(request, "login_user", ""))

    try:
        qs = DocumentFormalizeLog.objects.all()
        if user_id:
            qs = qs.filter(user_id=user_id)
        rows = list(qs[:limit])
    except Exception:
        rows = []

    return JsonResponse(
        {
            "status": "ok",
            "items": [
                {
                    "id": r.id,
                    "userId": r.user_id,
                    "userName": r.user_name,
                    "mode": r.mode,
                    "inputChars": r.input_chars,
                    "outputChars": r.output_chars,
                    "processingMs": r.processing_ms,
                    "statusTag": r.status,
                    "sourcePreview": r.source_masked[:120],
                    "resultPreview": r.result_masked[:120],
                    "createdAt": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }
    )


@csrf_exempt
@require_node("formalize", api=True)
def api_export(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return _error("METHOD_NOT_ALLOWED", "method not allowed", 405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return _error("INVALID_JSON", "invalid json")

    text = _safe_text(body.get("text")).strip()
    fmt = _safe_text(body.get("format")).strip().lower() or "txt"
    if not text:
        return _error("EMPTY_TEXT", "文字不可為空")

    if fmt == "txt":
        resp = HttpResponse(text, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = "attachment; filename*=UTF-8''formalized.txt"
        return resp

    if fmt == "docx":
        try:
            from docx import Document
        except Exception:
            return _error("DOCX_NOT_AVAILABLE", "docx 套件不可用", 500)

        doc = Document()
        for para in text.split("\n"):
            doc.add_paragraph(para)
        bio = io.BytesIO()
        doc.save(bio)
        content = bio.getvalue()
        resp = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp["Content-Disposition"] = "attachment; filename*=UTF-8''formalized.docx"
        return resp

    return _error("INVALID_EXPORT_FORMAT", "format 僅支援 txt/docx")


@require_node("formalize", api=True)
def api_template_list(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return _error("METHOD_NOT_ALLOWED", "method not allowed", 405)

    return JsonResponse(
        {
            "status": "ok",
            "modes": [
                {"value": key, "label": item["label"], "style": item["style"]}
                for key, item in MODE_CONFIG.items()
            ],
            "defaultOptions": DEFAULT_OPTIONS,
        }
    )
