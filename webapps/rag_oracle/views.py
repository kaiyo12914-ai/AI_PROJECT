# webapps/rag_oracle/views.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from webapps.portal.decorators import require_node


# ============================================================
# Lazy import (fail-open)
# - 避免 module import 時就把整站拖死
# - RAG 壞只壞 RAG
# ============================================================
_RAG_IMPORT_ERROR: Optional[str] = None
_RAG_SEARCH = None  # type: ignore


def _get_rag_search():
    global _RAG_IMPORT_ERROR, _RAG_SEARCH

    if _RAG_SEARCH is not None:
        return _RAG_SEARCH, _RAG_IMPORT_ERROR

    try:
        from .retrieve import rag_search  # type: ignore
        _RAG_SEARCH = rag_search
        _RAG_IMPORT_ERROR = None
    except Exception as e:
        _RAG_SEARCH = None
        _RAG_IMPORT_ERROR = str(e)

    return _RAG_SEARCH, _RAG_IMPORT_ERROR


def _parse_post_data(request: HttpRequest) -> Dict[str, Any]:
    """
    同時支援：
    - form POST
    - JSON POST（只接受 object/dict）
    """
    ct = (request.content_type or "").lower()
    if "application/json" in ct:
        try:
            body = (request.body or b"").decode("utf-8", errors="ignore").strip()
            if not body:
                return {}
            obj = json.loads(body)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return request.POST.dict()


# ============================================================
# Pages
# ============================================================
@require_node("rag")
@require_GET
def page(request: HttpRequest) -> HttpResponse:
    return render(request, "rag_oracle/index.html")


# ============================================================
# Health
# ============================================================
@require_node("rag", api=True)
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    # 依規範：health 不能永遠 ok=True，必須呈現「是否可用」
    try:
        from .rag_settings import RAG_CONFIG_ERROR, CHROMA_PERSIST_DIR, CHROMA_COLLECTION, TOP_K  # type: ignore
    except Exception as e:
        return JsonResponse(
            {
                "ok": False,
                "service": "rag_oracle",
                "error": "rag_settings_import_failed",
                "detail": str(e),
            },
            status=500,
        )

    rag_search, imp_err = _get_rag_search()

    ok = True
    err: Optional[str] = None
    if RAG_CONFIG_ERROR:
        ok = False
        err = "rag_config_error"
    elif rag_search is None:
        ok = False
        err = "rag_search_import_failed"

    out = {
        "ok": ok,
        "service": "rag_oracle",
        "status": "ready" if ok else "degraded",
        "error": err,
        "detail": (RAG_CONFIG_ERROR or imp_err or ""),
        "chroma_dir": str(CHROMA_PERSIST_DIR),
        "collection": str(CHROMA_COLLECTION),
        "top_k": int(TOP_K),
    }

    # config/import 壞掉時用 503（服務不可用），讓監控更好判斷
    return JsonResponse(out, status=200 if ok else 503)


# ============================================================
# API
# ============================================================
@csrf_exempt
@require_node("rag", api=True)
@require_POST
def api_ask(request: HttpRequest) -> JsonResponse:
    """
    POST /rag/ask/

    input:
      - q: str (required)
      - k: int (optional)

    output:
      { ok, answer, sources, top_k, collection, ... }
    """
    try:
        # 先檢查 rag_settings 狀態（fail-close 只關 RAG）
        from .rag_settings import RAG_CONFIG_ERROR  # type: ignore

        if RAG_CONFIG_ERROR:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "rag_not_ready",
                    "detail": RAG_CONFIG_ERROR,
                },
                status=503,
            )

        rag_search, imp_err = _get_rag_search()
        if rag_search is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "rag_search_not_available",
                    "detail": imp_err or "",
                },
                status=503,
            )

        data = _parse_post_data(request)

        q = str(data.get("q", "")).strip()
        if not q:
            return JsonResponse({"ok": False, "error": "missing q"}, status=400)

        k: Optional[int] = None
        if "k" in data:
            try:
                k = int(data.get("k"))
            except Exception:
                k = None

        result = rag_search(q, k=k)

        if isinstance(result, dict):
            out: Dict[str, Any] = {"ok": True, **result}
        else:
            out = {"ok": True, "result": result}

        return JsonResponse(out)

    except Exception as e:
        # 最後一道保險：任何錯誤都只回 JSON
        return JsonResponse(
            {
                "ok": False,
                "error": "rag_ask_failed",
                "detail": str(e),
            },
            status=500,
        )
