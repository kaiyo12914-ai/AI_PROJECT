from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from webapps.portal.decorators import require_node
from webapps.vanna.models import DataSource, QueryLog
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


def _is_ext_env() -> bool:
    import os
    return (os.getenv("ENV") or "").strip().upper() == "EXT"


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def execute_api(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    qlog_id = body.get("query_log_id")
    sql = body.get("sql")

    qlog = None
    if qlog_id:
        try:
            qlog = QueryLog.objects.get(id=qlog_id)
            sql = qlog.cleaned_sql or qlog.generated_sql
        except QueryLog.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Query log not found"}, status=404)

    sql = (sql or "").strip()
    if not sql:
        return JsonResponse({"ok": False, "error": "SQL statement is required"}, status=400)

    data_source = None
    try:
        data_source = qlog.data_source if qlog else _resolve_data_source(body)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

    # 1. 重新執行 SQL Guard 安全審查（雙重把關）
    from webapps.vanna.sql_guard import validate_sql
    is_safe, guard_err = validate_sql(sql)
    if not is_safe:
        if qlog:
            qlog.guard_status = "blocked"
            qlog.guard_message = guard_err
            qlog.save()
        return JsonResponse({"ok": False, "error": f"SQL blocked by SQL Guard: {guard_err}"}, status=403)

    if not data_source.enabled:
        return JsonResponse({"ok": False, "error": "Data source is disabled"}, status=403)

    # 2. 處理 ENV=EXT 與非 PostgreSQL 的 MOCK 執行
    is_mock = False
    mock_rows = []
    mock_columns = []

    if data_source.db_type != "postgresql" and _is_ext_env():
        is_mock = True
        mock_columns = ["ID", "NAME", "VAL", "STATUS", "MOCK_MESSAGE"]
        mock_rows = [
            [1, "Mock Record A", 100.5, "ACTIVE", "Running in ENV=EXT mode; physical connection is mocked."],
            [2, "Mock Record B", 200.0, "PENDING", "For security and compliance, non-PostgreSQL external DBs are mocked."],
            [3, "Mock Record C", 300.75, "INACTIVE", "Physical queries are only performed when ENV=INT."],
        ]

    import time
    started = time.monotonic()
    rows = []
    columns = []
    error_msg = ""
    latency_ms = 0

    if is_mock:
        rows = mock_rows
        columns = mock_columns
        latency_ms = 1
    else:
        # 3. 實體資料庫查詢（依資料庫類型區分，手動提取 description）
        try:
            if data_source.db_type == "postgresql":
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    if cursor.description:
                        columns = [col[0] for col in cursor.description]
                    rows = list(cursor.fetchall())
            elif data_source.db_type == "oracle":
                from webapps.database.db_factory import db_connect
                conn = db_connect("oracle", profile=data_source.db_profile)
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        if cur.description:
                            columns = [col[0] for col in cur.description]
                        rows = list(cur.fetchall())
                finally:
                    conn.close()
            else:
                error_msg = f"Unsupported database type for execution: '{data_source.db_type}'"

            latency_ms = int((time.monotonic() - started) * 1000)
        except Exception as exc:
            error_msg = str(exc)
            latency_ms = int((time.monotonic() - started) * 1000)

    # 4. 更新日誌與回傳
    if qlog:
        qlog.final_sql = sql
        qlog.latency_ms = (qlog.latency_ms or 0) + latency_ms
        if error_msg:
            qlog.execution_status = "failed"
            qlog.error_message = error_msg
        else:
            qlog.execution_status = "success"
            qlog.row_count = len(rows)
        qlog.save()

    if error_msg:
        return JsonResponse({"ok": False, "error": error_msg}, status=500)

    return JsonResponse({
        "ok": True,
        "columns": columns,
        "rows": rows,
        "is_mock": is_mock,
        "latency_ms": latency_ms
    })

