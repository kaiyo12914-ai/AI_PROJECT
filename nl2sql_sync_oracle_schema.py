"""Sync Oracle CT_/DT_* schema into NL2SQL tables and embeddings.

This tool extracts Oracle DDL, object comments, and column comments for
tables/views/materialized views whose names match the configured prefixes,
then writes the result into:

- nl2sql_schema_object
- nl2sql_schema_embedding
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402
from webapps.database.db_factory import db_connect  # noqa: E402
from webapps.llm.embedding_factory import (  # noqa: E402
    expected_embedding_dimension,
    get_shared_embedding_model,
    get_shared_embedding_model_name,
)
from webapps.vanna.models import DataSource, SchemaEmbedding, SchemaObject  # noqa: E402


DEFAULT_ORACLE_PROFILE = "ERP_MPC"
DEFAULT_DATA_SOURCE_CODE = "nl2sql_oracle_schema"
DEFAULT_DATA_SOURCE_NAME = "Oracle NL2SQL Schema"
DEFAULT_TABLE_PREFIXES = ("CT_", "DT_")
DEFAULT_OBJECT_TYPES = ("table", "view", "mview")
DEFAULT_BATCH_SIZE = 32

ORACLE_TRANSFORM_PLSQL = """
BEGIN
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'PRETTY', TRUE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SQLTERMINATOR', TRUE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'TABLESPACE', FALSE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'CONSTRAINTS', TRUE);
  DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'REF_CONSTRAINTS', TRUE);
END;
"""

FETCH_OBJECTS_SQL = """
SELECT owner, object_name, object_type
FROM all_objects
WHERE object_type IN ({object_types})
  AND ({name_filter})
  AND (:owner IS NULL OR owner = :owner)
ORDER BY owner, object_name, object_type
"""

GET_DDL_SQL = """
SELECT DBMS_METADATA.GET_DDL(:object_type, :object_name, :owner)
FROM dual
"""

GET_TABLE_COMMENT_SQL = """
SELECT comments
FROM all_tab_comments
WHERE owner = :owner
  AND table_name = :object_name
"""

GET_ROW_ESTIMATE_TABLE_SQL = """
SELECT num_rows
FROM all_tables
WHERE owner = :owner
  AND table_name = :object_name
"""

GET_ROW_ESTIMATE_MVIEW_SQL = """
SELECT num_rows
FROM all_mviews
WHERE owner = :owner
  AND mview_name = :object_name
"""

GET_COLUMN_COMMENTS_SQL = """
SELECT c.column_name, c.data_type, c.nullable, c.column_id, cm.comments
FROM all_tab_columns c
LEFT JOIN all_col_comments cm
  ON cm.owner = c.owner
 AND cm.table_name = c.table_name
 AND cm.column_name = c.column_name
WHERE c.owner = :owner
  AND c.table_name = :object_name
ORDER BY c.column_id
"""


def _sql_literal(value: str) -> str:
    return "'" + (value or "").replace("'", "''") + "'"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "read") and callable(value.read):
        try:
            value = value.read()
        except Exception:
            value = str(value)
    return str(value).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _split_table_prefixes(value: Any) -> list[str]:
    raw: list[str] = []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = str(value or "").replace(";", ",").replace(" ", ",").split(",")
    for item in items:
        text = _normalize_text(item).upper()
        if text:
            raw.append(text)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out or list(DEFAULT_TABLE_PREFIXES)


def _split_object_types(value: Any) -> list[str]:
    raw: list[str] = []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = str(value or "").replace(";", ",").replace(" ", ",").split(",")
    for item in items:
        text = _normalize_text(item).lower()
        if text in {"table", "view", "mview", "materialized_view"}:
            raw.append("materialized_view" if text in {"mview", "materialized_view"} else text)
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out or list(DEFAULT_OBJECT_TYPES)


def _oracle_object_type_name(object_type: str) -> str:
    value = _normalize_text(object_type).lower().replace(" ", "_")
    if value == "mview":
        return "materialized_view"
    if value == "materialized_view":
        return "materialized_view"
    return value


def _oracle_ddl_type(object_type: str) -> str:
    value = _oracle_object_type_name(object_type)
    if value == "view":
        return "VIEW"
    if value == "materialized_view":
        return "MATERIALIZED_VIEW"
    return "TABLE"


def _oracle_object_filter_type(object_type: str) -> str:
    value = _oracle_object_type_name(object_type)
    if value == "materialized_view":
        return "MATERIALIZED VIEW"
    if value == "view":
        return "VIEW"
    return "TABLE"


def _build_name_filter(prefixes: list[str]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for idx, prefix in enumerate(prefixes):
        param_name = f"object_like_{idx}"
        clauses.append(f"object_name LIKE :{param_name} ESCAPE '\\'")
        params[param_name] = prefix.replace("_", r"\_") + "%"
    return "(" + " OR ".join(clauses) + ")", params


def _build_comment_sql(owner: str, object_name: str, table_comment: str, columns: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    owner_name = _normalize_text(owner)
    object_name = _normalize_text(object_name)

    if table_comment:
        lines.append(f"COMMENT ON TABLE {owner_name}.{object_name} IS {_sql_literal(table_comment)};")

    for row in columns:
        col_name = _normalize_text(row.get("column_name"))
        comment = _normalize_text(row.get("comments"))
        if not col_name or not comment:
            continue
        lines.append(f"COMMENT ON COLUMN {owner_name}.{object_name}.{col_name} IS {_sql_literal(comment)};")
    return "\n".join(lines)


def _combine_schema_text(ddl_text: str, comment_sql: str) -> str:
    ddl_text = _normalize_text(ddl_text)
    comment_sql = _normalize_text(comment_sql)
    if not ddl_text:
        return comment_sql
    if not comment_sql:
        return ddl_text
    return ddl_text.rstrip() + "\n\n" + comment_sql.rstrip()


def _ensure_data_source(code: str, name: str, oracle_profile: str, oracle_owner: str, *, create_if_missing: bool) -> DataSource:
    defaults = {
        "name": name,
        "db_type": "oracle",
        "db_profile": oracle_profile,
        "default_schema": oracle_owner,
        "enabled": True,
        "execute_enabled": False,
        "config_json": {
            "source": "nl2sql_sync_oracle_schema",
            "oracle_profile": oracle_profile,
            "oracle_owner": oracle_owner,
        },
    }
    if create_if_missing:
        data_source, _ = DataSource.objects.update_or_create(code=code, defaults=defaults)
        return data_source

    return DataSource.objects.get(code=code)


def _get_oracle_object_rows(oracle_conn, owner: str, prefixes: list[str], object_types: list[str]) -> list[dict[str, str]]:
    owner = _normalize_text(owner).upper()
    name_filter, params = _build_name_filter(prefixes)
    params["owner"] = owner or None
    object_types_sql = ", ".join(f"'{_oracle_object_filter_type(item)}'" for item in object_types)
    fetch_sql = FETCH_OBJECTS_SQL.format(object_types=object_types_sql, name_filter=name_filter)

    with oracle_conn.cursor() as cur:
        cur.execute(ORACLE_TRANSFORM_PLSQL)
        cur.execute(fetch_sql, params)
        rows = cur.fetchall() or []

    out: list[dict[str, str]] = []
    for row in rows:
        out.append(
            {
                "owner": _normalize_text(row[0]).upper(),
                "object_name": _normalize_text(row[1]).upper(),
                "object_type": _oracle_object_type_name(row[2]),
            }
        )
    return out


def _extract_oracle_schema(oracle_conn, owner: str, object_name: str, object_type: str) -> dict[str, Any]:
    params = {"owner": owner, "object_name": object_name}
    ddl_object_type = _oracle_ddl_type(object_type)
    with oracle_conn.cursor() as cur:
        cur.execute(ORACLE_TRANSFORM_PLSQL)
        cur.execute(GET_DDL_SQL, {"owner": owner, "object_name": object_name, "object_type": ddl_object_type})
        ddl_row = cur.fetchone()
        ddl_text = _normalize_text(ddl_row[0] if ddl_row else "")

        cur.execute(GET_TABLE_COMMENT_SQL, params)
        comment_row = cur.fetchone()
        table_comment = _normalize_text(comment_row[0] if comment_row else "")

        row_estimate = None
        if ddl_object_type == "TABLE":
            cur.execute(GET_ROW_ESTIMATE_TABLE_SQL, params)
            row_estimate_row = cur.fetchone()
            row_estimate = row_estimate_row[0] if row_estimate_row else None
        elif ddl_object_type == "MATERIALIZED_VIEW":
            cur.execute(GET_ROW_ESTIMATE_MVIEW_SQL, params)
            row_estimate_row = cur.fetchone()
            row_estimate = row_estimate_row[0] if row_estimate_row else None

        cur.execute(GET_COLUMN_COMMENTS_SQL, params)
        column_rows = cur.fetchall() or []

    columns: list[dict[str, Any]] = []
    for row in column_rows:
        columns.append(
            {
                "column_name": _normalize_text(row[0]).upper(),
                "data_type": _normalize_text(row[1]),
                "nullable": _normalize_text(row[2]).upper(),
                "ordinal_position": int(row[3] or 0),
                "comments": _normalize_text(row[4]),
            }
        )

    comment_sql_text = _build_comment_sql(owner, object_name, table_comment, columns)
    combined_ddl = _combine_schema_text(ddl_text, comment_sql_text)
    columns_json = [
        {
            "name": col["column_name"],
            "type": col["data_type"],
            "nullable": col["nullable"],
            "ordinal": col["ordinal_position"],
            "description": col["comments"],
        }
        for col in columns
    ]
    columns_summary = "\n".join(
        " | ".join(
            part
            for part in (
                col["column_name"],
                col["data_type"],
                "NOT NULL" if col["nullable"] not in {"Y", "YES"} else "",
                col["comments"],
            )
            if part
        )
        for col in columns
    )
    documentation_text = "\n".join(part for part in (table_comment, columns_summary) if part)

    return {
        "table_schema": _normalize_text(owner).upper(),
        "table_name": _normalize_text(object_name).upper(),
        "object_type": ddl_object_type.lower(),
        "table_comment": table_comment,
        "row_estimate": row_estimate if row_estimate is not None else None,
        "ddl_text": combined_ddl,
        "columns_json": columns_json,
        "ddl_chunk_text": combined_ddl,
        "columns_chunk_text": columns_summary,
        "documentation_chunk_text": documentation_text,
        "column_comments_json": columns,
        "comment_sql_text": comment_sql_text,
    }


def _sync_schema_object(data_source: DataSource, schema: dict[str, Any], *, dry_run: bool) -> tuple[SchemaObject | None, bool]:
    defaults = {
        "object_type": schema["object_type"],
        "description": schema["table_comment"],
        "columns_json": schema["columns_json"],
        "ddl_text": schema["ddl_text"],
        "row_estimate": schema["row_estimate"],
        "is_enabled": True,
        "last_synced_at": timezone.now(),
    }
    if dry_run:
        return None, False

    schema_obj, created = SchemaObject.objects.update_or_create(
        data_source=data_source,
        schema_name=schema["table_schema"],
        object_name=schema["table_name"],
        defaults=defaults,
    )
    return schema_obj, created


def _upsert_embedding(schema_obj: SchemaObject, chunk_type: str, chunk_text: str, *, dry_run: bool) -> bool:
    text = _normalize_text(chunk_text)
    if dry_run:
        return bool(text)
    if not text:
        SchemaEmbedding.objects.filter(schema_object=schema_obj, chunk_type=chunk_type).delete()
        return False

    SchemaEmbedding.objects.update_or_create(
        schema_object=schema_obj,
        chunk_type=chunk_type,
        defaults={
            "chunk_text": text,
            "embedding": None,
            "embedding_model": "",
            "embedding_dimension": expected_embedding_dimension(),
            "content_hash": _sha256(text),
        },
    )
    return True


def _embed_schema_embeddings(data_source: DataSource, *, batch_size: int) -> dict[str, int]:
    embeddings_impl = get_shared_embedding_model()
    model_name = get_shared_embedding_model_name()
    expected_dim = expected_embedding_dimension()
    processed = 0
    updated = 0

    for chunk_type in ("ddl", "columns", "documentation"):
        items = list(
            SchemaEmbedding.objects.filter(
                schema_object__data_source=data_source,
                chunk_type=chunk_type,
                embedding__isnull=True,
            ).select_related("schema_object")
        )
        if not items:
            continue

        for idx in range(0, len(items), batch_size):
            batch = items[idx : idx + batch_size]
            texts = [item.chunk_text for item in batch]
            vectors = embeddings_impl.embed_documents(texts)
            processed += len(batch)

            with transaction.atomic():
                for item, vector in zip(batch, vectors):
                    if len(vector) != expected_dim:
                        continue
                    item.embedding = vector
                    item.embedding_model = model_name
                    item.embedding_dimension = len(vector)
                    item.save(update_fields=["embedding", "embedding_model", "embedding_dimension"])
                    updated += 1

    return {"processed": processed, "updated": updated}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Oracle CT_*/DT_* tables/views/materialized views into nl2sql_schema_object and nl2sql_schema_embedding.",
    )
    parser.add_argument("--oracle-profile", default=DEFAULT_ORACLE_PROFILE, help="Oracle db profile used by db_factory.")
    parser.add_argument("--oracle-owner", default="", help="Optional Oracle owner/schema filter.")
    parser.add_argument(
        "--table-prefixes",
        default="CT_,DT_",
        help="Comma/space/semicolon separated table prefixes, e.g. CT_,DT_.",
    )
    parser.add_argument(
        "--object-types",
        default="table,view,mview",
        help="Comma/space/semicolon separated Oracle object types: table, view, mview.",
    )
    parser.add_argument("--data-source-code", default=DEFAULT_DATA_SOURCE_CODE, help="NL2SQL data source code.")
    parser.add_argument("--data-source-name", default=DEFAULT_DATA_SOURCE_NAME, help="NL2SQL data source display name.")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of tables to process.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Embedding batch size.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Only build schema objects, not embeddings.")
    parser.add_argument("--clear", action="store_true", help="Delete existing schema objects for this data source first.")
    parser.add_argument("--dry-run", action="store_true", help="Print extracted rows without writing to NL2SQL tables.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    oracle_owner = _normalize_text(args.oracle_owner).upper()
    oracle_profile = _normalize_text(args.oracle_profile) or DEFAULT_ORACLE_PROFILE
    prefixes = _split_table_prefixes(args.table_prefixes)
    object_types = _split_object_types(args.object_types)

    oracle_conn = db_connect("oracle", profile=oracle_profile)
    try:
        objects = _get_oracle_object_rows(oracle_conn, oracle_owner, prefixes, object_types)
        if args.limit and args.limit > 0:
            objects = objects[: args.limit]

        if args.dry_run:
            for idx, item in enumerate(objects, start=1):
                schema = _extract_oracle_schema(oracle_conn, item["owner"], item["object_name"], item["object_type"])
                print(f"[{idx}] {schema['table_schema']}.{schema['table_name']} ({schema['object_type']})")
                print(schema["ddl_text"])
                print("-" * 80)
            print(f"Done. processed={len(objects)}")
            return 0

        data_source = _ensure_data_source(
            args.data_source_code,
            args.data_source_name,
            oracle_profile,
            oracle_owner,
            create_if_missing=True,
        )

        if args.clear:
            with transaction.atomic():
                SchemaEmbedding.objects.filter(schema_object__data_source=data_source).delete()
                SchemaObject.objects.filter(data_source=data_source).delete()

        processed = 0
        created_objects = 0
        updated_objects = 0
        embedded_rows = 0

        for item in objects:
            schema = _extract_oracle_schema(oracle_conn, item["owner"], item["object_name"], item["object_type"])
            with transaction.atomic():
                schema_obj, created = _sync_schema_object(data_source, schema, dry_run=False)
                if schema_obj is None:
                    continue
                processed += 1
                if created:
                    created_objects += 1
                else:
                    updated_objects += 1

                if _upsert_embedding(schema_obj, "ddl", schema["ddl_chunk_text"], dry_run=False):
                    embedded_rows += 1
                if _upsert_embedding(schema_obj, "columns", schema["columns_chunk_text"], dry_run=False):
                    embedded_rows += 1
                if _upsert_embedding(schema_obj, "documentation", schema["documentation_chunk_text"], dry_run=False):
                    embedded_rows += 1

        embed_result = {"processed": 0, "updated": 0}
        if not args.skip_embeddings:
            embed_result = _embed_schema_embeddings(data_source, batch_size=max(1, args.batch_size))

        print(
            f"Done. data_source={data_source.code} processed={processed} "
            f"created={created_objects} updated={updated_objects} "
            f"schema_embeddings_ready={embedded_rows} vector_updated={embed_result['updated']}"
        )
        return 0
    finally:
        try:
            oracle_conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
