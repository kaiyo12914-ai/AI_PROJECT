# PostgreSQL CodeGraph MCP Server

這是一個 PostgreSQL-backed 的 MCP server，用來替代 `.codegraph/codegraph.db` 的 SQLite 儲存方式。設計對齊 CodeGraph 的核心流程：

1. 掃描 source files。
2. 以 Python AST 抽取 symbols 與 calls。
3. 寫入 PostgreSQL tables：`pgcg_projects`、`pgcg_files`、`pgcg_symbols`、`pgcg_edges`。
4. 透過 MCP tools 提供 `search`、`callers`、`callees`、`context` 查詢。

## 初始化 / 重建索引

在專案根目錄執行：

```powershell
python -m tools.pg_codegraph_mcp.server --project-root H:\AI\AI_TOOLS --index H:\AI\AI_TOOLS --project-name AI_TOOLS
```

DB 連線走專案既有 `webapps.database.db_factory.db_connect("postgresql")`，因此會使用 root `.env` 的 `DATABASE_URL`。

## MCP Server 指令

```powershell
python -m tools.pg_codegraph_mcp.server --project-root H:\AI\AI_TOOLS
```

可掛到 MCP client 的 stdio server 設定：

```json
{
  "mcpServers": {
    "pg-codegraph": {
      "command": "python",
      "args": [
        "-m",
        "tools.pg_codegraph_mcp.server",
        "--project-root",
        "H:\\AI\\AI_TOOLS"
      ],
      "cwd": "H:\\AI\\AI_TOOLS"
    }
  }
}
```

## Tools

- `pgcg_index_project`
- `pgcg_search_symbols`
- `pgcg_callers`
- `pgcg_callees`
- `pgcg_context`
- `pgcg_status`

## 目前範圍

第一版先支援 Python AST。JavaScript/TypeScript 可後續加入 tree-sitter 或 language-specific regex extractor。

