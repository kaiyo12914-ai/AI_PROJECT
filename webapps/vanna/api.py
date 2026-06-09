from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, is_dataclass
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from webapps.portal.decorators import require_node
from webapps.vanna.models import (
    DataSource,
    QueryLog,
    ReviewQueue,
    SchemaEmbedding,
    SchemaObject,
    TrainingExample,
    VannaTrainingSync,
)
from webapps.vanna.views import is_vanna_admin
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


def _env_name() -> str:
    return str(getattr(settings, "ENV_NAME", "") or "").strip().upper()


def _is_int_env() -> bool:
    return _env_name() == "INT"


def _execution_policy(data_source: DataSource) -> dict[str, Any]:
    if data_source.db_type == "oracle":
        if _is_int_env():
            return {
                "mode": "oracle_execute",
                "can_execute": True,
                "message": "ENV=INT，可於 SQL Guard 通過後執行 Oracle 查詢。",
            }
        return {
            "mode": "sql_only_ext",
            "can_execute": False,
            "message": "ENV=EXT，Oracle 僅產生 SQL，不連線執行查詢。",
        }
    if data_source.db_type == "postgresql":
        return {
            "mode": "metadata_store_only",
            "can_execute": False,
            "message": "PostgreSQL 僅作為 Vanna/NL2SQL metadata 與訓練資料儲存庫，不作為業務查詢目標。",
        }
    return {
        "mode": "unsupported",
        "can_execute": False,
        "message": f"Unsupported data source type: {data_source.db_type}",
    }


def _user_id(request: HttpRequest) -> str:
    return str(
        getattr(request, "login_user_name", "")
        or getattr(getattr(request, "user", None), "username", "")
        or ""
    ).strip()


def _resolve_data_source(data: dict[str, Any]) -> DataSource:
    code = str(data.get("data_source") or data.get("code") or "legacy_vanna_chroma").strip()
    db_type = str(data.get("db_type") or "").strip().lower()
    if not db_type:
        db_type = "postgresql" if code == "default_pg" else "oracle"
    default_schema = str(
        data.get("schema")
        or data.get("default_schema")
        or ("public" if db_type == "postgresql" else "LEGACY")
    ).strip()
    return get_or_create_data_source(
        code=code,
        name=str(data.get("name") or code).strip(),
        db_type=db_type,
        db_profile=str(data.get("db_profile") or "").strip(),
        default_schema=default_schema,
    )


def _parse_ddl_object(ddl_text: str, default_schema: str) -> tuple[str, str, str]:
    patterns = [
        (r"(?is)\bCREATE\s+MATERIALIZED\s+VIEW\s+([\"A-Za-z0-9_.$@]+)", "materialized_view"),
        (r"(?is)\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\"A-Za-z0-9_.$@]+)", "view"),
        (r"(?is)\bCREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+([\"A-Za-z0-9_.$@]+)", "table"),
    ]
    for pattern, object_type in patterns:
        match = re.search(pattern, ddl_text or "")
        if not match:
            continue
        raw_name = match.group(1).strip().strip('"').split("@", 1)[0]
        if "." in raw_name:
            schema_name, object_name = raw_name.rsplit(".", 1)
        else:
            schema_name, object_name = default_schema or "LEGACY", raw_name
        return schema_name.strip('"').upper(), object_name.strip('"').upper(), object_type
    raise ValueError("DDL must contain CREATE TABLE, CREATE VIEW, or CREATE MATERIALIZED VIEW.")


def _content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _documentation_object_name(documentation: str) -> str:
    return f"VANNA_DOCUMENTATION_{_content_hash(documentation)[:16].upper()}"


def _oracle_config_diagnostics(profile: str = "") -> dict[str, Any]:
    try:
        from webapps.database.db_factory import _db_factory_md_path, load_db_config

        cfg = load_db_config("oracle", profile=profile)
        return {
            "profile": profile or "",
            "db_factory_md_path": str(_db_factory_md_path()),
            "has_ora_host": bool(cfg.ora_host),
            "ora_host": cfg.ora_host,
            "ora_port": cfg.ora_port,
            "has_ora_service_name": bool(cfg.ora_service),
            "ora_service_name": cfg.ora_service,
            "has_ora_user": bool(cfg.ora_user),
            "ora_user": cfg.ora_user,
            "has_ora_pass": bool(cfg.ora_pass),
        }
    except Exception as exc:
        return {
            "profile": profile or "",
            "diagnostic_error": f"{type(exc).__name__}: {exc}",
        }


def _positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(number, maximum))


def _schema_search_payload(data_source: DataSource, query: str, limit: int = 20) -> dict[str, Any]:
    clean_query = str(query or "").strip()
    max_items = _positive_int(limit, 20, 100)
    schema_qs = SchemaObject.objects.filter(data_source=data_source, is_enabled=True)
    if clean_query:
        schema_qs = schema_qs.filter(
            Q(schema_name__icontains=clean_query)
            | Q(object_name__icontains=clean_query)
            | Q(description__icontains=clean_query)
            | Q(ddl_text__icontains=clean_query)
        )
    items = [
        {
            "id": obj.id,
            "schema": obj.schema_name,
            "name": obj.object_name,
            "type": obj.object_type,
            "description": obj.description,
            "columns": obj.columns_json or [],
            "column_count": len(obj.columns_json or []),
            "has_ddl": bool(obj.ddl_text),
            "updated_at": obj.updated_at,
        }
        for obj in schema_qs.order_by("schema_name", "object_name")[:max_items]
    ]
    return {
        "data_source": data_source.code,
        "query": clean_query,
        "limit": max_items,
        "items": items,
    }


def _query_logs_payload(request: HttpRequest, data_source: DataSource | None, limit: int = 50) -> dict[str, Any]:
    max_items = _positive_int(limit, 50, 200)
    logs_qs = QueryLog.objects.select_related("data_source")
    if data_source is not None:
        logs_qs = logs_qs.filter(data_source=data_source)
    if not is_vanna_admin(request):
        logs_qs = logs_qs.filter(user_id=_user_id(request))
    items = [
        {
            "id": log.id,
            "data_source": log.data_source.code if log.data_source else "",
            "question": log.question,
            "generated_sql": log.generated_sql,
            "cleaned_sql": log.cleaned_sql,
            "guard_status": log.guard_status,
            "guard_message": log.guard_message,
            "execution_status": log.execution_status,
            "error_message": log.error_message,
            "latency_ms": log.latency_ms,
            "created_at": log.created_at,
        }
        for log in logs_qs.order_by("-created_at")[:max_items]
    ]
    return {"limit": max_items, "items": items}


def _review_payload(review: ReviewQueue) -> dict[str, Any]:
    query_log = review.query_log
    return {
        "id": review.id,
        "query_log_id": query_log.id,
        "data_source": query_log.data_source.code if query_log.data_source else "",
        "question": query_log.question,
        "generated_sql": query_log.generated_sql,
        "suggested_sql": review.suggested_sql,
        "reason": review.reason,
        "status": review.review_status,
        "reviewed_by": review.reviewed_by,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


@require_GET
@require_node("nl2sql", api=True)
def status_api(request: HttpRequest) -> JsonResponse:
    runtime = ensure_vanna_vendor_loaded()
    return JsonResponse(
        {
            "ok": runtime.available,
            "runtime": _payload(runtime),
            "env": _env_name(),
            "policy": {
                "postgresql": "metadata_store_only",
                "oracle": "execute_only_when_ENV_INT",
            },
        }
    )


@require_GET
@require_node("nl2sql", api=True)
def schema_search_api(request: HttpRequest) -> JsonResponse:
    try:
        data_source = _resolve_data_source(dict(request.GET))
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)
    payload = _schema_search_payload(
        data_source,
        str(request.GET.get("q") or request.GET.get("query") or ""),
        _positive_int(request.GET.get("limit"), 20, 100),
    )
    return JsonResponse({"ok": True, "result": payload}, json_dumps_params={"default": str})


@require_GET
@require_node("nl2sql", api=True)
def query_logs_api(request: HttpRequest) -> JsonResponse:
    data_source = None
    code = str(request.GET.get("code") or request.GET.get("data_source") or "").strip()
    if code:
        try:
            data_source = _resolve_data_source(dict(request.GET))
        except Exception as exc:
            return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)
    payload = _query_logs_payload(request, data_source, _positive_int(request.GET.get("limit"), 50, 200))
    return JsonResponse({"ok": True, "result": payload}, json_dumps_params={"default": str})


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def review_create_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can create review queue items."}, status=403)

    body = _json_body(request)
    query_log_id = body.get("query_log_id") or body.get("id")
    if not query_log_id:
        return JsonResponse({"ok": False, "error": "query_log_id is required"}, status=400)

    try:
        query_log = QueryLog.objects.select_related("data_source").get(id=query_log_id)
    except QueryLog.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Query log not found"}, status=404)

    suggested_sql = str(body.get("suggested_sql") or query_log.cleaned_sql or query_log.generated_sql or "").strip()
    reason = str(body.get("reason") or "").strip()

    review, created = ReviewQueue.objects.get_or_create(
        query_log=query_log,
        review_status="pending",
        defaults={
            "reason": reason,
            "suggested_sql": suggested_sql,
            "reviewed_by": _user_id(request),
        },
    )
    if not created:
        changed = False
        if reason and review.reason != reason:
            review.reason = reason
            changed = True
        if suggested_sql and review.suggested_sql != suggested_sql:
            review.suggested_sql = suggested_sql
            changed = True
        reviewer = _user_id(request)
        if reviewer and review.reviewed_by != reviewer:
            review.reviewed_by = reviewer
            changed = True
        if changed:
            review.save(update_fields=["reason", "suggested_sql", "reviewed_by", "updated_at"])

    return JsonResponse(
        {"ok": True, "created": created, "result": _review_payload(review)},
        status=201 if created else 200,
        json_dumps_params={"default": str},
    )


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def schema_sync_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can manage schema sync."}, status=403)

    body = _json_body(request)
    try:
        data_source = _resolve_data_source(body)
        if data_source.db_type == "oracle" and not _is_int_env():
            return JsonResponse(
                {
                    "ok": False,
                    "error": "ENV=EXT 不允許連線同步 Oracle schema；請使用已匯入的 Vanna training data，或切換 ENV=INT 後再同步。",
                    "env": _env_name(),
                    "policy": _execution_policy(data_source),
                },
                status=403,
            )
        result = sync_schema(data_source)
        return JsonResponse({"ok": True, "result": _payload(result)})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def training_sync_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can manage training sync."}, status=403)

    body = _json_body(request)
    try:
        data_source = _resolve_data_source(body)
        result = sync_training(data_source)
        return JsonResponse({"ok": True, "result": _payload(result)})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


def _training_dataset_payload(data_source: DataSource) -> dict[str, Any]:
    schema_qs = SchemaObject.objects.filter(data_source=data_source)
    examples_qs = TrainingExample.objects.filter(data_source=data_source)
    sync_qs = VannaTrainingSync.objects.filter(data_source=data_source)
    doc_qs = SchemaEmbedding.objects.filter(
        schema_object__data_source=data_source,
        chunk_type="documentation",
    ).select_related("schema_object")

    schema_items = [
        {
            "id": obj.id,
            "schema": obj.schema_name,
            "name": obj.object_name,
            "type": obj.object_type,
            "enabled": obj.is_enabled,
            "columns": len(obj.columns_json or []),
            "description": obj.description,
            "updated_at": obj.updated_at,
        }
        for obj in schema_qs.order_by("schema_name", "object_name")[:30]
    ]
    example_items = [
        {
            "id": ex.id,
            "question": ex.question,
            "sql": ex.sql_text,
            "dialect": ex.dialect,
            "status": ex.review_status,
            "created_by": ex.created_by,
            "updated_at": ex.updated_at,
        }
        for ex in examples_qs.order_by("-updated_at")[:30]
    ]
    sync_items = [
        {
            "id": item.id,
            "type": item.sync_type,
            "status": item.sync_status,
            "training_id": item.vanna_training_id,
            "error": item.error_message,
            "updated_at": item.updated_at,
        }
        for item in sync_qs.order_by("-updated_at")[:30]
    ]
    documentation_items = [
        {
            "id": item.id,
            "schema": item.schema_object.schema_name,
            "name": item.schema_object.object_name,
            "documentation": item.chunk_text,
            "created_at": item.created_at,
        }
        for item in doc_qs.order_by("-created_at")[:30]
    ]
    return {
        "data_source": {
            "code": data_source.code,
            "name": data_source.name,
            "db_type": data_source.db_type,
            "db_profile": data_source.db_profile,
            "schema": data_source.default_schema,
        },
        "summary": {
            "schema_objects": schema_qs.count(),
            "enabled_schema_objects": schema_qs.filter(is_enabled=True).count(),
            "training_examples": examples_qs.count(),
            "approved_examples": examples_qs.filter(review_status="approved").count(),
            "vanna_sync_records": sync_qs.count(),
            "synced_records": sync_qs.filter(sync_status="synced").count(),
            "failed_records": sync_qs.filter(sync_status="failed").count(),
            "ddl_items": schema_qs.exclude(ddl_text="").count(),
            "documentation_items": doc_qs.count(),
        },
        "schema_objects": schema_items,
        "documentation_items": documentation_items,
        "training_examples": example_items,
        "vanna_sync_records": sync_items,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_node("nl2sql", api=True)
def training_dataset_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can manage training dataset."}, status=403)

    body = _json_body(request) if request.method == "POST" else {}
    params = request.GET if request.method == "GET" else body
    try:
        data_source = _resolve_data_source(dict(params))
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

    if request.method == "GET":
        return JsonResponse({"ok": True, "result": _training_dataset_payload(data_source)}, json_dumps_params={"default": str})

    training_type = str(body.get("training_type") or body.get("type") or "sql").strip().lower()
    if training_type not in {"ddl", "documentation", "sql"}:
        return JsonResponse({"ok": False, "error": "training_type must be ddl, documentation, or sql"}, status=400)

    if training_type == "ddl":
        ddl_text = str(body.get("ddl") or body.get("ddl_text") or "").strip()
        if not ddl_text:
            return JsonResponse({"ok": False, "error": "ddl is required"}, status=400)
        try:
            schema_name, object_name, object_type = _parse_ddl_object(ddl_text, data_source.default_schema)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        schema_obj, _ = SchemaObject.objects.update_or_create(
            data_source=data_source,
            schema_name=schema_name,
            object_name=object_name,
            defaults={
                "object_type": object_type,
                "ddl_text": ddl_text,
                "is_enabled": True,
            },
        )
        SchemaEmbedding.objects.update_or_create(
            schema_object=schema_obj,
            chunk_type="ddl",
            content_hash=_content_hash(ddl_text),
            defaults={
                "chunk_text": ddl_text,
                "embedding": None,
                "embedding_model": "",
            },
        )
        return JsonResponse(
            {
                "ok": True,
                "result": {
                    "id": schema_obj.id,
                    "training_type": "ddl",
                    "schema": schema_obj.schema_name,
                    "name": schema_obj.object_name,
                    "type": schema_obj.object_type,
                },
            }
        )

    if training_type == "documentation":
        documentation = str(body.get("documentation") or "").strip()
        title = str(body.get("title") or "").strip()
        if not documentation:
            return JsonResponse({"ok": False, "error": "documentation is required"}, status=400)
        content = f"{title}\n{documentation}".strip() if title else documentation
        object_name = _documentation_object_name(content)
        doc_obj, _ = SchemaObject.objects.update_or_create(
            data_source=data_source,
            schema_name=data_source.default_schema or "LEGACY",
            object_name=object_name,
            defaults={
                "object_type": "view",
                "description": content,
                "columns_json": [],
                "ddl_text": "",
                "is_enabled": True,
            },
        )
        doc_embedding, _ = SchemaEmbedding.objects.update_or_create(
            schema_object=doc_obj,
            chunk_type="documentation",
            content_hash=_content_hash(content),
            defaults={
                "chunk_text": content,
                "embedding": None,
                "embedding_model": "",
            },
        )
        return JsonResponse(
            {
                "ok": True,
                "result": {
                    "id": doc_embedding.id,
                    "training_type": "documentation",
                    "name": doc_obj.object_name,
                    "documentation": content,
                },
            }
        )

    question = str(body.get("question") or "").strip()
    sql_text = str(body.get("sql") or "").strip()
    if not question or not sql_text:
        return JsonResponse({"ok": False, "error": "question and sql are required"}, status=400)

    from webapps.vanna.sql_guard import validate_sql

    is_safe, guard_err = validate_sql(sql_text)
    if not is_safe:
        return JsonResponse({"ok": False, "error": f"SQL blocked by SQL Guard: {guard_err}"}, status=403)

    created_by = _user_id(request)
    example = TrainingExample.objects.create(
        data_source=data_source,
        question=question,
        sql_text=sql_text,
        dialect="oracle" if data_source.db_type == "oracle" else "postgresql",
        review_status="approved",
        created_by=created_by,
        tags_json=body.get("tags") if isinstance(body.get("tags"), list) else [],
    )
    return JsonResponse(
        {
            "ok": True,
            "result": {
                "id": example.id,
                "question": example.question,
                "sql": example.sql_text,
                "status": example.review_status,
            },
        }
    )


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def admin_sql_execute_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can execute SQL tests."}, status=403)

    body = _json_body(request)
    sql = str(body.get("sql") or "").strip()
    if not sql:
        return JsonResponse({"ok": False, "error": "SQL statement is required"}, status=400)

    try:
        data_source = _resolve_data_source(body)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

    from webapps.vanna.sql_guard import validate_sql

    is_safe, guard_err = validate_sql(sql)
    if not is_safe:
        return JsonResponse({"ok": False, "error": f"SQL blocked by SQL Guard: {guard_err}"}, status=403)

    if not data_source.enabled:
        return JsonResponse({"ok": False, "error": "Data source is disabled"}, status=403)

    policy = _execution_policy(data_source)
    try:
        max_rows = int(body.get("max_rows") or getattr(settings, "NL2SQL_DEFAULT_ROW_LIMIT", 100) or 100)
    except (TypeError, ValueError):
        max_rows = int(getattr(settings, "NL2SQL_DEFAULT_ROW_LIMIT", 100) or 100)
    max_limit = int(getattr(settings, "NL2SQL_MAX_ROW_LIMIT", 1000) or 1000)
    max_rows = max(1, min(max_rows, max_limit))

    if data_source.db_type == "postgresql":
        return JsonResponse({"ok": False, "error": policy["message"], "policy": policy}, status=403)

    if data_source.db_type == "oracle" and not _is_int_env():
        return JsonResponse(
            {
                "ok": True,
                "sql_only": True,
                "sql": sql,
                "columns": [],
                "rows": [],
                "latency_ms": 0,
                "policy": policy,
                "message": policy["message"],
                "max_rows": max_rows,
            }
        )

    started = time.monotonic()
    rows = []
    columns = []
    error_msg = ""

    try:
        if data_source.db_type == "oracle":
            from webapps.database.db_factory import db_connect

            conn = db_connect("oracle", profile=data_source.db_profile)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    if cur.description:
                        columns = [col[0] for col in cur.description]
                    rows = list(cur.fetchmany(max_rows))
            finally:
                conn.close()
        else:
            error_msg = f"Unsupported database type for execution: '{data_source.db_type}'"
    except Exception as exc:
        error_msg = str(exc)

    latency_ms = int((time.monotonic() - started) * 1000)
    if error_msg:
        payload = {"ok": False, "error": error_msg, "policy": policy}
        if "Oracle config incomplete" in error_msg:
            payload["oracle_config"] = _oracle_config_diagnostics(data_source.db_profile)
        return JsonResponse(payload, status=500)

    return JsonResponse(
        {
            "ok": True,
            "columns": columns,
            "rows": rows,
            "is_mock": False,
            "sql_only": False,
            "latency_ms": latency_ms,
            "policy": policy,
            "max_rows": max_rows,
        }
    )


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
        payload = _generate_payload(result, include_prompt=bool(body.get("debug_prompt")))
        payload["execution_policy"] = _execution_policy(data_source)
        payload["env"] = _env_name()
        return JsonResponse({"ok": True, "result": payload})
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


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

    try:
        data_source = qlog.data_source if qlog else _resolve_data_source(body)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

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

    policy = _execution_policy(data_source)
    if data_source.db_type == "postgresql":
        if qlog:
            qlog.final_sql = sql
            qlog.execution_status = "blocked_metadata_store_only"
            qlog.error_message = policy["message"]
            qlog.save()
        return JsonResponse({"ok": False, "error": policy["message"], "policy": policy}, status=403)

    if data_source.db_type == "oracle" and not _is_int_env():
        if qlog:
            qlog.final_sql = sql
            qlog.execution_status = "not_executed_ext_sql_only"
            qlog.error_message = ""
            qlog.save()
        return JsonResponse(
            {
                "ok": True,
                "sql_only": True,
                "sql": sql,
                "columns": [],
                "rows": [],
                "latency_ms": 0,
                "policy": policy,
                "message": policy["message"],
            }
        )

    started = time.monotonic()
    rows = []
    columns = []
    error_msg = ""
    latency_ms = 0

    try:
        if data_source.db_type == "oracle":
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
        return JsonResponse({"ok": False, "error": error_msg, "policy": policy}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "columns": columns,
            "rows": rows,
            "is_mock": False,
            "sql_only": False,
            "latency_ms": latency_ms,
            "policy": policy,
        }
    )
