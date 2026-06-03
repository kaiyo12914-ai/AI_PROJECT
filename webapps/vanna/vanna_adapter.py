from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from pgvector.django import CosineDistance
from webapps.database.db_factory import db_query_all
from webapps.llm.llm_factory import get_chat_model, get_embedding_model
from webapps.vanna.models import (
    DataSource,
    QueryLog,
    SchemaObject,
    TrainingExample,
    VannaTrainingSync,
    SchemaEmbedding,
    ExampleEmbedding,
)
from webapps.vanna.sql_guard import validate_sql


APP_DIR = Path(__file__).resolve().parent
VENDOR_ROOT = APP_DIR / "vendor" / "vanna2"
VENDOR_SRC = VENDOR_ROOT / "src"


@dataclass(frozen=True)
class VannaRuntimeStatus:
    available: bool
    version: str
    module_path: str
    error: str = ""


@dataclass(frozen=True)
class SchemaSyncResult:
    data_source: str
    db_type: str
    schema_name: str
    discovered: int
    created: int
    updated: int


@dataclass(frozen=True)
class TrainingSyncResult:
    data_source: str
    ddl_synced: int
    documentation_synced: int
    examples_synced: int
    skipped: int
    failed: int


@dataclass(frozen=True)
class GenerateSqlResult:
    sql: str
    prompt: str
    context_summary: dict[str, Any]
    query_log_id: int
    latency_ms: int


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _row_get(row: Any, index: int, key: str = "") -> Any:
    if isinstance(row, dict):
        return row.get(key) if key else None
    try:
        return row[index]
    except Exception:
        return None


def _llm_to_text(value: Any) -> str:
    if value is None:
        return ""
    content = getattr(value, "content", None)
    if content is not None:
        return str(content).strip()
    return str(value).strip()


def _read_vendor_version() -> str:
    pyproject = VENDOR_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    for line in pyproject.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if text.startswith("version"):
            _, _, value = text.partition("=")
            return value.strip().strip('"').strip("'") or "unknown"
    return "unknown"


def ensure_vanna_vendor_loaded() -> VannaRuntimeStatus:
    if not VENDOR_SRC.exists():
        return VannaRuntimeStatus(False, "unknown", "", f"Vanna vendor src not found: {VENDOR_SRC}")

    src = str(VENDOR_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)

    try:
        import vanna  # type: ignore
    except Exception as exc:
        return VannaRuntimeStatus(False, _read_vendor_version(), src, f"{type(exc).__name__}: {exc}")

    return VannaRuntimeStatus(
        available=True,
        version=_read_vendor_version(),
        module_path=str(getattr(vanna, "__file__", "")),
    )


def get_or_create_data_source(
    *,
    code: str = "default_pg",
    name: str = "Default PostgreSQL",
    db_type: str = "postgresql",
    db_profile: str = "",
    default_schema: str = "public",
) -> DataSource:
    code = _safe_text(code) or "default_pg"
    db_type = (_safe_text(db_type) or "postgresql").lower()
    default_schema = _safe_text(default_schema) or ("public" if db_type == "postgresql" else "")
    obj, _ = DataSource.objects.update_or_create(
        code=code,
        defaults={
            "name": _safe_text(name) or code,
            "db_type": db_type,
            "db_profile": _safe_text(db_profile),
            "default_schema": default_schema,
            "enabled": True,
        },
    )
    return obj


def _postgres_schema_rows(data_source: DataSource) -> list[dict[str, Any]]:
    schema = data_source.default_schema or "public"
    sql = """
        SELECT
          t.table_schema,
          t.table_name,
          t.table_type,
          c.column_name,
          c.data_type,
          c.is_nullable,
          c.ordinal_position,
          obj_description((quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass, 'pg_class') AS table_comment,
          col_description((quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass, c.ordinal_position) AS column_comment
        FROM information_schema.tables t
        JOIN information_schema.columns c
          ON c.table_schema = t.table_schema
         AND c.table_name = t.table_name
        WHERE t.table_schema = %s
          AND t.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY t.table_schema, t.table_name, c.ordinal_position
    """
    rows = db_query_all("postgresql", sql, [schema], profile=data_source.db_profile)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "schema_name": _safe_text(_row_get(r, 0)),
                "object_name": _safe_text(_row_get(r, 1)),
                "table_type": _safe_text(_row_get(r, 2)),
                "column_name": _safe_text(_row_get(r, 3)),
                "data_type": _safe_text(_row_get(r, 4)),
                "is_nullable": _safe_text(_row_get(r, 5)),
                "ordinal_position": int(_row_get(r, 6) or 0),
                "table_comment": _safe_text(_row_get(r, 7)),
                "column_comment": _safe_text(_row_get(r, 8)),
            }
        )
    return out


def _oracle_schema_rows(data_source: DataSource) -> list[dict[str, Any]]:
    owner = (data_source.default_schema or "").upper()
    sql = """
        SELECT
          c.owner,
          c.table_name,
          o.object_type,
          c.column_name,
          c.data_type,
          c.nullable,
          c.column_id,
          tc.comments AS table_comment,
          cc.comments AS column_comment
        FROM all_tab_columns c
        JOIN all_objects o
          ON o.owner = c.owner
         AND o.object_name = c.table_name
         AND o.object_type IN ('TABLE', 'VIEW')
        LEFT JOIN all_tab_comments tc
          ON tc.owner = c.owner
         AND tc.table_name = c.table_name
        LEFT JOIN all_col_comments cc
          ON cc.owner = c.owner
         AND cc.table_name = c.table_name
         AND cc.column_name = c.column_name
        WHERE (:owner IS NULL OR c.owner = :owner)
        ORDER BY c.owner, c.table_name, c.column_id
    """
    params = {"owner": owner or None}
    rows = db_query_all("oracle", sql, params, profile=data_source.db_profile)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "schema_name": _safe_text(_row_get(r, 0)),
                "object_name": _safe_text(_row_get(r, 1)),
                "table_type": _safe_text(_row_get(r, 2)),
                "column_name": _safe_text(_row_get(r, 3)),
                "data_type": _safe_text(_row_get(r, 4)),
                "is_nullable": _safe_text(_row_get(r, 5)),
                "ordinal_position": int(_row_get(r, 6) or 0),
                "table_comment": _safe_text(_row_get(r, 7)),
                "column_comment": _safe_text(_row_get(r, 8)),
            }
        )
    return out


def _object_type(db_type: str, raw: str) -> str:
    text = (raw or "").upper()
    if "VIEW" in text:
        return "view"
    return "table"


def _build_ddl(schema_name: str, object_name: str, columns: list[dict[str, Any]]) -> str:
    lines = []
    for col in columns:
        nullable = "" if str(col.get("is_nullable", "")).upper() in ("YES", "Y") else " NOT NULL"
        lines.append(f"  {col['column_name']} {col['data_type']}{nullable}")
    return f"CREATE TABLE {schema_name}.{object_name} (\n" + ",\n".join(lines) + "\n);"


def sync_schema(data_source: DataSource) -> SchemaSyncResult:
    if data_source.db_type == "postgresql":
        rows = _postgres_schema_rows(data_source)
    elif data_source.db_type == "oracle":
        rows = _oracle_schema_rows(data_source)
    else:
        raise ValueError(f"Unsupported db_type={data_source.db_type!r}")

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["schema_name"], row["object_name"]), []).append(row)

    created = 0
    updated = 0
    now = timezone.now()
    for (schema_name, object_name), cols in grouped.items():
        cols = sorted(cols, key=lambda item: int(item.get("ordinal_position") or 0))
        first = cols[0]
        columns_json = [
            {
                "name": col["column_name"],
                "type": col["data_type"],
                "nullable": col["is_nullable"],
                "ordinal": col["ordinal_position"],
                "description": col["column_comment"],
            }
            for col in cols
        ]
        ddl_text = _build_ddl(schema_name, object_name, cols)
        _, was_created = SchemaObject.objects.update_or_create(
            data_source=data_source,
            schema_name=schema_name,
            object_name=object_name,
            defaults={
                "object_type": _object_type(data_source.db_type, first["table_type"]),
                "description": first["table_comment"],
                "columns_json": columns_json,
                "ddl_text": ddl_text,
                "is_enabled": True,
                "last_synced_at": now,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return SchemaSyncResult(
        data_source=data_source.code,
        db_type=data_source.db_type,
        schema_name=data_source.default_schema,
        discovered=len(grouped),
        created=created,
        updated=updated,
    )


def sync_training(data_source: DataSource) -> TrainingSyncResult:
    ensure_vanna_vendor_loaded()
    skipped = 0
    failed = 0
    ddl_synced = 0
    documentation_synced = 0
    examples_synced = 0

    for obj in SchemaObject.objects.filter(data_source=data_source, is_enabled=True).iterator():
        for sync_type, content in (
            ("ddl", obj.ddl_text),
            ("documentation", obj.description),
        ):
            content = _safe_text(content)
            if not content:
                skipped += 1
                continue
            content_hash = _sha256(content)
            _, created = VannaTrainingSync.objects.update_or_create(
                data_source=data_source,
                sync_type=sync_type,
                source_object_id=obj.id,
                content_hash=content_hash,
                defaults={
                    "vanna_training_id": f"local:{sync_type}:{obj.id}:{content_hash[:12]}",
                    "sync_status": "synced",
                    "error_message": "",
                },
            )
            if created:
                if sync_type == "ddl":
                    ddl_synced += 1
                else:
                    documentation_synced += 1
            else:
                skipped += 1

    examples = TrainingExample.objects.filter(data_source=data_source, review_status="approved")
    for ex in examples.iterator():
        content = f"Question:\n{ex.question}\n\nSQL:\n{ex.sql_text}"
        content_hash = _sha256(content)
        _, created = VannaTrainingSync.objects.update_or_create(
            data_source=data_source,
            sync_type="example",
            source_object_id=ex.id,
            content_hash=content_hash,
            defaults={
                "vanna_training_id": f"local:example:{ex.id}:{content_hash[:12]}",
                "sync_status": "synced",
                "error_message": "",
            },
        )
        if created:
            examples_synced += 1
        else:
            skipped += 1

    return TrainingSyncResult(
        data_source=data_source.code,
        ddl_synced=ddl_synced,
        documentation_synced=documentation_synced,
        examples_synced=examples_synced,
        skipped=skipped,
        failed=failed,
    )


def _tokenize(text: str) -> set[str]:
    lowered = (text or "").lower()
    return {tok for tok in re.split(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", lowered) if tok}


def _score_schema(question: str, obj: SchemaObject) -> int:
    tokens = _tokenize(question)
    text = " ".join(
        [
            obj.schema_name,
            obj.object_name,
            obj.description,
            " ".join(str(c.get("name", "")) for c in (obj.columns_json or [])),
            " ".join(str(c.get("description", "")) for c in (obj.columns_json or [])),
        ]
    ).lower()
    return sum(3 if tok in obj.object_name.lower() else 1 for tok in tokens if tok and tok in text)


def retrieve_context(data_source: DataSource, question: str, *, top_k: int = 6) -> dict[str, Any]:
    # 嘗試獲取向量問題嵌入
    q_vector = None
    try:
        emb_model = get_embedding_model()
        q_vector = emb_model.embed_query(question)
    except Exception:
        # Fallback to keyword if model fetch fails
        pass

    selected_objects = []
    examples = []

    # 1. 檢索最相似的 SchemaObjects
    if q_vector:
        # 使用 pgvector 的 CosineDistance 來查詢相似的 DDL 與 Doc 向量
        se_matches = SchemaEmbedding.objects.filter(
            schema_object__data_source=data_source,
            schema_object__is_enabled=True,
            embedding__isnull=False
        ).annotate(
            distance=CosineDistance("embedding", q_vector)
        ).order_by("distance")[:top_k]

        seen_ids = set()
        for se in se_matches:
            obj = se.schema_object
            if obj.id not in seen_ids:
                seen_ids.add(obj.id)
                selected_objects.append(obj)
                
    # Fallback to keyword-based score if no vector matches found
    if not selected_objects:
        objects = list(SchemaObject.objects.filter(data_source=data_source, is_enabled=True))
        ranked = sorted(objects, key=lambda obj: _score_schema(question, obj), reverse=True)
        selected_objects = [obj for obj in ranked[:top_k] if _score_schema(question, obj) > 0] or ranked[: min(top_k, len(ranked))]

    # 2. 檢索最相似的 Approved SQL Examples
    if q_vector:
        ee_matches = ExampleEmbedding.objects.filter(
            data_source=data_source,
            training_example__review_status="approved",
            embedding__isnull=False
        ).annotate(
            distance=CosineDistance("embedding", q_vector)
        ).order_by("distance")[:3]
        examples = [ee.training_example for ee in ee_matches]

    # Fallback to keyword-based if no vector examples found
    if not examples:
        example_tokens = _tokenize(question)
        temp_examples = []
        for ex in TrainingExample.objects.filter(data_source=data_source, review_status="approved").order_by("-updated_at")[:20]:
            text = f"{ex.question}\n{ex.sql_text}".lower()
            score = sum(1 for tok in example_tokens if tok in text)
            if score > 0:
                temp_examples.append((score, ex))
        examples = [ex for _, ex in sorted(temp_examples, key=lambda item: item[0], reverse=True)[:3]]

    return {
        "tables": [
            {
                "id": obj.id,
                "schema": obj.schema_name,
                "name": obj.object_name,
                "description": obj.description,
                "ddl": obj.ddl_text,
                "columns": obj.columns_json,
            }
            for obj in selected_objects
        ],
        "examples": [
            {
                "question": ex.question,
                "sql": ex.sql_text,
            }
            for ex in examples
        ],
    }


def build_generate_prompt(data_source: DataSource, question: str, context: dict[str, Any]) -> str:
    tables = context.get("tables") or []
    examples = context.get("examples") or []
    ddl_blocks = "\n\n".join(str(item.get("ddl") or "") for item in tables if item.get("ddl"))
    example_blocks = "\n\n".join(
        f"Q: {item.get('question')}\nSQL:\n{item.get('sql')}" for item in examples
    )
    limit = int(getattr(settings, "NL2SQL_DEFAULT_ROW_LIMIT", 100) or 100)
    dialect = "PostgreSQL" if data_source.db_type == "postgresql" else "Oracle"
    return f"""你是 NL2SQL SQL 產生器。請只輸出 SQL，不要解釋，不要 Markdown code fence。

規則：
- 目標資料庫：{dialect}
- 只能產生 SELECT 或 WITH ... SELECT。
- 不可產生 INSERT、UPDATE、DELETE、MERGE、DROP、ALTER、CREATE、TRUNCATE、EXEC、CALL、GRANT、REVOKE。
- 不可查詢未列在 schema context 的 table。
- 若使用者問題不足以產生 SQL，輸出：-- NEED_MORE_CONTEXT
- 預設限制最多 {limit} 筆資料。

Schema context:
{ddl_blocks or "(no schema context)"}

Approved examples:
{example_blocks or "(no approved examples)"}

User question:
{question}
""".strip()


def extract_sql(text: str) -> str:
    raw = (text or "").strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    raw = raw.strip().strip("`").strip()
    marker = re.search(r"(?is)\b(with|select)\b", raw)
    if marker:
        raw = raw[marker.start() :].strip()
    return raw


def generate_sql(data_source: DataSource, question: str, user_id: str = "") -> GenerateSqlResult:
    started = time.monotonic()
    runtime = ensure_vanna_vendor_loaded()
    context = retrieve_context(data_source, question)
    prompt = build_generate_prompt(data_source, question, context)
    llm = get_chat_model(
        temperature=0.0,
        timeout=int(getattr(settings, "NL2SQL_QUERY_TIMEOUT_SEC", 30) or 30),
    )
    response = llm.invoke(prompt)
    sql = extract_sql(_llm_to_text(response))
    latency_ms = int((time.monotonic() - started) * 1000)

    # 整合 SQL Guard 進行安全審查
    is_safe, guard_err = validate_sql(sql)
    guard_status = "passed" if is_safe else "blocked"
    guard_message = "" if is_safe else guard_err

    qlog = QueryLog.objects.create(
        data_source=data_source,
        user_id=user_id,
        question=question,
        normalized_question=question.strip(),
        retrieved_context_json=context,
        generated_sql=sql,
        cleaned_sql=sql,
        guard_status=guard_status,
        guard_message=guard_message,
        execution_status="not_executed",
        latency_ms=latency_ms,
        engine_version="ai_tools_vanna_adapter_v1",
        prompt_version="nl2sql_generate_v1",
        guard_version="sql_guard_ast_v1",
        retriever_version="vector_v1",
        vanna_version=runtime.version,
        vanna_training_version="local_sync_v1",
        vanna_response_json={"vendor_available": runtime.available, "vendor_error": runtime.error},
    )
    return GenerateSqlResult(
        sql=sql,
        prompt=prompt,
        context_summary={
            "tables": [{"schema": t["schema"], "name": t["name"]} for t in context.get("tables", [])],
            "examples": len(context.get("examples", [])),
            "vendor_available": runtime.available,
            "vendor_version": runtime.version,
            "guard_status": guard_status,
            "guard_message": guard_message,
        },
        query_log_id=qlog.id,
        latency_ms=latency_ms,
    )


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    return json.loads(json.dumps(getattr(obj, "__dict__", {}), default=str))
