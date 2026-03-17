# webapps/comment/views.py
from __future__ import annotations

import json
import os
from typing import Any, List, Optional

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from webapps.portal.decorators import require_node
from webapps.llm.llm_factory import get_chat_model


# ============================================================
# Pages
# ============================================================
@require_node("comment")
def index(request: HttpRequest) -> HttpResponse:
    """
    comment 主頁（人員績效考核雛形）
    - Template 請使用「靜態資源分離」版本：CSS/JS 外掛 static
    - body 請使用 data-base-url="{{ request.script_name }}"
    """
    return render(request, "comment/performance.html")


# ============================================================
# Helpers
# ============================================================
def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _as_text(x: Any) -> str:
    if x is None:
        return ""
    if hasattr(x, "content"):
        try:
            return str(getattr(x, "content") or "")
        except Exception:
            return ""
    return str(x)


def _llm_provider_tag(llm_obj: object) -> str:
    """
    僅做除錯標籤（不影響核心邏輯）
    """
    s = repr(llm_obj)
    if "AutoFallbackChatModel" in s:
        return "auto"
    if "Ollama" in s:
        return "ollama"
    if "ChatOpenAI" in s:
        return "openai"
    return (os.getenv("MODEL_TYPE") or "auto").strip().lower()


def _truncate_chars(s: str, n: int) -> str:
    s = (s or "").strip()
    if n and n > 0 and len(s) > n:
        return s[:n].rstrip()
    return s


def _read_json(request: HttpRequest) -> Optional[dict]:
    """
    安全讀 JSON（避免空 body / 非 JSON 直接炸）
    - 空 body -> {}
    - 非 JSON -> None
    """
    try:
        raw = request.body or b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _clamp_int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        x = int(v)
    except Exception:
        x = default
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def _norm_traits(traits: Any, *, limit: int = 10) -> List[str]:
    """
    traits 清理：
    - 必須是 list
    - 去空白、去重（case-insensitive）
    - 最多 limit 筆（避免 prompt 膨脹）
    """
    if not isinstance(traits, list):
        return []

    cleaned: List[str] = []
    seen = set()
    for t in traits:
        s = _safe_str(t).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)
        if len(cleaned) >= max(1, int(limit)):
            break
    return cleaned


def _build_prompt(student_name: str, performance_grade: str, traits: List[str], max_chars: int) -> str:
    performance_info = f"績效評等: {performance_grade}" if performance_grade else "未指定績效評等"
    trait_lines = "\n".join([f"- {x}" for x in traits]) if traits else "(未提供其他特質)"

    return (
        f"同仁姓名: {student_name}\n"
        f"{performance_info}\n"
        f"以下是同仁表現特質:\n"
        f"{trait_lines}\n\n"
        f"請將上述同仁表現以軍事風格撰寫評語，字數嚴格限制不得超過{max_chars}字。\n"
        "請避免出現以下前言或句型：\n"
        "- 以下是以軍事風格撰寫的評語：\n"
        "- 以下為…\n"
        "請直接輸出評語內容，勿加標題。"
    ).strip()


# ============================================================
# API: 生成評語
# POST /comment/api/generate_comment/
# JSON:
#   { student_name, traits[], performance_grade, max_chars, temperature, timeout }
# 回傳:
#   { ok, reply, provider, error? , debug? }
# ============================================================
@csrf_exempt  # 目前保留；若要啟用 CSRF，前端需帶 X-CSRFToken
@require_POST
@require_node("comment", api=True)
def api_generate_comment(request: HttpRequest) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    student_name = _safe_str(body.get("student_name")).strip()
    performance_grade = _safe_str(body.get("performance_grade")).strip()

    if not student_name:
        return JsonResponse({"ok": False, "error": "student_name_required"}, status=400)

    traits = _norm_traits(body.get("traits") or [], limit=10)

    if (not traits) and (not performance_grade):
        return JsonResponse({"ok": False, "error": "traits_or_performance_grade_required"}, status=400)

    # max_chars：預設 80；限制 1~120
    max_chars = _clamp_int(body.get("max_chars", 80), default=80, lo=1, hi=120)

    prompt = _build_prompt(student_name, performance_grade, traits, max_chars)

    # 可由前端帶參數；不帶則交給 llm_factory 用預設 / env
    temperature = _to_float(body.get("temperature"))
    timeout: Optional[int]
    try:
        timeout = int(body.get("timeout")) if body.get("timeout") is not None else None
    except Exception:
        timeout = None

    try:
        llm = get_chat_model(temperature=temperature, timeout=timeout)
        out = llm.invoke(prompt)

        reply = _truncate_chars(_as_text(out).strip(), max_chars)
        if not reply:
            reply = "(模型未回傳內容)"

        resp = {
            "ok": True,
            "reply": reply,
            "provider": _llm_provider_tag(llm),
        }

        # ✅ 僅 DEBUG 纔回傳 debug 資訊（避免上線洩漏 prompt）
        if getattr(settings, "DEBUG", False):
            resp["debug"] = {
                "max_chars": max_chars,
                "temperature": temperature,
                "timeout": timeout,
                "traits_count": len(traits),
                "prompt": prompt,
            }

        return JsonResponse(resp, status=200)

    except Exception as e:
        resp = {
            "ok": False,
            "error": str(e),
            "provider": "error",
        }
        if getattr(settings, "DEBUG", False):
            resp["debug"] = {"prompt": prompt}
        return JsonResponse(resp, status=500)
