# webapps/meetingreply/views.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.llm.llm_factory import get_chat_model
from webapps.portal.decorators import require_node
from webapps.doc.utils_login import get_login_user_idno

# ✅ 直接呼叫 rag_search（不走 HTTP）
try:
    from webapps.rag_oracle.retrieve import rag_search  # type: ignore
except Exception as e:
    rag_search = None  # type: ignore
    _RAG_IMPORT_ERROR = str(e)
else:
    _RAG_IMPORT_ERROR = ""


# ============================================================
# helpers: env / request.script_name
# ============================================================
def _env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d).strip()


def _env_int(k: str, d: int) -> int:
    try:
        return int((_env(k, str(d)) or str(d)).strip())
    except Exception:
        return d


def _env_float(k: str, d: float) -> float:
    try:
        return float((_env(k, str(d)) or str(d)).strip())
    except Exception:
        return d


def _env_bool(k: str, d: bool = False) -> bool:
    v = (_env(k, "1" if d else "0") or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _ensure_request_script_name(request: HttpRequest) -> str:
    """
    ✅ 專案規範：模板用 {{ request.script_name }} 組 apiUrl base
    - Django 原生不一定有 request.script_name
    - 這裡統一補上（fail-open）
    """
    v = getattr(request, "script_name", None)
    if isinstance(v, str):
        return v

    script = (request.META.get("SCRIPT_NAME") or "").strip()

    if not script:
        fsn = getattr(settings, "FORCE_SCRIPT_NAME", None)
        if isinstance(fsn, str):
            script = fsn.strip()

    if script and not script.startswith("/"):
        script = "/" + script

    setattr(request, "script_name", script)
    return script


def _safe_json_body(request: HttpRequest) -> Dict[str, Any]:
    try:
        body = request.body.decode("utf-8", errors="ignore").strip()
        if not body:
            return {}
        obj = json.loads(body)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _as_int(
    v: Any,
    default: int,
    *,
    min_v: Optional[int] = None,
    max_v: Optional[int] = None,
) -> int:
    try:
        n = int(v)
    except Exception:
        n = default
    if min_v is not None and n < min_v:
        n = min_v
    if max_v is not None and n > max_v:
        n = max_v
    return n


def _json_ok(**payload: Any) -> JsonResponse:
    p: Dict[str, Any] = {"ok": True}
    p.update(payload)
    return JsonResponse(p)


def _json_err(msg: str, *, status: int = 400, **payload: Any) -> JsonResponse:
    p: Dict[str, Any] = {"ok": False, "error": msg}
    p.update(payload)
    return JsonResponse(p, status=status)


def _normalize_sources(raw: Any) -> List[Dict[str, Any]]:
    """
    rag_search 的 sources/hits 可能是：
    - list[dict]
    - dict[key->dict]
    - 其他：當作空
    統一轉成 list[dict]，讓前端穩定渲染。
    """
    if isinstance(raw, list):
        out: List[Dict[str, Any]] = []
        for x in raw:
            if isinstance(x, dict):
                out.append(x)
        return out

    if isinstance(raw, dict):
        out2: List[Dict[str, Any]] = []
        for k, v in raw.items():
            if isinstance(v, dict):
                h = dict(v)
                h.setdefault("id", k)
                h.setdefault("doc_id", h.get("doc_id") or k)
                out2.append(h)
        return out2

    return []


def _extract_todo_items(raw: Any) -> List[Any]:
    """
    Normalize remote todo payload into a flat list.
    Supports:
    - list
    - dict with items/rows/data/list/result
    - nested dict: result.items / result.rows / result.data / result.list
    """
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []

    for key in ("items", "rows", "data", "list", "result"):
        val = raw.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            for sub_key in ("items", "rows", "data", "list", "result"):
                sub_val = val.get(sub_key)
                if isinstance(sub_val, list):
                    return sub_val
    return []


# ============================================================
# RAG settings
# ============================================================
RAG_TOP_K = _env_int("RAG_TOP_K", 10)

# auto injection policy（保留計算給 UI 顯示；但沒勾選不注入）
RAG_BASE_MAX_DIST = _env_float("RAG_BASE_MAX_DIST", 0.15)
RAG_FALLBACK_MAX_DIST = _env_float("RAG_FALLBACK_MAX_DIST", 0.25)
RAG_FALLBACK_TOP_N = _env_int("RAG_FALLBACK_TOP_N", 2)

# manual override hard limit (server-side)
MANUAL_OVERRIDE_MAX_N = _env_int("MANUAL_OVERRIDE_MAX_N", 2)

RAG_INJECT_MAX_CHARS = _env_int("RAG_INJECT_MAX_CHARS", 1600)


# ============================================================
# page
# ============================================================
@require_node("meetingreply")
def index(request: HttpRequest):
    _ensure_request_script_name(request)
    return render(
        request,
        "meetingreply/index.html",
        {
            "ENV_NAME": _env("ENV", "").strip().upper(),
            "INT_TODO_URL": _env(
                "MEETING_INT_TODO_URL",
                "https://www.mpc.mil.tw/notificationsingleton/WebService/CaseManager/UnHandle_Item_AssignJson.ashx",
            ),
        },
    )


# ============================================================
# API: todo_list (meeting directives)
# ============================================================
@csrf_exempt
@require_node("meetingreply", api=True)
def todo_list(request: HttpRequest):
    if request.method not in ("GET", "POST"):
        return _json_err("Method not allowed", status=405)

    login_user = (get_login_user_idno(request) or "").strip()
    if not login_user:
        return _json_err("missing_login_user", status=401)

    base_url = _env("MEETING_TODO_URL", "")
    if not base_url:
        return _json_err("missing_meeting_todo_url", status=500, hint="set MEETING_TODO_URL")

    param_name = _env("MEETING_TODO_LOGIN_PARAM", "login_user") or "login_user"
    q_param = _env("MEETING_TODO_Q_PARAM", "q") or "q"
    timeout_s = _env_int("MEETING_TODO_TIMEOUT", 10)
    method = (_env("MEETING_TODO_METHOD", "GET") or "GET").strip().upper()

    q = ""
    if request.method == "GET":
        q = (request.GET.get(q_param) or request.GET.get("q") or "").strip()
    else:
        body = _safe_json_body(request)
        q = (body.get(q_param) or body.get("q") or "").strip()

    params: Dict[str, Any] = {param_name: login_user}
    if q:
        params[q_param] = q

    try:
        headers = {"Accept": "application/json"}
        if method == "POST":
            resp = requests.post(base_url, json=params, headers=headers, timeout=timeout_s)
        else:
            resp = requests.get(base_url, params=params, headers=headers, timeout=timeout_s)
    except Exception as e:
        return _json_err("todo_fetch_failed", status=502, detail=str(e))

    if not resp.ok:
        snippet = (resp.text or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        return _json_err(
            "todo_fetch_failed",
            status=502,
            http_status=resp.status_code,
            detail=snippet,
        )

    try:
        data = resp.json()
    except Exception as e:
        snippet = (resp.text or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        return _json_err("todo_invalid_json", status=502, detail=f"{e}: {snippet}")

    items: List[Any] = _extract_todo_items(data)
    if not items and _env_bool("MEETING_TODO_ECHO_SINGLE", False) and isinstance(data, dict):
        items = [data]

    return _json_ok(
        items=items,
        meta={
            "login_user": login_user,
            "count": len(items),
            "source": "remote",
        },
    )

# ============================================================
# rag direct call
# ============================================================
def _rag_ask_direct(q: str, *, k: int) -> Dict[str, Any]:
    """
    依 webapps/rag_oracle/retrieve.py 的 rag_search 簽名：
      rag_search(q, k=None, where=None, include_documents=True)
    """
    if rag_search is None:
        raise RuntimeError(f"rag_search 無法載入：{_RAG_IMPORT_ERROR}")

    q = (q or "").strip()
    if not q:
        return {"ok": True, "sources": [], "top_k": 0}

    k = _as_int(k, RAG_TOP_K, min_v=1, max_v=50)
    return rag_search(q=q, k=k, where=None, include_documents=True)


# =========================
# hit helpers
# =========================
def _meta(h: Dict[str, Any]) -> Dict[str, Any]:
    m = h.get("meta")
    if isinstance(m, dict):
        return m
    m2 = h.get("metadata")
    if isinstance(m2, dict):
        return m2
    return {}


def _get_dist(h: Dict[str, Any]) -> Optional[float]:
    v = h.get("dist", None)
    if isinstance(v, (int, float)):
        return float(v)
    v2 = h.get("distance", None)
    if isinstance(v2, (int, float)):
        return float(v2)
    return None


def _source_key(h: Dict[str, Any]) -> str:
    m = _meta(h)
    return (
        (h.get("doc_id") or "")
        or (h.get("source") or "")
        or (m.get("doc_id") or "")
        or (m.get("source") or "")
        or (h.get("id") or "")
    ).strip()


def _get_title(h: Dict[str, Any]) -> str:
    m = _meta(h)
    return (h.get("title") or m.get("title") or "").strip()


def _get_text(h: Dict[str, Any]) -> str:
    return (h.get("text") or h.get("snippet") or h.get("document") or "").strip()


def _pick_hits_for_injection(
    hits_all: List[Dict[str, Any]],
    *,
    base_max_dist: float,
    fallback_max_dist: float,
    fallback_top_n: int,
) -> Tuple[List[Dict[str, Any]], str]:
    with_dist: List[Dict[str, Any]] = [h for h in hits_all if _get_dist(h) is not None]
    if not with_dist:
        return [], "no_dist_available"

    with_dist.sort(key=lambda x: float(_get_dist(x) or 9e9))
    min_d = float(_get_dist(with_dist[0]) or 9e9)

    base_hits = [h for h in with_dist if float(_get_dist(h) or 9e9) <= base_max_dist]
    if base_hits:
        return base_hits, f"base(dist<={base_max_dist}, picked={len(base_hits)}, min_dist={min_d})"

    cand = [h for h in with_dist if float(_get_dist(h) or 9e9) < fallback_max_dist]
    if cand:
        picked = cand[: max(1, fallback_top_n)]
        return picked, f"fallback_top_n(dist<{fallback_max_dist}, top_n={fallback_top_n}, picked={len(picked)}, min_dist={min_d})"

    return [], f"none(min_dist={min_d}>= {fallback_max_dist})"


def _apply_manual_injection_override(
    hits_all: List[Dict[str, Any]],
    manual_sources: List[str],
    *,
    limit: int,
) -> Tuple[List[Dict[str, Any]], str]:
    want = [str(s).strip() for s in (manual_sources or []) if str(s).strip()]
    if not want:
        return [], "manual:none"

    if len(want) > max(1, limit):
        want = want[: max(1, limit)]

    want_set = set(want)

    picked: List[Dict[str, Any]] = []
    for h in hits_all:
        k = _source_key(h)
        if k and k in want_set:
            picked.append(h)
            if len(picked) >= max(1, limit):
                break

    return picked, f"manual:override(picked={len(picked)}/req={len(want)}, limit={limit})"


def _build_rag_context_from_hits(hits: List[Dict[str, Any]], *, max_chars: int) -> str:
    blocks: List[str] = []
    for i, h in enumerate((hits or [])[:10], start=1):
        title = _get_title(h)
        snippet = _get_text(h)
        dist = _get_dist(h)
        source = _source_key(h)

        header = f"[{i}]"
        if title:
            header += f" {title}"
        if dist is not None:
            header += f" (dist={dist})"
        if source:
            header += f" | {source}"

        blocks.append(header + ("\n" + snippet if snippet else ""))

    ctx = "\n\n".join(blocks).strip()
    if max_chars > 0 and len(ctx) > max_chars:
        ctx = ctx[: max_chars - 50] + "\n\n（…已截斷）"
    return ctx


def _build_supporting_injection(staff: str, rag_context: str) -> str:
    staff = (staff or "").strip()
    rag_context = (rag_context or "").strip()
    parts: List[str] = []
    parts.append("【參謀想法】\n" + (staff if staff else "（未提供）"))
    parts.append("【RAG 參考資料】\n" + (rag_context if rag_context else "（無）"))
    return "\n\n".join(parts).strip()


def _build_prompt_short(directive: str, injection: str) -> str:
    return f"""
你是機關幕僚助理，請依下列資訊，產生一份正式、可呈報的「會議彙辦事項擬答（簡要版）」。
請使用繁體中文，語氣正式。

【一、指裁示事項】
{directive if directive else "（未提供）"}

【二、參考注入資訊（參謀想法 + RAG）】
{injection if injection else "（無）"}

要求：
- 200個繁體中文字以內（含標點）
- 直接輸出擬答內容，不要輸出提示詞
- 單一段落輸出（不可使用條列、編號、換行）
- 語氣正式、可呈報
- 直接輸出內容，無需重複描述指裁示事項（不要加任何標題/前綴/說明）
""".strip()


def _build_prompt_long(directive: str, injection: str) -> str:
    return f"""
你是機關幕僚助理，請依下列資訊，產生一份正式、可呈報的「會議彙辦事項擬答（詳答版）」。
請使用繁體中文，語氣正式。

【一、指裁示事項】
{directive if directive else "（未提供）"}

【二、參考注入資訊（參謀想法 + RAG）】
{injection if injection else "（無）"}

要求：
- 400個繁體中文字以內（含標點）
- 直接輸出擬答內容，不要輸出提示詞
- 語氣正式、可呈報
- 分段時請換行並標註一、二、...
- 直接輸出內容，無需重複描述指裁示事項（不要加任何標題/前綴/說明）
""".strip()


def _llm_text(x: Any) -> str:
    if hasattr(x, "content"):
        try:
            return str(getattr(x, "content") or "").strip()
        except Exception:
            return str(x).strip()
    return str(x).strip()


# ============================================================
# API: rag_only
# ============================================================
@csrf_exempt
@require_node("meetingreply", api=True)
def rag_only(request: HttpRequest):
    if request.method != "POST":
        return _json_err("Method not allowed", status=405)

    data = _safe_json_body(request)
    q = (data.get("q") or "").strip()
    k = _as_int(data.get("k"), RAG_TOP_K, min_v=1, max_v=50)

    if not q:
        return _json_ok(
            rag_ok=True,
            sources=[],
            hits_count=0,
            top_k=k,
            service="rag_oracle:direct",
            note="empty_query",
        )

    try:
        rag = _rag_ask_direct(q, k=k)

        if not bool(rag.get("ok", False)):
            # rag_only：讓前端明確看到錯誤（保留你原設計）
            return _json_err(
                rag.get("error") or "rag_search_failed",
                status=500,
                service="rag_oracle:direct",
                collection=rag.get("collection", ""),
                count=rag.get("count", None),
                persist_dir=rag.get("persist_dir", ""),
            )

        hits_all = _normalize_sources(rag.get("sources") or rag.get("hits") or [])

        return _json_ok(
            rag_ok=True,
            sources=hits_all,
            hits_count=len(hits_all),
            top_k=int(rag.get("top_k") or k),
            service="rag_oracle:direct",
            collection=rag.get("collection", ""),
            count=rag.get("count", None),
            persist_dir=rag.get("persist_dir", ""),
        )

    except Exception as e:
        return _json_err(str(e), status=500, service="rag_oracle:direct")


# ✅ 相容別名：解掉你目前 template/JS 的 {% url 'api_rag_only' %} / reverse('api_rag_only')
api_rag_only = rag_only


# ============================================================
# API: build_reply
# ============================================================
@csrf_exempt
@require_node("meetingreply", api=True)
def build_reply(request: HttpRequest):
    if request.method != "POST":
        return _json_err("Method not allowed", status=405)

    data = _safe_json_body(request)
    directive = (data.get("directive") or "").strip()
    staff = (data.get("staff") or "").strip()

    if not directive:
        return _json_err("directive_required", status=400)

    manual_sources_raw = data.get("manual_inject_sources") or []
    manual_sources: List[str] = []
    if isinstance(manual_sources_raw, list):
        manual_sources = [str(x).strip() for x in manual_sources_raw if str(x).strip()]

    manual_mode = (data.get("manual_inject_mode") or "").strip()  # "override" or ""

    rag_payload: Dict[str, Any] = {
        "ok": False,
        "rag_ok": False,
        "query": "",
        "note": "",
        "hits": [],
        "hits_count": 0,
        "auto_hits": [],
        "auto_note": "",
        "hits_injected": [],
        "context": "",
        "error": "",
        "service": "rag_oracle:direct",
        "collection": "",
        "count": None,
        "persist_dir": "",
    }

    rag_query = directive or staff
    rag_payload["query"] = rag_query

    if not rag_query:
        rag_payload.update(
            {
                "ok": True,
                "rag_ok": True,
                "note": "empty_query",
                "hits": [],
                "hits_count": 0,
                "auto_hits": [],
                "hits_injected": [],
                "context": "",
            }
        )
    else:
        try:
            rag = _rag_ask_direct(rag_query, k=RAG_TOP_K)

            rag_payload["collection"] = rag.get("collection", "")
            rag_payload["count"] = rag.get("count", None)
            rag_payload["persist_dir"] = rag.get("persist_dir", "")

            rag_ok = bool(rag.get("ok", False))
            rag_payload["rag_ok"] = rag_ok

            if not rag_ok:
                # ✅ build_reply：fail-open（仍可用 staff/directive 生成）
                rag_payload["ok"] = False
                rag_payload["error"] = rag.get("error") or "rag_search_failed"
                rag_payload["note"] = "rag_failed"
                hits_all: List[Dict[str, Any]] = []
            else:
                hits_all = _normalize_sources(rag.get("sources") or rag.get("hits") or [])

                rag_payload["ok"] = True
                rag_payload["hits"] = hits_all
                rag_payload["hits_count"] = len(hits_all)
                rag_payload["note"] = "no_hits" if len(hits_all) == 0 else ""

                auto_hits, auto_note = _pick_hits_for_injection(
                    hits_all,
                    base_max_dist=RAG_BASE_MAX_DIST,
                    fallback_max_dist=RAG_FALLBACK_MAX_DIST,
                    fallback_top_n=RAG_FALLBACK_TOP_N,
                )
                rag_payload["auto_hits"] = auto_hits
                rag_payload["auto_note"] = auto_note

                if manual_mode == "override" and manual_sources:
                    manual_hits, manual_note = _apply_manual_injection_override(
                        hits_all,
                        manual_sources,
                        limit=MANUAL_OVERRIDE_MAX_N,
                    )
                    injected = manual_hits
                    rag_payload["note"] = manual_note
                else:
                    injected = []
                    rag_payload["note"] = "manual:none"

                rag_payload["hits_injected"] = injected
                rag_payload["context"] = _build_rag_context_from_hits(
                    injected, max_chars=RAG_INJECT_MAX_CHARS
                )

        except Exception as e:
            rag_payload["ok"] = False
            rag_payload["rag_ok"] = False
            rag_payload["error"] = str(e)
            rag_payload["note"] = "rag_exception"

    try:
        llm = get_chat_model()
        rag_context = str(rag_payload.get("context") or "")
        injection = _build_supporting_injection(staff, rag_context)

        prompt_short = _build_prompt_short(directive, injection)
        prompt_long = _build_prompt_long(directive, injection)

        short_out = _llm_text(llm.invoke(prompt_short))
        long_out = _llm_text(llm.invoke(prompt_long))

        return _json_ok(
            short=short_out,
            long=long_out,
            rag=rag_payload,
            meta={"short_len": len(short_out), "long_len": len(long_out)},
        )
    except Exception as e:
        return _json_err(str(e), status=500, rag=rag_payload)
