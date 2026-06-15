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

from webapps.common.login_utils import get_login_user_org, normalize_org_code
from webapps.portal.decorators import require_node
from webapps.vanna.models import (
    DataSource,
    QueryLog,
    ReviewQueue,
    SchemaEmbedding,
    SchemaObject,
    TrainingExample,
    VannaTrainingSync,
    ExampleEmbedding,
    FailedQueryRecord,
)
from webapps.vanna.views import _is_named_system_admin, is_vanna_admin
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


def _can_view_sql_command(request: HttpRequest) -> bool:
    return _is_named_system_admin(request)


def _apply_sql_visibility(payload: dict[str, Any], request: HttpRequest, *sql_keys: str) -> dict[str, Any]:
    can_view = _can_view_sql_command(request)
    payload["can_view_sql_command"] = can_view
    payload["sql_hidden"] = not can_view
    if not can_view:
        for key in sql_keys:
            if key in payload:
                payload[key] = ""
    return payload


def _resolve_data_source(data: dict[str, Any]) -> DataSource:
    def _get_first(k: str) -> Any:
        val = data.get(k)
        if isinstance(val, (list, tuple)) and val:
            return val[0]
        return val

    code = str(_get_first("data_source") or _get_first("code") or "legacy_vanna_chroma").strip()
    db_type = str(_get_first("db_type") or "").strip().lower()
    if not db_type:
        db_type = "postgresql" if code == "default_pg" else "oracle"
    default_schema = str(
        _get_first("schema")
        or _get_first("default_schema")
        or ("public" if db_type == "postgresql" else "LEGACY")
    ).strip()
    return get_or_create_data_source(
        code=code,
        name=str(_get_first("name") or code).strip(),
        db_type=db_type,
        db_profile=str(_get_first("db_profile") or "").strip(),
        default_schema=default_schema,
    )


TRAINING_DATASET_AGGREGATE_CODE = "__nl2sql_training_catalog__"
TRAINING_DATASET_SOURCE_CODES = ("nl2sql_oracle_schema", "legacy_vanna_chroma")
TRAINING_DATASET_PRIMARY_CODE = "nl2sql_oracle_schema"


def _training_dataset_sources(data: dict[str, Any]) -> tuple[list[DataSource], DataSource, bool]:
    def _get_first(k: str) -> Any:
        val = data.get(k)
        if isinstance(val, (list, tuple)) and val:
            return val[0]
        return val

    requested_code = str(_get_first("code") or _get_first("data_source") or "").strip()
    if requested_code in ("", TRAINING_DATASET_AGGREGATE_CODE):
        sources = list(DataSource.objects.filter(code__in=TRAINING_DATASET_SOURCE_CODES).order_by("code"))
        if not sources:
            raise ValueError("No training dataset data sources found.")
        primary = next((ds for ds in sources if ds.code == TRAINING_DATASET_PRIMARY_CODE), sources[0])
        return sources, primary, True

    source = _resolve_data_source(data)
    return [source], source, False


def _training_dataset_target_source(
    data: dict[str, Any],
    sources: list[DataSource],
    primary_source: DataSource,
) -> DataSource:
    def _get_first(k: str) -> Any:
        val = data.get(k)
        if isinstance(val, (list, tuple)) and val:
            return val[0]
        return val

    item_source_code = str(_get_first("data_source_code") or _get_first("source_data_source_code") or "").strip()
    if item_source_code:
        for source in sources:
            if source.code == item_source_code:
                return source
        return DataSource.objects.get(code=item_source_code)

    requested_code = str(_get_first("code") or _get_first("data_source") or "").strip()
    if requested_code in ("", TRAINING_DATASET_AGGREGATE_CODE):
        return primary_source

    return _resolve_data_source(data)


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


_FACTORY_SCOPE_MAP: dict[str, set[str]] = {
    "MPC": {"MPC", "202", "205", "209", "401"},
    "202": {"202"},
    "205": {"205"},
    "209": {"209"},
    "401": {"401"},
}

_PII_MASK_COLUMNS = {"IDNO", "EMPNO"}


def _factory_from_question(question: str) -> str:
    text = str(question or "").strip().upper()
    if not text:
        return ""
    if re.search(r"(?<![A-Z0-9])MPC(?![A-Z0-9])", text):
        return "MPC"
    match = re.search(r"(?<!\d)(202|205|209|401)(?:\s*廠)?(?!\d)", text)
    if not match:
        return ""
    return normalize_org_code(match.group(1), default="")


def _validate_factory_scope(request: HttpRequest, question: str) -> tuple[bool, str]:
    if _is_named_system_admin(request):
        return True, ""

    login_org = normalize_org_code(get_login_user_org(request), default="")
    if login_org not in _FACTORY_SCOPE_MAP:
        return True, ""

    requested_factory = _factory_from_question(question)
    if not requested_factory:
        allowed_text = "、".join(sorted(_FACTORY_SCOPE_MAP[login_org], key=lambda x: (x != "MPC", x)))
        return False, f"問題必須明確包含可查詢廠別；您目前僅可查詢：{allowed_text}。"

    if requested_factory not in _FACTORY_SCOPE_MAP[login_org]:
        allowed_text = "、".join(sorted(_FACTORY_SCOPE_MAP[login_org], key=lambda x: (x != "MPC", x)))
        return False, f"login_user_org={login_org} 僅可查詢 {allowed_text} 資料，不能查詢 {requested_factory}。"

    return True, ""


def _mask_last_five(value: Any) -> Any:
    if value is None:
        return value
    text = str(value)
    if not text:
        return text
    if len(text) <= 5:
        return "*****"
    return f"{text[:-5]}*****"


def _mask_ct_employ_pii(sql: str, columns: list[str], rows: list[Any]) -> list[Any]:
    if not re.search(r"\bCT_EMPLOY\b", str(sql or ""), flags=re.IGNORECASE):
        return rows
    if not columns or not rows:
        return rows

    mask_indexes = [idx for idx, col in enumerate(columns) if str(col or "").strip().upper() in _PII_MASK_COLUMNS]
    if not mask_indexes:
        return rows

    masked_rows: list[Any] = []
    for row in rows:
        items = list(row) if isinstance(row, (list, tuple)) else [row]
        for idx in mask_indexes:
            if idx < len(items):
                items[idx] = _mask_last_five(items[idx])
        masked_rows.append(items)
    return masked_rows


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
            | Q(embeddings__chunk_type="ddl", embeddings__chunk_text__icontains=clean_query)
        )
    ddl_embeddings = {
        emb.schema_object_id: emb.chunk_text
        for emb in SchemaEmbedding.objects.filter(
            schema_object__data_source=data_source,
            chunk_type="ddl",
        ).select_related("schema_object")
    }
    items = [
        {
            "id": obj.id,
            "schema": obj.schema_name,
            "name": obj.object_name,
            "type": obj.object_type,
            "description": obj.description,
            "columns": obj.columns_json or [],
            "column_count": len(obj.columns_json or []),
            "has_ddl": bool(obj.ddl_text or ddl_embeddings.get(obj.id, "")),
            "updated_at": obj.updated_at,
        }
        for obj in schema_qs.distinct().order_by("schema_name", "object_name")[:max_items]
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
    items = []
    for log in logs_qs.order_by("-created_at")[:max_items]:
        item = {
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
        items.append(_apply_sql_visibility(item, request, "generated_sql", "cleaned_sql"))
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


def _training_dataset_payload(data_sources: list[DataSource], primary_source: DataSource, all_items: bool = False) -> dict[str, Any]:
    source_codes = [source.code for source in data_sources]
    schema_qs = SchemaObject.objects.filter(data_source__in=data_sources).select_related("data_source")
    examples_qs = TrainingExample.objects.filter(data_source__in=data_sources).select_related("data_source")
    sync_qs = VannaTrainingSync.objects.filter(data_source__in=data_sources).select_related("data_source")
    doc_qs = SchemaEmbedding.objects.filter(
        schema_object__data_source__in=data_sources,
        chunk_type="documentation",
    ).select_related("schema_object", "schema_object__data_source")
    ddl_embedding_qs = SchemaEmbedding.objects.filter(
        schema_object__data_source__in=data_sources,
        chunk_type="ddl",
    ).select_related("schema_object", "schema_object__data_source")
    ddl_embedding_map = {
        item.schema_object_id: item.chunk_text
        for item in ddl_embedding_qs.order_by("created_at")
    }

    schema_list_qs = schema_qs.order_by("data_source__code", "schema_name", "object_name")
    examples_list_qs = examples_qs.order_by("-updated_at")
    sync_list_qs = sync_qs.order_by("-updated_at")
    doc_list_qs = doc_qs.order_by("-created_at")
    failed_qs = FailedQueryRecord.objects.filter(data_source_code__in=source_codes)
    failed_list_qs = failed_qs.order_by("-created_at")

    if not all_items:
        schema_list_qs = schema_list_qs[:30]
        examples_list_qs = examples_list_qs[:30]
        sync_list_qs = sync_list_qs[:30]
        doc_list_qs = doc_list_qs[:30]
        failed_list_qs = failed_list_qs[:30]

    schema_items = [
        {
            "id": obj.id,
            "data_source_code": obj.data_source.code,
            "data_source_name": obj.data_source.name,
            "schema": obj.schema_name,
            "name": obj.object_name,
            "type": obj.object_type,
            "enabled": obj.is_enabled,
            "columns": len(obj.columns_json or []),
            "description": obj.description,
            "ddl": obj.ddl_text or ddl_embedding_map.get(obj.id, ""),
            "updated_at": obj.updated_at,
        }
        for obj in schema_list_qs
    ]
    example_items = [
        {
            "id": ex.id,
            "data_source_code": ex.data_source.code,
            "question": ex.question,
            "sql": ex.sql_text,
            "dialect": ex.dialect,
            "status": ex.review_status,
            "created_by": ex.created_by,
            "updated_at": ex.updated_at,
        }
        for ex in examples_list_qs
    ]
    sync_items = [
        {
            "id": item.id,
            "data_source_code": item.data_source.code,
            "type": item.sync_type,
            "status": item.sync_status,
            "training_id": item.vanna_training_id,
            "error": item.error_message,
            "updated_at": item.updated_at,
        }
        for item in sync_list_qs
    ]
    documentation_items = [
        {
            "id": item.id,
            "data_source_code": item.schema_object.data_source.code,
            "schema": item.schema_object.schema_name,
            "name": item.schema_object.object_name,
            "documentation": item.chunk_text,
            "created_at": item.created_at,
        }
        for item in doc_list_qs
    ]
    failed_items = [
        {
            "id": item.id,
            "data_source_code": item.data_source_code,
            "query_log_id": item.query_log_id,
            "question": item.question,
            "failed_sql": item.failed_sql,
            "error_message": item.error_message,
            "analysis": item.analysis,
            "action_taken": item.action_taken,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in failed_list_qs
    ]
    display_sources = [primary_source] + [source for source in data_sources if source.code != primary_source.code]
    return {
        "data_source": {
            "code": TRAINING_DATASET_AGGREGATE_CODE if len(data_sources) > 1 else primary_source.code,
            "name": " + ".join(source.name for source in display_sources),
            "db_type": primary_source.db_type,
            "db_profile": " + ".join(dict.fromkeys(source.db_profile for source in display_sources if source.db_profile)),
            "schema": "ALL" if len(data_sources) > 1 else primary_source.default_schema,
        },
        "primary_data_source_code": primary_source.code,
        "data_sources": [
            {
                "code": source.code,
                "name": source.name,
                "db_type": source.db_type,
                "db_profile": source.db_profile,
                "schema": source.default_schema,
            }
            for source in data_sources
        ],
        "summary": {
            "schema_objects": schema_qs.count(),
            "enabled_schema_objects": schema_qs.filter(is_enabled=True).count(),
            "training_examples": examples_qs.count(),
            "approved_examples": examples_qs.filter(review_status="approved").count(),
            "vanna_sync_records": sync_qs.count(),
            "synced_records": sync_qs.filter(sync_status="synced").count(),
            "failed_records": sync_qs.filter(sync_status="failed").count(),
            "ddl_items": ddl_embedding_qs.values("schema_object_id").distinct().count(),
            "documentation_items": doc_qs.count(),
        },
        "schema_objects": schema_items,
        "documentation_items": documentation_items,
        "training_examples": example_items,
        "vanna_sync_records": sync_items,
        "failed_queries": failed_items,
    }


@csrf_exempt
@require_http_methods(["GET", "POST", "PUT", "DELETE"])
@require_node("nl2sql", api=True)
def training_dataset_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can manage training dataset."}, status=403)

    body = _json_body(request) if request.method in ("POST", "PUT", "DELETE") else {}
    params = request.GET if request.method == "GET" else body
    try:
        data_sources, primary_source, _aggregate_mode = _training_dataset_sources(dict(params))
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

    if request.method == "GET":
        all_items = str(request.GET.get("all") or "").lower() == "true"
        return JsonResponse({"ok": True, "result": _training_dataset_payload(data_sources, primary_source, all_items=all_items)}, json_dumps_params={"default": str})

    if request.method == "DELETE":
        training_type = str(body.get("training_type") or body.get("type") or "").strip().lower()
        item_id = body.get("id")
        if not item_id:
            return JsonResponse({"ok": False, "error": "id is required for deletion"}, status=400)
        if training_type not in ("ddl", "documentation", "sql", "failed"):
            return JsonResponse({"ok": False, "error": "training_type must be ddl, documentation, sql, or failed"}, status=400)

        if training_type == "ddl":
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                obj = SchemaObject.objects.get(id=item_id, data_source=item_source)
                VannaTrainingSync.objects.filter(data_source=item_source, sync_type="ddl", source_object_id=obj.id).delete()
                obj.delete()
                return JsonResponse({"ok": True})
            except SchemaObject.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"SchemaObject with id {item_id} not found"}, status=404)

        elif training_type == "documentation":
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                emb = SchemaEmbedding.objects.get(id=item_id, chunk_type="documentation", schema_object__data_source=item_source)
                parent_obj = emb.schema_object
                content_hash = emb.content_hash
                VannaTrainingSync.objects.filter(data_source=item_source, sync_type="documentation", content_hash=content_hash).delete()
                emb.delete()
                if parent_obj.object_name.startswith("VANNA_DOCUMENTATION_") and not parent_obj.embeddings.exists():
                    parent_obj.delete()
                return JsonResponse({"ok": True})
            except SchemaEmbedding.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"SchemaEmbedding with id {item_id} not found"}, status=404)

        elif training_type == "sql":
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                ex = TrainingExample.objects.get(id=item_id, data_source=item_source)
                VannaTrainingSync.objects.filter(data_source=item_source, sync_type="example", source_object_id=ex.id).delete()
                ex.delete()
                return JsonResponse({"ok": True})
            except TrainingExample.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"TrainingExample with id {item_id} not found"}, status=404)

        elif training_type == "failed":
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                item = FailedQueryRecord.objects.get(id=item_id, data_source_code=item_source.code)
                item.delete()
                return JsonResponse({"ok": True})
            except FailedQueryRecord.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"FailedQueryRecord with id {item_id} not found"}, status=404)

    if request.method == "PUT":
        training_type = str(body.get("training_type") or body.get("type") or "").strip().lower()
        item_id = body.get("id")
        if not item_id:
            return JsonResponse({"ok": False, "error": "id is required for update"}, status=400)
        if training_type not in ("ddl", "documentation", "sql", "failed"):
            return JsonResponse({"ok": False, "error": "training_type must be ddl, documentation, sql, or failed"}, status=400)

        if training_type == "ddl":
            ddl_text = str(body.get("ddl") or body.get("ddl_text") or "").strip()
            if not ddl_text:
                return JsonResponse({"ok": False, "error": "ddl is required"}, status=400)
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                obj = SchemaObject.objects.get(id=item_id, data_source=item_source)
                schema_name, object_name, object_type = _parse_ddl_object(ddl_text, item_source.default_schema)
                obj.schema_name = schema_name
                obj.object_name = object_name
                obj.object_type = object_type
                obj.ddl_text = ddl_text
                obj.save()

                content_hash = _content_hash(ddl_text)
                SchemaEmbedding.objects.update_or_create(
                    schema_object=obj,
                    chunk_type="ddl",
                    defaults={
                        "chunk_text": ddl_text,
                        "content_hash": content_hash,
                        "embedding": None,
                        "embedding_model": "",
                    }
                )
                VannaTrainingSync.objects.filter(data_source=item_source, sync_type="ddl", source_object_id=obj.id).delete()
                return JsonResponse({"ok": True, "result": {"id": obj.id, "schema": obj.schema_name, "name": obj.object_name}})
            except SchemaObject.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"SchemaObject with id {item_id} not found"}, status=404)
            except ValueError as exc:
                return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        elif training_type == "documentation":
            documentation = str(body.get("documentation") or "").strip()
            title = str(body.get("title") or "").strip()
            if not documentation:
                return JsonResponse({"ok": False, "error": "documentation is required"}, status=400)
            content = f"{title}\n{documentation}".strip() if title else documentation
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                emb = SchemaEmbedding.objects.get(id=item_id, chunk_type="documentation", schema_object__data_source=item_source)
                parent_obj = emb.schema_object
                VannaTrainingSync.objects.filter(data_source=item_source, sync_type="documentation", content_hash=emb.content_hash).delete()

                emb.chunk_text = content
                emb.content_hash = _content_hash(content)
                emb.embedding = None
                emb.embedding_model = ""
                emb.save()

                parent_obj.description = content
                parent_obj.save()

                return JsonResponse({"ok": True, "result": {"id": emb.id, "name": parent_obj.object_name, "documentation": content}})
            except SchemaEmbedding.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"SchemaEmbedding with id {item_id} not found"}, status=404)

        elif training_type == "sql":
            question = str(body.get("question") or "").strip()
            sql_text = str(body.get("sql") or "").strip()
            if not question or not sql_text:
                return JsonResponse({"ok": False, "error": "question and sql are required"}, status=400)

            from webapps.vanna.sql_guard import validate_sql
            is_safe, guard_err = validate_sql(sql_text)
            if not is_safe:
                return JsonResponse({"ok": False, "error": f"SQL blocked by SQL Guard: {guard_err}"}, status=403)

            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                ex = TrainingExample.objects.get(id=item_id, data_source=item_source)
                ex.question = question
                ex.sql_text = sql_text
                if isinstance(body.get("tags"), list):
                    ex.tags_json = body.get("tags")
                ex.save()

                content_hash = _content_hash(f"{question}\n{sql_text}")
                ExampleEmbedding.objects.update_or_create(
                    training_example=ex,
                    data_source=item_source,
                    defaults={
                        "question_text": question,
                        "sql_text": sql_text,
                        "content_hash": content_hash,
                        "embedding": None,
                        "embedding_model": "",
                    }
                )
                VannaTrainingSync.objects.filter(data_source=item_source, sync_type="example", source_object_id=ex.id).delete()
                return JsonResponse({"ok": True, "result": {"id": ex.id, "question": ex.question, "sql": ex.sql_text}})
            except TrainingExample.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"TrainingExample with id {item_id} not found"}, status=404)

        elif training_type == "failed":
            analysis = str(body.get("analysis") or "").strip()
            action_taken = str(body.get("action_taken") or "").strip()
            status = str(body.get("status") or "pending").strip()
            try:
                item_source = _training_dataset_target_source(body, data_sources, primary_source)
                item = FailedQueryRecord.objects.get(id=item_id, data_source_code=item_source.code)
                item.analysis = analysis
                item.action_taken = action_taken
                item.status = status
                if "question" in body:
                    item.question = str(body.get("question") or "").strip()
                if "sql" in body:
                    item.failed_sql = str(body.get("sql") or "").strip()
                item.save()
                return JsonResponse({
                    "ok": True,
                    "result": {
                        "id": item.id,
                        "question": item.question,
                        "failed_sql": item.failed_sql,
                        "analysis": item.analysis,
                        "action_taken": item.action_taken,
                        "status": item.status,
                    }
                })
            except FailedQueryRecord.DoesNotExist:
                return JsonResponse({"ok": False, "error": f"FailedQueryRecord with id {item_id} not found"}, status=404)

    training_type = str(body.get("training_type") or body.get("type") or "sql").strip().lower()
    if training_type not in {"ddl", "documentation", "sql"}:
        return JsonResponse({"ok": False, "error": "training_type must be ddl, documentation, or sql"}, status=400)

    if training_type == "ddl":
        ddl_text = str(body.get("ddl") or body.get("ddl_text") or "").strip()
        if not ddl_text:
            return JsonResponse({"ok": False, "error": "ddl is required"}, status=400)
        try:
            item_source = _training_dataset_target_source(body, data_sources, primary_source)
            schema_name, object_name, object_type = _parse_ddl_object(ddl_text, item_source.default_schema)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        schema_obj, _ = SchemaObject.objects.update_or_create(
            data_source=item_source,
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
        item_source = _training_dataset_target_source(body, data_sources, primary_source)
        doc_obj, _ = SchemaObject.objects.update_or_create(
            data_source=item_source,
            schema_name=item_source.default_schema or "LEGACY",
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
    item_source = _training_dataset_target_source(body, data_sources, primary_source)
    example = TrainingExample.objects.create(
        data_source=item_source,
        question=question,
        sql_text=sql_text,
        dialect="oracle" if item_source.db_type == "oracle" else "postgresql",
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

    if data_source.db_type == "oracle":
        sql = sql.rstrip(";").strip()

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

    rows = _mask_ct_employ_pii(sql, columns, rows)

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
    is_allowed, scope_error = _validate_factory_scope(request, question)
    if not is_allowed:
        return JsonResponse({"ok": False, "error": scope_error}, status=403)

    try:
        data_source = _resolve_data_source(body)
        result = generate_sql(data_source, question, user_id=_user_id(request))
        payload = _generate_payload(result, include_prompt=bool(body.get("debug_prompt")))
        payload["execution_policy"] = _execution_policy(data_source)
        payload["env"] = _env_name()
        _apply_sql_visibility(payload, request, "sql")
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
    if qlog is not None:
        is_allowed, scope_error = _validate_factory_scope(request, qlog.question or "")
        if not is_allowed:
            return JsonResponse({"ok": False, "error": scope_error}, status=403)

    try:
        data_source = qlog.data_source if qlog else _resolve_data_source(body)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

    if data_source.db_type == "oracle":
        sql = sql.rstrip(";").strip()

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
        payload = {
            "ok": True,
            "sql_only": True,
            "sql": sql,
            "columns": [],
            "rows": [],
            "latency_ms": 0,
            "policy": policy,
            "message": policy["message"],
        }
        _apply_sql_visibility(payload, request, "sql")
        return JsonResponse(payload)

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
            from webapps.vanna.models import FailedQueryRecord
            FailedQueryRecord.objects.update_or_create(
                query_log=qlog,
                defaults={
                    "question": qlog.question,
                    "failed_sql": sql,
                    "error_message": error_msg,
                    "data_source_code": qlog.data_source.code if qlog.data_source else "",
                }
            )

    if error_msg:
        return JsonResponse({"ok": False, "error": error_msg, "policy": policy}, status=500)

    rows = _mask_ct_employ_pii(sql, columns, rows)

    payload = {
        "ok": True,
        "columns": columns,
        "rows": rows,
        "is_mock": False,
        "sql_only": False,
        "latency_ms": latency_ms,
        "policy": policy,
    }
    payload["can_view_sql_command"] = _can_view_sql_command(request)
    payload["sql_hidden"] = not payload["can_view_sql_command"]
    return JsonResponse(payload)


@csrf_exempt
@require_POST
@require_node("nl2sql", api=True)
def rag_debug_api(request: HttpRequest) -> JsonResponse:
    if not is_vanna_admin(request):
        return JsonResponse({"ok": False, "error": "Only Vanna administrators can debug RAG."}, status=403)

    body = _json_body(request)
    question = str(body.get("question") or "").strip()
    if not question:
        return JsonResponse({"ok": False, "error": "question is required"}, status=400)

    try:
        data_source = _resolve_data_source(body)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to resolve data source: {exc}"}, status=400)

    from webapps.llm.embedding_factory import expected_embedding_dimension, get_shared_embedding_model
    from pgvector.django import CosineDistance

    q_vector = None
    se_results = []
    ee_results = []

    try:
        emb_model = get_shared_embedding_model()
        q_vector = emb_model.embed_query(question)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"Failed to calculate query embedding: {exc}"}, status=500)

    expected_dim = expected_embedding_dimension()

    if q_vector and len(q_vector) == expected_dim:
        se_matches = SchemaEmbedding.objects.filter(
            schema_object__data_source=data_source,
            schema_object__is_enabled=True,
            embedding__isnull=False,
            embedding_dimension=expected_dim,
        ).annotate(
            distance=CosineDistance("embedding", q_vector)
        ).order_by("distance")[:6]

        for se in se_matches:
            se_results.append({
                "id": se.id,
                "schema_name": se.schema_object.schema_name,
                "object_name": se.schema_object.object_name,
                "chunk_type": se.chunk_type,
                "chunk_text": se.chunk_text,
                "distance": float(se.distance or 0.0),
                "similarity": float(1.0 - (se.distance or 0.0)),
            })

        ee_matches = ExampleEmbedding.objects.filter(
            data_source=data_source,
            training_example__review_status="approved",
            embedding__isnull=False,
            embedding_dimension=expected_dim,
        ).annotate(
            distance=CosineDistance("embedding", q_vector)
        ).order_by("distance")[:3]

        for ee in ee_matches:
            ee_results.append({
                "id": ee.id,
                "question": ee.training_example.question,
                "sql": ee.training_example.sql_text,
                "distance": float(ee.distance or 0.0),
                "similarity": float(1.0 - (ee.distance or 0.0)),
            })

    from webapps.vanna.vanna_adapter import retrieve_context, build_generate_prompt
    context = retrieve_context(data_source, question)
    prompt = build_generate_prompt(data_source, question, context)

    return JsonResponse({
        "ok": True,
        "schema_matches": se_results,
        "example_matches": ee_results,
        "prompt": prompt,
    })
