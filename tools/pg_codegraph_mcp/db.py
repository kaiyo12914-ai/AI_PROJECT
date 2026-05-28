from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pgcg_projects (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    root_path TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pgcg_files (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES pgcg_projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    language TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mtime DOUBLE PRECISION NOT NULL,
    size_bytes BIGINT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(project_id, rel_path)
);

CREATE TABLE IF NOT EXISTS pgcg_symbols (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES pgcg_projects(id) ON DELETE CASCADE,
    file_id BIGINT NOT NULL REFERENCES pgcg_files(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT NOT NULL DEFAULT '',
    docstring TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL DEFAULT '',
    UNIQUE(project_id, file_id, qualname, line)
);

CREATE TABLE IF NOT EXISTS pgcg_edges (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES pgcg_projects(id) ON DELETE CASCADE,
    source_symbol_id BIGINT REFERENCES pgcg_symbols(id) ON DELETE CASCADE,
    target_symbol_id BIGINT REFERENCES pgcg_symbols(id) ON DELETE SET NULL,
    file_id BIGINT NOT NULL REFERENCES pgcg_files(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    target_name TEXT NOT NULL,
    line INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS pgcg_files_project_idx ON pgcg_files(project_id);
CREATE INDEX IF NOT EXISTS pgcg_symbols_project_name_idx ON pgcg_symbols(project_id, name);
CREATE INDEX IF NOT EXISTS pgcg_symbols_project_qualname_idx ON pgcg_symbols(project_id, qualname);
CREATE INDEX IF NOT EXISTS pgcg_edges_project_source_idx ON pgcg_edges(project_id, source_symbol_id);
CREATE INDEX IF NOT EXISTS pgcg_edges_project_target_idx ON pgcg_edges(project_id, target_symbol_id);
CREATE INDEX IF NOT EXISTS pgcg_files_fts_idx ON pgcg_files USING GIN (to_tsvector('simple', content));
CREATE INDEX IF NOT EXISTS pgcg_symbols_fts_idx ON pgcg_symbols USING GIN (to_tsvector('simple', qualname || ' ' || docstring || ' ' || code));
"""


def _load_dotenv(project_root: Path) -> None:
    env_path = project_root / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def connect(project_root: str | Path | None = None) -> Any:
    root = Path(project_root or os.getcwd()).resolve()
    _load_dotenv(root)
    try:
        from webapps.database.db_factory import db_connect
    except Exception as exc:
        raise RuntimeError("pg_codegraph_mcp must be launched from the AI_TOOLS project root.") from exc
    return db_connect("postgresql")


def ensure_schema(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def fetch_all(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_one(conn: Any, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None

