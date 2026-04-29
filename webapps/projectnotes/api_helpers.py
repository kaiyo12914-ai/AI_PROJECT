from __future__ import annotations

import json
from typing import Any, Dict

from django.http import HttpRequest, JsonResponse


def safe_text(v: Any) -> str:
    return "" if v is None else str(v).strip()


def safe_json_response(data: Dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def api_error(message: str, error_code: str = "bad_request", status: int = 400) -> JsonResponse:
    return safe_json_response({"ok": False, "error": str(message), "error_code": error_code}, status=status)


def read_json_body(request: HttpRequest) -> Dict[str, Any]:
    raw = request.body or b""
    if not raw:
        return {}
    try:
        text = raw.decode("utf-8")
        return json.loads(text)
    except UnicodeDecodeError:
        setattr(request, "_bad_utf8_body", True)
        return {}
    except Exception:
        return {}


def to_int(v: Any, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def is_bad_utf8_request(request: HttpRequest) -> bool:
    return bool(getattr(request, "_bad_utf8_body", False))

