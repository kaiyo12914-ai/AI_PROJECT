# webapps/translator/views.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.models import DocumentTemplate

# ✅ 統一 LLM：只走 llm_factory（禁止在 translator 內 new Ollama / 打 OpenAI HTTP）
from webapps.llm.llm_factory import get_chat_model
from webapps.llm.services import translate_core


# =========================
# Pages
# =========================
@require_node("translator")
def index(request):
    return render(request, "translator/index.html")


# =========================
# ✅ NO_PROXY helper（統一走 NO_PROXY / no_proxy）
# - 不用 trust_env=False（避免子系統各玩一套）
# - 呼叫外部服務前，確保 host 在 NO_PROXY
# =========================
def _extract_host(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return ""
    if "://" not in s:
        s = "http://" + s
    try:
        u = urlparse(s)
        return (u.hostname or "").strip()
    except Exception:
        return ""


def _ensure_no_proxy(hosts: List[str]) -> None:
    hosts = [h.strip() for h in (hosts or []) if h and h.strip()]
    if not hosts:
        return

    # 優先用你可能已存在的共用工具
    try:
        from webapps.common.net import ensure_no_proxy  # type: ignore
        ensure_no_proxy(hosts)
        return
    except Exception:
        pass

    # fallback：合併 NO_PROXY + no_proxy 並去重（case-insensitive）
    cur: List[str] = []
    for k in ("NO_PROXY", "no_proxy"):
        cur += [x.strip() for x in (os.environ.get(k) or "").split(",") if x.strip()]

    merged: List[str] = []
    seen = set()
    for x in cur + hosts:
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(x)

    val = ",".join(merged)
    os.environ["NO_PROXY"] = val
    os.environ["no_proxy"] = val


# =========================
# ✅ TTS API
# POST /translator/tts/
# form-data: draft 或 text
# 回傳: {ok, text, audio}
# =========================
@csrf_exempt
@require_node("translator", api=True)
def generate_comment_tts(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    draft = (
        request.POST.get("draft")
        or request.POST.get("text")
        or request.GET.get("draft")
        or request.GET.get("text")
        or ""
    ).strip()

    if not draft:
        return JsonResponse({"ok": False, "error": "draft/text is required"}, status=400)

    base = (getattr(settings, "TTS_API_BASE_URL", "") or "").rstrip("/")
    url = (base + "/tts/generate/") if base else "/tts/generate/"

    # ✅ 統一 NO_PROXY：把 TTS host 加入 NO_PROXY/no_proxy，讓 requests 正常走 NO_PROXY 邏輯
    host = _extract_host(base)
    if host:
        _ensure_no_proxy([host])

    try:
        r = requests.post(
            url,
            json={"text": draft},
            timeout=int(getattr(settings, "TTS_API_TIMEOUT", 60)),
        )
        data = r.json() if r.content else {}
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"call tts api failed: {e}"}, status=500)

    if not data or not data.get("ok"):
        return JsonResponse(
            {"ok": False, "error": data.get("error", "tts failed"), "raw": data},
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "text": draft,
            "audio": data.get("wav_url"),
            "provider": "tts_api",
        },
        status=200,
    )


# =========================
# ---- 檔案解析：DOCX / ODT / PDF ----
# =========================
def _extract_text_docx(file_obj) -> str:
    from docx import Document
    doc = Document(file_obj)
    lines = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            lines.append(t)
    return "\n".join(lines)


def _extract_text_odt(file_obj) -> str:
    from odf.opendocument import load
    from odf import text as odf_text
    odt = load(file_obj)
    lines = []
    for p in odt.getElementsByType(odf_text.P):
        t = "".join([n.data for n in p.childNodes if getattr(n, "data", None)])
        t = (t or "").strip()
        if t:
            lines.append(t)
    return "\n".join(lines)


def _extract_text_pdf(file_obj) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_obj)
    lines = []
    for page in reader.pages:
        t = (page.extract_text() or "").strip()
        if t:
            lines.append(t)
    return "\n\n".join(lines)


def _extract_text_by_ext(file_obj, filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".docx":
        return _extract_text_docx(file_obj)
    if ext in (".odt",):
        return _extract_text_odt(file_obj)
    if ext == ".pdf":
        return _extract_text_pdf(file_obj)
    raise ValueError(f"unsupported file type: {ext}")


# =========================
# ✅ 來文/附件解析 API
# POST /translator/parse/
# multipart/form-data: attachments (multiple)
# =========================
@csrf_exempt
@require_node("translator", api=True)
def api_parse_attachments(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    files = request.FILES.getlist("attachments")
    if not files:
        return JsonResponse({"ok": False, "error": "no files uploaded"}, status=400)

    max_files = 5
    max_each_mb = 10

    results = []
    combined_parts = []

    for f in files[:max_files]:
        if f.size > max_each_mb * 1024 * 1024:
            results.append({"filename": f.name, "ok": False, "error": f"file too large (>{max_each_mb}MB)"})
            continue

        try:
            text = (_extract_text_by_ext(f, f.name) or "").strip()
            results.append({"filename": f.name, "ok": True, "chars": len(text), "text": text})
            if text:
                combined_parts.append(f"【附件：{f.name}】\n{text}")
        except Exception as e:
            results.append({"filename": f.name, "ok": False, "error": str(e)})

    combined_text = "\n\n".join(combined_parts).strip()
    return JsonResponse({"ok": True, "files": results, "combined_text": combined_text}, status=200)


# =========================
# Helpers（保留你原本 build_prompt）
# =========================
DOC_TYPE_LABEL = {"sign": "簽", "draft": "稿", "report": "報告", "letter": "函"}


def _safe_str(x) -> str:
    return "" if x is None else str(x)


def build_prompt(doc_type: str, requirement: str, examples: list[str]) -> str:
    dt = DOC_TYPE_LABEL.get(doc_type, doc_type)

    example_block = ""
    if examples:
        chunks = []
        for i, ex in enumerate(examples, start=1):
            ex = (ex or "").strip()
            if ex:
                chunks.append(f"【範例 {i}】\n{ex}")
        if chunks:
            example_block = "\n\n".join(chunks)

    prompt = f"""你是一位機關文書與公文寫作專家。
請依照使用者需求，撰寫一份「{dt}」的正式公文草稿，語氣正式、結構清楚、用語一致。
請避免輸出「以下為…」等前言，直接輸出正文。

【使用者需求】
{requirement.strip()}
"""

    if example_block:
        prompt += f"""

【參考範例（請學習其格式與語氣，但不得照抄）】
{example_block}
"""

    prompt += """

【輸出要求】
1. 直接輸出公文正文（不要加標題說明）
2. 內容應包含：主旨、說明（條列）、擬辦（條列）；若需求有附件/期程/經費請明確寫出
3. 文字力求精簡，但要完整可送簽（不要空泛）
"""
    return prompt.strip()


def _as_text(x: Any) -> str:
    if x is None:
        return ""
    if hasattr(x, "content"):
        try:
            return str(x.content or "")
        except Exception:
            pass
    return str(x)


def _llm_provider_tag(llm_obj: object) -> str:
    s = repr(llm_obj)
    if "AutoFallbackChatModel" in s:
        return "auto"
    if "Ollama" in s:
        return "ollama"
    if "ChatOpenAI" in s:
        return "openai"
    # fallback
    return (os.getenv("MODEL_TYPE") or "AUTO").strip().lower()


@csrf_exempt
@require_node("translator", api=True)
def api_translate(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
        if not isinstance(body, dict):
            body = {}
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    text = _safe_str(body.get("text")).strip()
    if not text:
        return JsonResponse({"ok": False, "error": "text is required"}, status=400)

    source_lang = _safe_str(body.get("source_lang")).strip() or "auto"
    target_lang = _safe_str(body.get("target_lang")).strip() or "zh-Hant"

    try:
        temperature = float(body.get("temperature")) if body.get("temperature") is not None else 0.2
    except Exception:
        temperature = 0.2

    try:
        timeout = int(body.get("timeout")) if body.get("timeout") is not None else 120
    except Exception:
        timeout = 120

    try:
        result = translate_core(
            text,
            source_lang=source_lang,
            target_lang=target_lang,
            temperature=temperature,
            timeout=timeout,
        )
        return JsonResponse(result, status=200)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": "internal error", "detail": repr(e)}, status=500)


# =========================
# API: /translator/templates/（GET/POST）
# =========================
@csrf_exempt
@require_node("translator", api=True)
def api_templates(request):
    if request.method == "GET":
        doc_type = request.GET.get("doc_type")
        tag = request.GET.get("tag")

        qs = DocumentTemplate.objects.all()
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        if tag:
            qs = qs.filter(tags__contains=[tag])

        data = [{
            "id": t.id,
            "title": t.title,
            "doc_type": t.doc_type,
            "description": t.description,
            "tags": t.tags or [],
            "content": t.content,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        } for t in qs.order_by("-created_at")]

        return JsonResponse({"ok": True, "templates": data}, status=200)

    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

        title = _safe_str(body.get("title")).strip()
        doc_type = _safe_str(body.get("doc_type")).strip()
        content = _safe_str(body.get("content")).strip()
        description = _safe_str(body.get("description")).strip()

        tags = body.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            return JsonResponse({"ok": False, "error": "tags must be a list"}, status=400)

        cleaned = []
        seen = set()
        for x in tags:
            s = _safe_str(x).strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)

        if not title:
            return JsonResponse({"ok": False, "error": "missing field: title"}, status=400)
        if not doc_type:
            return JsonResponse({"ok": False, "error": "missing field: doc_type"}, status=400)
        if doc_type not in dict(DocumentTemplate.DOC_TYPE_CHOICES):
            return JsonResponse({"ok": False, "error": f"invalid doc_type: {doc_type}"}, status=400)
        if not content:
            return JsonResponse({"ok": False, "error": "missing field: content"}, status=400)

        t = DocumentTemplate.objects.create(
            title=title,
            doc_type=doc_type,
            description=description,
            tags=cleaned,
            content=content,
        )
        return JsonResponse({"ok": True, "message": "created", "id": t.id}, status=201)

    return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)


# =========================
# API: /translator/generate/ （POST JSON）
# 回傳 {ok, prompt, draft, provider}
# ✅ 生成一律走 llm_factory（get_chat_model），不再在 translator 自建 Ollama / OpenAI
# =========================
@csrf_exempt
@require_node("translator", api=True)
def api_generate_doc_prompt(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    doc_type = _safe_str(body.get("doc_type")).strip()
    requirement = _safe_str(body.get("requirement")).strip()
    example_ids = body.get("example_ids", []) or []

    if not isinstance(example_ids, list):
        return JsonResponse({"ok": False, "error": "example_ids must be a list"}, status=400)

    if not doc_type or doc_type not in dict(DocumentTemplate.DOC_TYPE_CHOICES):
        return JsonResponse({"ok": False, "error": "doc_type is required and must be valid"}, status=400)
    if not requirement:
        return JsonResponse({"ok": False, "error": "requirement is required"}, status=400)

    examples = list(
        DocumentTemplate.objects.filter(id__in=example_ids, doc_type=doc_type)
        .values_list("content", flat=True)
    )

    prompt = build_prompt(doc_type=doc_type, requirement=requirement, examples=examples)

    # ✅ 支援前端可帶 temperature/timeout；不帶則讓 llm_factory 用 .env 的 MODEL_* fallback
    temperature = body.get("temperature", None)
    timeout = body.get("timeout", None)

    try:
        temperature = float(temperature) if temperature is not None else None
    except Exception:
        temperature = None

    try:
        timeout = int(timeout) if timeout is not None else None
    except Exception:
        timeout = None

    try:
        llm = get_chat_model(temperature=temperature, timeout=timeout)
        out = llm.invoke(prompt)
        draft = _as_text(out).strip() or "(模型未回傳內容)"
        provider = _llm_provider_tag(llm)

        return JsonResponse(
            {"ok": True, "prompt": prompt, "draft": draft, "provider": provider},
            status=200,
        )
    except Exception as e:
        return JsonResponse(
            {"ok": False, "prompt": prompt, "draft": "(生成失敗)", "provider": "error", "error": str(e)},
            status=500,
        )
