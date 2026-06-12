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
from webapps.llm.llm_factory import get_chat_model
from webapps.llm.embedding_factory import expected_embedding_dimension, get_shared_embedding_model
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


ORACLE_DB_LINK_BY_PROFILE = {
    "ERP_MPC": "MPCDB",
    "ERP_202": "DBLT202DB",
    "ERP_205": "DBLT205DB",
    "ERP_209": "DBLT209DB",
    "ERP_401": "DBLT401DB",
    "CIM_MPC": "DBLCIMMPC",
    "CIM_202": "DBLCIM202A",
    "CIM_205": "DBLCIM205A",
    "CIM_209": "DBLCIM209A",
    "CIM_401": "DBLCIM401A",
}

ERP_PROFILE_BY_FACTORY = {
    "MPC": "ERP_MPC",
    "202": "ERP_202",
    "205": "ERP_205",
    "209": "ERP_209",
    "401": "ERP_401",
}

CIM_PROFILE_BY_FACTORY = {
    "MPC": "CIM_MPC",
    "202": "CIM_202",
    "205": "CIM_205",
    "209": "CIM_209",
    "401": "CIM_401",
}


def oracle_db_link_for_profile(db_profile: str) -> str:
    profile = _safe_text(db_profile).upper()
    return ORACLE_DB_LINK_BY_PROFILE.get(profile, "")


def _factory_from_question(question: str) -> str:
    text = _safe_text(question).upper()
    if "MPC" in text:
        return "MPC"
    for factory in ("202", "205", "209", "401"):
        if re.search(rf"(?<!\d){factory}(?:\s*廠)?(?!\d)", text):
            return factory
    return ""


def oracle_profile_for_question(question: str, default_profile: str = "ERP_MPC") -> str:
    factory = _factory_from_question(question)
    if not factory:
        return _safe_text(default_profile).upper() or "ERP_MPC"
    if re.search(r"\[\s*主計\s*\]", _safe_text(question)):
        return CIM_PROFILE_BY_FACTORY[factory]
    return ERP_PROFILE_BY_FACTORY[factory]


def _oracle_db_link_prompt_rule(data_source: DataSource, question: str = "") -> str:
    if data_source.db_type != "oracle":
        return ""
    effective_profile = oracle_profile_for_question(question, data_source.db_profile or "ERP_MPC")
    db_link = oracle_db_link_for_profile(effective_profile)
    mapping = "、".join(f"{profile}=>{link}" for profile, link in ORACLE_DB_LINK_BY_PROFILE.items())
    if not db_link:
        return (
            "- Oracle 各廠資料必須透過 DB LINK 查詢；目前資料源 profile "
            f"`{effective_profile or '(empty)'}` 未設定 DB LINK 對應，若無法判定請輸出：-- NEED_MORE_CONTEXT\n"
            f"- 已知 DB LINK 對應：{mapping}。"
        )
    return (
        "- 問題格式以 `[業務]廠別...` 判定 DB LINK；`[主計]` 走 CIM，其它業務別依廠別走 ERP。\n"
        f"- 依本次問題判定使用 profile `{effective_profile}`，對應 DB LINK `{db_link}`。\n"
        f"- 所有 schema context 內的實體表或檢視都必須引用 `@{db_link}`，例如 `TABLE_NAME@{db_link}` 或 `SCHEMA.TABLE_NAME@{db_link}`。\n"
        f"- JOIN、子查詢、CTE 來源表也一律必須加上 `@{db_link}`；禁止輸出未帶 DB LINK 的遠端業務表。"
    )


def sql_uses_required_oracle_db_link(sql: str, data_source: DataSource, question: str = "") -> tuple[bool, str]:
    if data_source.db_type != "oracle":
        return True, ""
    if (sql or "").strip().upper().startswith("-- NEED_MORE_CONTEXT"):
        return True, ""
    effective_profile = oracle_profile_for_question(question, data_source.db_profile or "ERP_MPC")
    db_link = oracle_db_link_for_profile(effective_profile)
    if not db_link:
        return False, f"Oracle data source profile '{effective_profile}' has no DB LINK mapping."
    if not re.search(rf"@{re.escape(db_link)}\b", sql or "", flags=re.IGNORECASE):
        return False, f"Generated Oracle SQL must reference DB LINK '@{db_link}' for profile '{effective_profile}'."
    return True, ""


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
    db_profile = _safe_text(db_profile)
    if db_type == "oracle" and not db_profile:
        db_profile = "ERP_MPC"
    default_schema = _safe_text(default_schema) or ("public" if db_type == "postgresql" else "")
    obj, _ = DataSource.objects.update_or_create(
        code=code,
        defaults={
            "name": _safe_text(name) or code,
            "db_type": db_type,
            "db_profile": db_profile,
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


def _expected_embedding_dimension() -> int:
    return expected_embedding_dimension()


def _embedding_vector_is_usable(vector: Any) -> bool:
    try:
        return bool(vector) and len(vector) == _expected_embedding_dimension()
    except TypeError:
        return False


def retrieve_context(data_source: DataSource, question: str, *, top_k: int = 6) -> dict[str, Any]:
    # 嘗試獲取向量問題嵌入
    q_vector = None
    try:
        emb_model = get_shared_embedding_model()
        candidate_vector = emb_model.embed_query(question)
        if _embedding_vector_is_usable(candidate_vector):
            q_vector = candidate_vector
    except Exception:
        # Fallback to keyword if model fetch fails
        pass

    selected_objects = []
    schema_chunks = []
    examples = []

    # 1. 檢索最相似的 SchemaObjects
    if q_vector:
        # 使用 pgvector 的 CosineDistance 來查詢相似的 DDL 與 Doc 向量
        try:
            se_matches = SchemaEmbedding.objects.filter(
                schema_object__data_source=data_source,
                schema_object__is_enabled=True,
                embedding__isnull=False,
                embedding_dimension=_expected_embedding_dimension(),
            ).annotate(
                distance=CosineDistance("embedding", q_vector)
            ).order_by("distance")[:top_k]

            seen_ids = set()
            for se in se_matches:
                obj = se.schema_object
                schema_chunks.append(
                    {
                        "id": se.id,
                        "schema_object_id": obj.id,
                        "schema": obj.schema_name,
                        "name": obj.object_name,
                        "chunk_type": se.chunk_type,
                        "chunk_text": se.chunk_text,
                        "distance": float(se.distance or 0.0),
                    }
                )
                if obj.id not in seen_ids:
                    seen_ids.add(obj.id)
                    selected_objects.append(obj)
        except Exception:
            selected_objects = []
            schema_chunks = []
                
    # Fallback to keyword-based score if no vector matches found
    if not selected_objects:
        objects = list(SchemaObject.objects.filter(data_source=data_source, is_enabled=True))
        ranked = sorted(objects, key=lambda obj: _score_schema(question, obj), reverse=True)
        selected_objects = [obj for obj in ranked[:top_k] if _score_schema(question, obj) > 0] or ranked[: min(top_k, len(ranked))]

    # 2. 檢索最相似的 Approved SQL Examples
    if q_vector:
        try:
            ee_matches = ExampleEmbedding.objects.filter(
                data_source=data_source,
                training_example__review_status="approved",
                embedding__isnull=False,
                embedding_dimension=_expected_embedding_dimension(),
            ).annotate(
                distance=CosineDistance("embedding", q_vector)
            ).order_by("distance")[:3]
            examples = [ee.training_example for ee in ee_matches]
        except Exception:
            examples = []

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
        "schema_chunks": schema_chunks,
        "examples": [
            {
                "question": ex.question,
                "sql": ex.sql_text,
            }
            for ex in examples
        ],
    }


def _format_columns_context(columns: Any) -> str:
    if not isinstance(columns, list):
        return ""
    lines = []
    for col in columns:
        if not isinstance(col, dict):
            continue
        name = _safe_text(col.get("name") or col.get("column_name"))
        if not name:
            continue
        data_type = _safe_text(col.get("type") or col.get("data_type"))
        description = _safe_text(col.get("description") or col.get("comment"))
        detail = " ".join(part for part in [data_type, description] if part)
        lines.append(f"- {name}: {detail}" if detail else f"- {name}")
    return "\n".join(lines)


def _build_schema_context(context: dict[str, Any]) -> str:
    tables = context.get("tables") or []
    schema_chunks = context.get("schema_chunks") or []
    blocks = []
    seen_texts = set()

    def _push(block: str) -> None:
        text = _safe_text(block)
        if not text or text in seen_texts:
            return
        seen_texts.add(text)
        blocks.append(text)

    for chunk in schema_chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_text = _safe_text(chunk.get("chunk_text"))
        if not chunk_text:
            continue
        schema = _safe_text(chunk.get("schema"))
        name = _safe_text(chunk.get("name"))
        chunk_type = _safe_text(chunk.get("chunk_type")) or "schema"
        object_label = ".".join(part for part in [schema, name] if part) or "schema"
        _push(f"-- {object_label} ({chunk_type})\n{chunk_text}")

    for table in tables:
        if not isinstance(table, dict):
            continue
        schema = _safe_text(table.get("schema"))
        name = _safe_text(table.get("name"))
        object_label = ".".join(part for part in [schema, name] if part) or "schema"
        ddl = _safe_text(table.get("ddl"))
        if ddl:
            _push(f"-- {object_label} (ddl)\n{ddl}")
        columns_context = _format_columns_context(table.get("columns"))
        if columns_context:
            _push(f"-- {object_label} (columns)\n{columns_context}")

    return "\n\n".join(blocks)


def build_generate_prompt(data_source: DataSource, question: str, context: dict[str, Any]) -> str:
    examples = context.get("examples") or []
    schema_context = _build_schema_context(context)
    example_blocks = "\n\n".join(
        f"Q: {item.get('question')}\nSQL:\n{item.get('sql')}" for item in examples
    )
    limit = int(getattr(settings, "NL2SQL_DEFAULT_ROW_LIMIT", 100) or 100)
    dialect = "PostgreSQL" if data_source.db_type == "postgresql" else "Oracle"
    db_link_rule = _oracle_db_link_prompt_rule(data_source, question)
    return f"""你是 NL2SQL SQL 產生器。請只輸出 SQL，不要解釋，不要 Markdown code fence。

規則：
- 目標資料庫：{dialect}
- 只能產生 SELECT 或 WITH ... SELECT。
- 不可產生 INSERT、UPDATE、DELETE、MERGE、DROP、ALTER、CREATE、TRUNCATE、EXEC、CALL、GRANT、REVOKE。
- 不可查詢未列在 schema context 的 table。
- Oracle DB LINK 規則優先於 approved examples；若範例未帶 DB LINK，也必須改成目前資料源對應 DB LINK。
{db_link_rule}
- 若使用者問題不足以產生 SQL，輸出：-- NEED_MORE_CONTEXT
- 預設限制最多 {limit} 筆資料。

Schema context:
{schema_context or "(no schema context)"}

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
    # 移除尾隨分號，防範 Oracle 報 ORA-00933 錯誤
    raw = raw.rstrip(";").strip()
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
    if is_safe:
        is_safe, guard_err = sql_uses_required_oracle_db_link(sql, data_source, question)
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
            "oracle_profile": oracle_profile_for_question(question, data_source.db_profile or "ERP_MPC")
            if data_source.db_type == "oracle"
            else "",
        },
        query_log_id=qlog.id,
        latency_ms=latency_ms,
    )


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    return json.loads(json.dumps(getattr(obj, "__dict__", {}), default=str))
