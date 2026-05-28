from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from .db import connect, ensure_schema, fetch_all, fetch_one
from .indexer import rebuild_project

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _json_default(value: Any) -> str:
    return str(value)


class PgCodeGraphServer:
    def __init__(self, project_root: str | None = None) -> None:
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.conn = connect(self.project_root)
        ensure_schema(self.conn)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            self._tool("pgcg_index_project", "Rebuild the PostgreSQL code graph for a project.", {
                "project_path": {"type": "string"},
                "project_name": {"type": "string"},
            }, ["project_path"]),
            self._tool("pgcg_search_symbols", "Search symbols by name, qualname, docstring, or code.", {
                "query": {"type": "string"},
                "project_name": {"type": "string"},
                "limit": {"type": "integer"},
            }, ["query"]),
            self._tool("pgcg_callers", "Find symbols that call a symbol.", {
                "symbol": {"type": "string"},
                "project_name": {"type": "string"},
                "limit": {"type": "integer"},
            }, ["symbol"]),
            self._tool("pgcg_callees", "Find symbols called by a symbol.", {
                "symbol": {"type": "string"},
                "project_name": {"type": "string"},
                "limit": {"type": "integer"},
            }, ["symbol"]),
            self._tool("pgcg_context", "Build compact AI-readable context for a task or symbol query.", {
                "query": {"type": "string"},
                "project_name": {"type": "string"},
                "limit": {"type": "integer"},
            }, ["query"]),
            self._tool("pgcg_status", "Show indexed projects and graph counts.", {}, []),
        ]

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "pgcg_index_project": self.tool_index_project,
            "pgcg_search_symbols": self.tool_search_symbols,
            "pgcg_callers": self.tool_callers,
            "pgcg_callees": self.tool_callees,
            "pgcg_context": self.tool_context,
            "pgcg_status": self.tool_status,
        }
        if name not in handlers:
            raise ValueError(f"Unknown tool: {name}")
        return handlers[name](args)

    def tool_index_project(self, args: dict[str, Any]) -> Any:
        return rebuild_project(self.conn, args["project_path"], args.get("project_name"))

    def tool_search_symbols(self, args: dict[str, Any]) -> Any:
        query = args["query"]
        limit = int(args.get("limit") or 20)
        project = args.get("project_name")
        return fetch_all(
            self.conn,
            """
            SELECT s.qualname, s.name, s.kind, f.rel_path, s.line, s.signature,
                   left(s.docstring, 300) AS docstring
            FROM pgcg_symbols s
            JOIN pgcg_files f ON f.id = s.file_id
            JOIN pgcg_projects p ON p.id = s.project_id
            WHERE (%s IS NULL OR p.name = %s)
              AND (
                s.name ILIKE %s OR s.qualname ILIKE %s OR s.docstring ILIKE %s OR s.code ILIKE %s
                OR to_tsvector('simple', s.qualname || ' ' || s.docstring || ' ' || s.code)
                   @@ plainto_tsquery('simple', %s)
              )
            ORDER BY CASE WHEN s.name ILIKE %s THEN 0 ELSE 1 END, s.qualname
            LIMIT %s
            """,
            (project, project, f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", query, query, limit),
        )

    def tool_callers(self, args: dict[str, Any]) -> Any:
        symbol = args["symbol"]
        limit = int(args.get("limit") or 20)
        project = args.get("project_name")
        return fetch_all(
            self.conn,
            """
            SELECT src.qualname AS caller, src.kind, f.rel_path, e.line,
                   tgt.qualname AS target, e.target_name, left(src.code, 800) AS code
            FROM pgcg_edges e
            JOIN pgcg_symbols src ON src.id = e.source_symbol_id
            LEFT JOIN pgcg_symbols tgt ON tgt.id = e.target_symbol_id
            JOIN pgcg_files f ON f.id = src.file_id
            JOIN pgcg_projects p ON p.id = e.project_id
            WHERE (%s IS NULL OR p.name = %s)
              AND (tgt.qualname = %s OR tgt.name = %s OR e.target_name = %s OR e.target_name LIKE %s)
            ORDER BY f.rel_path, e.line
            LIMIT %s
            """,
            (project, project, symbol, symbol, symbol, f"%.{symbol}", limit),
        )

    def tool_callees(self, args: dict[str, Any]) -> Any:
        symbol = args["symbol"]
        limit = int(args.get("limit") or 20)
        project = args.get("project_name")
        return fetch_all(
            self.conn,
            """
            SELECT src.qualname AS source, e.target_name,
                   tgt.qualname AS target, tgt.kind AS target_kind,
                   COALESCE(tf.rel_path, sf.rel_path) AS rel_path, e.line,
                   left(COALESCE(tgt.code, ''), 800) AS code
            FROM pgcg_edges e
            JOIN pgcg_symbols src ON src.id = e.source_symbol_id
            JOIN pgcg_files sf ON sf.id = src.file_id
            LEFT JOIN pgcg_symbols tgt ON tgt.id = e.target_symbol_id
            LEFT JOIN pgcg_files tf ON tf.id = tgt.file_id
            JOIN pgcg_projects p ON p.id = e.project_id
            WHERE (%s IS NULL OR p.name = %s)
              AND (src.qualname = %s OR src.name = %s)
            ORDER BY e.line, e.target_name
            LIMIT %s
            """,
            (project, project, symbol, symbol, limit),
        )

    def tool_context(self, args: dict[str, Any]) -> str:
        rows = self.tool_search_symbols(args)
        parts = [f"# pg_codegraph context for: {args['query']}"]
        for row in rows[: int(args.get("limit") or 8)]:
            detail = fetch_one(
                self.conn,
                """
                SELECT s.qualname, s.kind, f.rel_path, s.line, s.signature, s.docstring, s.code
                FROM pgcg_symbols s JOIN pgcg_files f ON f.id = s.file_id
                WHERE s.qualname = %s AND f.rel_path = %s
                """,
                (row["qualname"], row["rel_path"]),
            )
            if not detail:
                continue
            parts.append(
                "\n".join([
                    f"## {detail['qualname']} ({detail['kind']})",
                    f"{detail['rel_path']}:{detail['line']}",
                    detail.get("signature") or "",
                    detail.get("docstring") or "",
                    "```python",
                    (detail.get("code") or "")[:3000],
                    "```",
                ])
            )
        return "\n\n".join(parts)

    def tool_status(self, args: dict[str, Any]) -> Any:
        return fetch_all(
            self.conn,
            """
            SELECT p.name, p.root_path, p.indexed_at,
                   COALESCE(f.files, 0) AS files,
                   COALESCE(s.symbols, 0) AS symbols,
                   COALESCE(e.edges, 0) AS edges
            FROM pgcg_projects p
            LEFT JOIN (
                SELECT project_id, count(*) AS files
                FROM pgcg_files
                GROUP BY project_id
            ) f ON f.project_id = p.id
            LEFT JOIN (
                SELECT project_id, count(*) AS symbols
                FROM pgcg_symbols
                GROUP BY project_id
            ) s ON s.project_id = p.id
            LEFT JOIN (
                SELECT project_id, count(*) AS edges
                FROM pgcg_edges
                GROUP BY project_id
            ) e ON e.project_id = p.id
            ORDER BY p.name
            """,
        )

    @staticmethod
    def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            if not line.strip():
                continue
            request = json.loads(line)
            response = self.handle(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, default=_json_default) + "\n")
                sys.stdout.flush()

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pg-codegraph-mcp", "version": "0.1.0"},
                }
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                params = request.get("params") or {}
                result_data = self.call_tool(params["name"], params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(result_data, ensure_ascii=False, default=_json_default)}]}
            elif method and method.startswith("notifications/"):
                return None
            else:
                raise ValueError(f"Unsupported MCP method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}


def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL-backed code graph MCP server")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--index", help="Index a project and exit.")
    parser.add_argument("--project-name", help="Project name stored in PostgreSQL.")
    parser.add_argument("--status", action="store_true", help="Print indexed project status and exit.")
    args = parser.parse_args()
    server = PgCodeGraphServer(args.project_root)
    if args.index:
        print(json.dumps(server.tool_index_project({"project_path": args.index, "project_name": args.project_name}), ensure_ascii=False, default=_json_default))
        return
    if args.status:
        print(json.dumps(server.tool_status({}), ensure_ascii=False, default=_json_default))
        return
    server.serve_stdio()


if __name__ == "__main__":
    main()
