from __future__ import annotations

import json
from typing import Any, Dict

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt

from webapps.llm.services import chat_core, translate_core, LLMServiceConfig


def _json_error(message: str, status: int = 400, **extra):
    payload: Dict[str, Any] = {"error": message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:
    try:
        raw = request.body.decode("utf-8")
    except Exception:
        raw = ""

    if not raw.strip():
        return {}

    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return {}
        return obj
    except json.JSONDecodeError:
        return {}


@csrf_exempt
def chat(request: HttpRequest):
    """
    POST /api/chat/
    Body: {"prompt": "...", "enable_rag": true?}
    Response: {"reply": "...", "backend": "..."} or {"error": "..."}
    """
    if request.method != "POST":
        return _json_error("Method not allowed", status=405)

    data = _parse_json_body(request)
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return _json_error("prompt is required", status=400)

    # Default: enable RAG unless caller explicitly disables it.
    enable_rag = bool(data.get("enable_rag", True))

    # Allow caller override for timeout/temperature with safe fallback values.
    temperature = data.get("temperature", None)
    timeout = data.get("timeout", None)
    try:
        temperature = float(temperature) if temperature is not None else 0.2
    except Exception:
        temperature = 0.2
    try:
        timeout = int(timeout) if timeout is not None else 120
    except Exception:
        timeout = 120

    # Service config loads runtime settings (env/base_dir) centrally.
    config = LLMServiceConfig()

    try:
        result = chat_core(
            prompt,
            temperature=temperature,
            timeout=timeout,
            enable_rag=enable_rag,
            config=config,
        )
        return JsonResponse(result, status=200)
    except ValueError as ve:
        return _json_error(str(ve), status=400)
    except Exception as e:
        return _json_error("internal error", status=500, detail=repr(e))


@csrf_exempt
def translate(request: HttpRequest):
    """
    POST /api/translate/
    Body: {"text":"...", "source_lang":"auto", "target_lang":"zh-Hant"}
    Response: {"translated":"...", "backend":"..."} or {"error": "..."}
    """
    if request.method != "POST":
        return _json_error("Method not allowed", status=405)

    data = _parse_json_body(request)
    text_in = (data.get("text") or "").strip()
    if not text_in:
        return _json_error("text is required", status=400)

    source_lang = (data.get("source_lang") or "auto").strip()
    target_lang = (data.get("target_lang") or "zh-Hant").strip()

    temperature = data.get("temperature", None)
    timeout = data.get("timeout", 30)
    try:
        temperature = float(temperature) if temperature is not None else 0.2
    except Exception:
        temperature = 0.2
    try:
        timeout = int(timeout) if timeout is not None else 120
    except Exception:
        timeout = 120

    try:
        result = translate_core(
            text_in,
            source_lang=source_lang,
            target_lang=target_lang,
            temperature=temperature,
            timeout=timeout,
        )
        return JsonResponse(result, status=200)
    except ValueError as ve:
        return _json_error(str(ve), status=400)
    except Exception as e:
        return _json_error("internal error", status=500, detail=repr(e))
