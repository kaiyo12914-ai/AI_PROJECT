"""Export Oracle CT_* table DDL and column comments into PostgreSQL."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql as pg_sql
from psycopg2.extras import Json


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from webapps.database.db_factory import db_connect  # noqa: E402


DEFAULT_ORACLE_PROFILE = "ERP_MPC"
DEFAULT_TABLE_PREFIX = "CT_"
DEFAULT_PG_TABLE_NAME = "TACLE_SCHEMA"

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

FETCH_TABLES_SQL = """
SELECT owner, table_name
FROM all_tables
WHERE table_name LIKE :table_like ESCAPE '\\'
  AND (:owner IS NULL OR owner = :owner)
ORDER BY owner, table_name
"""

GET_TABLE_DDL_SQL = """
SELECT DBMS_METADATA.GET_DDL('TABLE', :table_name, :owner)
FROM dual
"""

GET_TABLE_COMMENT_SQL = """
SELECT comments
FROM all_tab_comments
WHERE owner = :owner
  AND table_name = :table_name
"""

GET_COLUMN_COMMENTS_SQL = """
SELECT c.column_name, cm.comments
FROM all_tab_columns c
LEFT JOIN all_col_comments cm
  ON cm.owner = c.owner
 AND cm.table_name = c.table_name
 AND cm.column_name = c.column_name
WHERE c.owner = :owner
  AND c.table_name = :table_name
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


def _build_comment_sql(owner: str, table_name: str, table_comment: str, column_comments: list[dict[str, str]]) -> str:
    lines: list[str] = []
    owner_name = _normalize_text(owner)
    table_name = _normalize_text(table_name)
    if table_comment:
        lines.append(f"COMMENT ON TABLE {owner_name}.{table_name} IS {_sql_literal(table_comment)};")
    for row in column_comments:
        col_name = _normalize_text(row.get("column_name"))
        comment = _normalize_text(row.get("comments"))
        if not col_name or not comment:
            continue
        lines.append(f"COMMENT ON COLUMN {owner_name}.{table_name}.{col_name} IS {_sql_literal(comment)};")
    return "\n".join(lines)


def _combine_schema_text(ddl_text: str, comment_sql: str) -> str:
    ddl_text = _normalize_text(ddl_text)
    comment_sql = _normalize_text(comment_sql)
    if not comment_sql:
        return ddl_text
    if not ddl_text:
        return comment_sql
    return ddl_text.rstrip() + "\n\n" + comment_sql.rstrip()


def _parse_dsn_from_env() -> str:
    for key in ("POSTGRES_DSN", "PG_DSN", "DATABASE_URL"):
        val = _normalize_text(os.getenv(key))
        if val:
            return val

    host = _normalize_text(os.getenv("PGHOST"))
    port = _normalize_text(os.getenv("PGPORT")) or "5432"
    dbname = _normalize_text(os.getenv("PGDATABASE"))
    user = _normalize_text(os.getenv("PGUSER"))
    password = _normalize_text(os.getenv("PGPASSWORD"))
    if not (host and dbname and user):
        return ""

    auth = user
    if password:
        auth = f"{user}:{password}"
    return f"postgresql://{auth}@{host}:{port}/{dbname}"


def _ensure_target_table(cur, table_name: str) -> None:
    ddl = pg_sql.SQL(
        """
        CREATE TABLE IF NOT EXISTS {table_name} (
            table_schema text NOT NULL,
            table_name text NOT NULL,
            ddl_text text NOT NULL DEFAULT '',
            comment_sql_text text NOT NULL DEFAULT '',
            schema_text text NOT NULL DEFAULT '',
            table_comment text NOT NULL DEFAULT '',
            column_comments_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_profile text NOT NULL DEFAULT '',
            source_owner text NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (table_schema, table_name)
        )
        """
    ).format(table_name=pg_sql.Identifier(table_name))
    cur.execute(ddl)


def _get_oracle_table_rows(oracle_conn, owner: str, table_prefix: str) -> list[dict[str, str]]:
    owner = _normalize_text(owner).upper()
    prefix = _normalize_text(table_prefix).upper() or DEFAULT_TABLE_PREFIX
    like_pattern = prefix.replace("_", r"\_") + "%"
    params = {"table_like": like_pattern}
    if owner:
        params["owner"] = owner
    else:
        params["owner"] = None

    with oracle_conn.cursor() as cur:
        cur.execute(ORACLE_TRANSFORM_PLSQL)
        cur.execute(FETCH_TABLES_SQL, params)
        rows = cur.fetchall() or []

    out: list[dict[str, str]] = []
    for row in rows:
        out.append(
            {
                "owner": _normalize_text(row[0]).upper(),
                "table_name": _normalize_text(row[1]).upper(),
            }
        )
    return out


def _extract_oracle_table_schema(oracle_conn, owner: str, table_name: str) -> dict[str, Any]:
    params = {"owner": owner, "table_name": table_name}
    with oracle_conn.cursor() as cur:
        cur.execute(ORACLE_TRANSFORM_PLSQL)
        cur.execute(GET_TABLE_DDL_SQL, params)
        ddl_row = cur.fetchone()
        ddl_text = _normalize_text(ddl_row[0] if ddl_row else "")

        cur.execute(GET_TABLE_COMMENT_SQL, params)
        comment_row = cur.fetchone()
        table_comment = _normalize_text(comment_row[0] if comment_row else "")

        cur.execute(GET_COLUMN_COMMENTS_SQL, params)
        column_rows = cur.fetchall() or []

    column_comments = [
        {
            "column_name": _normalize_text(row[0]).upper(),
            "comments": _normalize_text(row[1]),
        }
        for row in column_rows
    ]
    comment_sql_text = _build_comment_sql(owner, table_name, table_comment, column_comments)
    schema_text = _combine_schema_text(ddl_text, comment_sql_text)
    return {
        "table_schema": _normalize_text(owner).upper(),
        "table_name": _normalize_text(table_name).upper(),
        "ddl_text": ddl_text,
        "comment_sql_text": comment_sql_text,
        "schema_text": schema_text,
        "table_comment": table_comment,
        "column_comments_json": column_comments,
    }


def _upsert_pg_row(pg_conn, target_table: str, row: dict[str, Any], source_profile: str) -> None:
    sql = pg_sql.SQL(
        """
        INSERT INTO {table_name} (
            table_schema,
            table_name,
            ddl_text,
            comment_sql_text,
            schema_text,
            table_comment,
            column_comments_json,
            source_profile,
            source_owner,
            updated_at
        )
        VALUES (
            %(table_schema)s,
            %(table_name)s,
            %(ddl_text)s,
            %(comment_sql_text)s,
            %(schema_text)s,
            %(table_comment)s,
            %(column_comments_json)s,
            %(source_profile)s,
            %(source_owner)s,
            now()
        )
        ON CONFLICT (table_schema, table_name) DO UPDATE SET
            ddl_text = EXCLUDED.ddl_text,
            comment_sql_text = EXCLUDED.comment_sql_text,
            schema_text = EXCLUDED.schema_text,
            table_comment = EXCLUDED.table_comment,
            column_comments_json = EXCLUDED.column_comments_json,
            source_profile = EXCLUDED.source_profile,
            source_owner = EXCLUDED.source_owner,
            updated_at = now()
        """
    ).format(table_name=pg_sql.Identifier(target_table))

    payload = dict(row)
    payload["source_profile"] = _normalize_text(source_profile)
    payload["source_owner"] = _normalize_text(row.get("table_schema")).upper()
    payload["column_comments_json"] = Json(row.get("column_comments_json") or [])

    with pg_conn.cursor() as cur:
        cur.execute(sql, payload)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export Oracle CT_* table DDL and column comments into PostgreSQL TACLE_SCHEMA.",
    )
    parser.add_argument("--oracle-profile", default=DEFAULT_ORACLE_PROFILE, help="Oracle db profile used by db_factory.")
    parser.add_argument("--oracle-owner", default="", help="Optional Oracle owner/schema filter.")
    parser.add_argument("--table-prefix", default=DEFAULT_TABLE_PREFIX, help="Oracle table name prefix filter.")
    parser.add_argument("--pg-dsn", default="", help="PostgreSQL DSN. Falls back to env variables.")
    parser.add_argument("--pg-table-name", default=DEFAULT_PG_TABLE_NAME, help="Target PostgreSQL table name.")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of tables to process.")
    parser.add_argument("--dry-run", action="store_true", help="Print extracted rows without writing to PostgreSQL.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    oracle_owner = _normalize_text(args.oracle_owner).upper()
    source_profile = _normalize_text(args.oracle_profile) or DEFAULT_ORACLE_PROFILE
    target_table = _normalize_text(args.pg_table_name) or DEFAULT_PG_TABLE_NAME
    pg_dsn = _normalize_text(args.pg_dsn) or _parse_dsn_from_env()

    if not pg_dsn and not args.dry_run:
        raise SystemExit("Missing PostgreSQL DSN. Set --pg-dsn or POSTGRES_DSN/PG_DSN/DATABASE_URL/PGHOST envs.")

    oracle_conn = db_connect("oracle", profile=source_profile)
    pg_conn = None
    try:
        tables = _get_oracle_table_rows(oracle_conn, oracle_owner, args.table_prefix)
        if args.limit and args.limit > 0:
            tables = tables[: args.limit]

        if not args.dry_run:
            pg_conn = psycopg2.connect(pg_dsn)
            pg_conn.autocommit = False
            with pg_conn.cursor() as cur:
                _ensure_target_table(cur, target_table)
            pg_conn.commit()

        processed = 0
        for item in tables:
            row = _extract_oracle_table_schema(oracle_conn, item["owner"], item["table_name"])
            processed += 1
            print(f"[{processed}] {row['table_schema']}.{row['table_name']}")
            print(row["schema_text"])
            print("-" * 80)

            if args.dry_run:
                continue

            assert pg_conn is not None
            _upsert_pg_row(pg_conn, target_table, row, source_profile)
            pg_conn.commit()

        print(f"Done. processed={processed}")
        return 0
    finally:
        try:
            oracle_conn.close()
        except Exception:
            pass
        if pg_conn is not None:
            try:
                pg_conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
