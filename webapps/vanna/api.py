from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from webapps.portal.decorators import require_node
from webapps.vanna.models import DataSource
from webapps.vanna.vanna_adapter import (
    ensure_vanna_vendor_loaded,
    generate_sql,
    get_or_create_data_source,
    sync_schema,
    sync_training,
)


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _payload(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    return dict(getattr(obj, "__dict__", {}) or {})


def _generate_payload(result: Any, *, include_prompt: bool = False) -> dict[str, Any]:
    data = _payload(result)
    prompt = str(data.pop("prompt", "") or "")
    data["prompt_chars"] = len(prompt)
    if include_prompt:
        data["prompt"] = prompt
    return data


def _user_id(request: HttpRequest) -> str:
    return str(
        getattr(request, "login_user_name", "")
        or getattr(getattr(request, "user", None), "username", "")
        or ""
    ).strip()


def _resolve_data_source(data: dict[str, Any]) -> DataSource:
    code = str(data.get("data_source") or data.get("code") or "default_pg").strip()
    db_type = str(data.get("db_type") or "postgresql").strip().lower()
    default_schema = str(data.get("schema") or data.get("default_schema") or ("public" if db_type == "postgresql" else "")).strip()
    return get_or_create_data_source(
        code=code,
        name=str(data.get("name") or code).strip(),
        db_type=db_type,
        db_profile=str(data.get("db_profile") or "").strip(),
        default_schema=default_schema,
    )


@require_GET
@require_node("nl2sql", api=True)
def status_api(request: HttpRequest) -> JsonResponse:
    runtime = ensure_vanna_vendor_loaded()
    return JsonResponse({"ok": runtime.available, "runtime": _payload(runtime)})


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def schema_sync_api(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    try:
        data_source = _resolve_data_source(body)
        result = sync_schema(data_source)
        return JsonResponse({"ok": True, "result": _payload(result)})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def training_sync_api(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    try:
        data_source = _resolve_data_source(body)
        result = sync_training(data_source)
        return JsonResponse({"ok": True, "result": _payload(result)})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def generate_api(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    question = str(body.get("question") or "").strip()
    if not question:
        return JsonResponse({"ok": False, "error": "question is required"}, status=400)

    try:
        data_source = _resolve_data_source(body)
        result = generate_sql(data_source, question, user_id=_user_id(request))
        include_prompt = bool(body.get("debug_prompt"))
        return JsonResponse({"ok": True, "result": _generate_payload(result, include_prompt=include_prompt)})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)
