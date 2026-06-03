# 整合 Vanna 2.0：Django + PostgreSQL + Oracle NL2SQL Roadmap

最後更新：2026-06-03

## 1. 策略定位

本專案採「整合 Vanna 2.0」策略，不自研類 Vanna 2.0 工具。

Vanna 2.0 負責：

- schema / documentation / approved examples training。
- 自然語言轉 SQL 的核心能力。
- 產生候選 SQL 與相關上下文。

AI_TOOLS Django 負責：

- Portal 入口、ACL 與使用紀錄。
- PostgreSQL / Oracle 資料源管理。
- `pgvector` 儲存 schema / example embeddings。
- SQL Guard、唯讀執行、審計紀錄與評估資料集。
- 統一使用 `webapps/database/db_factory.py` 與 `webapps/llm/llm_factory.py`。

## 2. 目前整合狀態

- Vanna 2.0 原始碼已由 `D:\AI\vanna` 複製至 `H:\AI\AI_TOOLS\webapps\vanna\vendor\vanna2`。
- 已排除 `.git`、`venv`、`__pycache__` 等不應納入專案的內容。
- Django app 位置為 `webapps/vanna`。
- Portal 的 `NL2SQL 自然語言查詢 DB` 卡片導向 `/nl2sql/`。
- 原本外部 Vanna 節點仍保留，不取代。
- 目前 `/nl2sql/` 是整合狀態頁，尚未開放 DB 查詢。

## 3. 架構原則

- 不建立第二套 Django project。
- 不建立子專案 `.env`、`requirements.txt` 或獨立虛擬環境。
- 頁面端點必須使用 `@require_node("nl2sql")`。
- API 端點必須使用 `@require_node("nl2sql", api=True)`。
- DB 存取只能經由 `db_factory`。
- LLM 存取只能經由 `llm_factory`。
- SQL 預設 generate-only，執行前必須通過 SQL Guard。
- **ENV 政策約束（Mandatory）**：
  - `ENV=EXT`：PostgreSQL 允許連實體，但 SQL Server / Oracle / Sybase 禁止連實體 DB。NL2SQL 對於 Oracle 的 Schema 同步與 SQL 執行必須模擬/走 Mock 機制（如 Mock Schema/Tables 或特定的 Mock SQL 執行結果），禁止在 EXT 下建立與 Oracle/Sybase 實體 DB 的實質連線。
  - `ENV=INT`：必須連接實體 DB，禁止 fallback 到 Mock JSON。

## 4. 目標目錄

```text
webapps/vanna/
  __init__.py
  apps.py
  urls.py
  views.py
  vanna_adapter.py
  service.py
  prompt_builder.py
  schema_retriever.py
  context_packer.py
  sql_guard.py
  sql_dialect.py
  db_executor.py
  schema_introspector.py
  training_service.py
  audit_service.py
  models.py
  migrations/
  management/
    commands/
      nl2sql_sync_schema.py
      nl2sql_embed_schema.py
      nl2sql_sync_vanna_training.py
      nl2sql_run_eval.py
      nl2sql_import_examples.py
  templates/vanna/
  static/vanna/
  vendor/vanna2/
```

## 5. MVP 範圍

- Portal `/nl2sql/` 入口。
- PostgreSQL data source 設定。
- PostgreSQL schema introspection。
- schema object / column metadata 儲存。
- `pgvector` schema embeddings。
- approved question-SQL examples 與 example embeddings。
- Vanna 2.0 training corpus sync。
- minimal RAG：keyword search + vector search + approved example search。
- Vanna 2.0 generate-only SQL。
- SQL Guard：只允許安全 SELECT / WITH SELECT。
- 使用者確認後 readonly execute。
- query log 與審計紀錄。
- 基礎 evaluation dataset。

## 6. Phase 規劃

### Phase 0：整合骨架

- 完成 `webapps/vanna` Django app。
- Portal NL2SQL 卡片導向 `/nl2sql/`。
- 複製 Vanna 2.0 vendor source。
- 建立 `vanna_adapter.py` 介面。
- 建立 SQL Guard prototype。
- `manage.py check` 通過。

### Phase 1：PostgreSQL MVP

- 建立 PostgreSQL data source model。
- 建立 schema sync command (`nl2sql_sync_schema`)。
- 建立 pgvector migration。
- 建立 schema / example embeddings：
  - 實作 `nl2sql_embed_schema` 指令，批次處理尚未計算 Embedding 向量的 Schema DDL 與 Examples，呼叫嵌入模型計算 1536 維度向量並儲存，避免即時查詢時運算造成延遲。
  - 將 RAG 的 `retrieve_context` 由目前的關鍵字分詞打分升級為真正的 pgvector 餘弦相似度向量檢索。
- 串接 Vanna 2.0 generate SQL。
- 建立 generate API 與 query log。
- 加入 readonly execute after confirm。

### Phase 2：Oracle 支援

- Oracle schema sync。
- Oracle dialect prompt。
- Oracle limit injection。
- Oracle SQL Guard。
- Oracle timeout 與 LOB 防護。
- Oracle evaluation cases。

### Phase 3：Training Loop

- approved examples 管理。
- business terms 管理。
- review queue。
- query log 轉 training example。
- rerank 與 eval dashboard。

### Phase 4：權限與治理

- user data source ACL。
- table policy。
- column policy。
- sensitive column deny / mask。
- audit dashboard。

## 7. 核心資料表

- `nl2sql_data_source`
- `nl2sql_schema_object`
- `nl2sql_schema_embedding`
- `nl2sql_training_example`
- `nl2sql_example_embedding`
- `nl2sql_vanna_training_sync`
- `nl2sql_business_term`
- `nl2sql_user_data_source_acl`
- `nl2sql_table_policy`
- `nl2sql_column_policy`
- `nl2sql_query_log`
- `nl2sql_review_queue`
- `nl2sql_eval_case`

## 8. pgvector 策略

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nl2sql_schema_embedding_hnsw
ON nl2sql_schema_embedding
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nl2sql_example_embedding_hnsw
ON nl2sql_example_embedding
USING hnsw (embedding vector_cosine_ops);
```

MVP 可先不啟用 HNSW，先完成正確寫入與查詢；資料量上來後再補 index migration。

## 9. SQL Guard 原則

禁止：

- `DROP`
- `DELETE`
- `UPDATE`
- `INSERT`
- `MERGE`
- `EXEC`
- `CALL`
- `BEGIN`
- `GRANT`
- `REVOKE`
- `ALTER`
- `CREATE`
- `TRUNCATE`

允許：

- 單一 `SELECT`
- 安全 `WITH ... SELECT`
- 系統注入 row limit
- 僅查詢 allowlist table / column

**審查機制精進**：
- 避免單純的字串比對或 Regex（因其容易被註解或巢狀 SQL 繞過）。
- 必須使用 Python 的 `sqlparse` 套件進行**抽象語法樹（AST）解析**。
- 遞迴檢查語法樹中是否僅含有安全的 `DQL`（SELECT/WITH）節點，一旦遍歷發現任何 `DML` 或 `DDL` 的寫入、修改、控制指令，一律判定安全審查不通過並寫入 SQL Guard 審計日誌。

## 10. API 規劃

- `GET /nl2sql/api/data-sources/`
- `POST /nl2sql/api/schema/sync/`
- `POST /nl2sql/api/schema/embed/`
- `POST /nl2sql/api/vanna/sync-training/`
- `GET /nl2sql/api/schema/search/?q=`
- `POST /nl2sql/api/generate/`
- `POST /nl2sql/api/execute/`
- `GET /nl2sql/api/query-logs/`
- `POST /nl2sql/api/review/create/`

## 11. Definition of Done

- `/nl2sql/` 可由 Portal 正確進入。
- Vanna 2.0 vendor source 可被 adapter 載入。
- PostgreSQL MVP 具備 schema sync、embedding、Vanna generate SQL、SQL Guard、readonly execute。
- Oracle Phase 2 具備 schema sync、dialect prompt、SQL Guard 與 readonly execute，且完全符合當前 `ENV`（EXT/INT）的 Mock/實體連線限制。
- Query log 完整記錄 Vanna / prompt / guard / retriever / model / training corpus version。
- **前端開發規範**：
  - 網頁對話 UI 的入口腳本必須使用 `<script defer src="...">` 加載，**禁止使用 `<script type="module">`**。
  - 所有 API 調用請求網址一律使用 `apiurl('/nl2sql/api/...')` 進行拼接，禁止寫死絕對路徑或 proxy prefix。
- **三層測試規格與驗收**：
  - **Unit Tests**：測試 SQL Guard 規則過濾、`extract_sql` 的 SQL 提取邏輯、以及 `retrieve_context` 的 RAG 相似度計分排序。
  - **Integration Tests**：測試 API 端點（如 `/api/generate/`）的請求回傳格式，並驗證搭配 Mock 外部 DB/API 服務時的錯誤處理。
  - **E2E Tests**：在瀏覽器中驗證使用者在 UI 對話窗輸入問題、取得生成的 SQL、預覽並點擊執行，最後將資料以表格/圖表呈現的完整互動流程。
- Unit / integration / E2E tests 覆蓋主要流程。
