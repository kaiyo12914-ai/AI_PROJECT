# 數位孿生知識庫系統 Roadmap

## 目標

在既有 `H:\AI\AI_TOOLS` Django 專案中整合數位孿生知識庫子系統，不建立獨立 Django 專案。

固定架構：
- Django 主專案：`H:\AI\AI_TOOLS\webproj`
- 子系統 App：`H:\AI\AI_TOOLS\webapps\digital_twin_kb`
- 文件來源：`H:\AI\AI_TOOLS\documents\digital_twin_kb`
- 暫存與上傳檔：`H:\AI\AI_TOOLS\media\digital_twin_kb`
- 環境設定：只使用根目錄 `H:\AI\AI_TOOLS\.env`
- 套件清單：只使用根目錄 `H:\AI\AI_TOOLS\requirements.txt`
- 資料庫：PostgreSQL + pgvector
- 禁止：Docker、Docker Compose、ChromaDB、Qdrant、Milvus、Weaviate、獨立 `manage.py`

## Phase 1：整合到既有專案

- 建立 `webapps\digital_twin_kb` Django app。
- 將原本獨立專案的 knowledge、ingestion、embeddings、rag、taxonomy 整合為同一 app 的模組。
- 將 URL 掛載於 `digital-twin-kb/`，避免污染既有 `/api/`。
- 在 `webproj\settings.py` 加入 app、DRF 與數位孿生設定。
- 在 `PORTAL_ACL` 加入 `digital_twin_kb` 節點。

驗收條件：
- 不存在第二套 `manage.py`、`config/settings.py`、子專案 `.env`、子專案 `requirements.txt`。
- `webapps\digital_twin_kb` 單檔不超過 1000 行。
- 匯入路徑全部使用 `webapps.digital_twin_kb...`。

## Phase 2：資料模型與 migration

- 使用 Django ORM 建立 Document、DocumentChunk、DigitalTwinCategory、QALog、KnowledgeNode、IngestionJob、UserProfile。
- DocumentChunk 使用 pgvector `VectorField(dimensions=384)`。
- migration 建立 `CREATE EXTENSION IF NOT EXISTS vector;`。
- migration 建立 HNSW 向量索引。

驗收條件：
- PostgreSQL migration 可執行。
- `digital_twin_kb_documentchunk.embedding` 為 pgvector 欄位。
- 不新增 SQLite 表。

## Phase 3：文件匯入與 embedding

- 支援 PDF、DOCX、TXT、Markdown、CSV、Excel。
- 支援 `documents\digital_twin_kb` 批次匯入。
- 支援 DRF multipart upload。
- 自動完成文字清理、切段、metadata 分類、embedding、寫入 PostgreSQL。

驗收條件：
- 匯入任務寫入 `IngestionJob`。
- 文件 metadata 寫入 `Document`。
- chunks 與向量寫入 `DocumentChunk`。

## Phase 4：pgvector RAG 問答

- 問題轉 embedding。
- 使用 PostgreSQL pgvector cosine distance 查詢。
- 支援 `security_level`、`twin_level`、`isa95_level`、`system_type`、`topic` 過濾。
- 回答需附來源引用。
- 若未設定 LLM，回傳檢索摘要，不直接失敗。

驗收條件：
- `/digital-twin-kb/api/ask/` 可回傳 answer、sources、retrieved_chunks、similarity_scores。
- 問答紀錄寫入 `QALog`。

## Phase 5：內網與離線部署

- 使用本機或內網 PostgreSQL，不使用 Docker service name。
- embedding model 與 LLM 模型可預先下載到內網環境。
- API 預留 ACL、Session 或 Token 管制。
- 定期備份 PostgreSQL。

驗收條件：
- `.env` 使用明確 PostgreSQL host/IP，例如 `127.0.0.1` 或內網 IP。
- README 或維運文件不出現 Docker 啟動流程。
- 支援封閉式內網與實體隔離環境。