# ProjectNotes 參考 Open Notebook 檢討修正 Roadmap

更新日期：2026-04-29

## 目標

參考 `webapps/open-notebook-main` 的架構與功能設計，檢討並修正 `webapps/projectnotes` 子系統，使其成為可維護、可測試、可擴充的專案知識庫與 RAG 問答工具。

本 roadmap 不主張直接移植 Open Notebook。Open Notebook 是獨立 FastAPI + Next.js + SurrealDB 架構；ProjectNotes 必須維持 AI_TOOLS 既有 Django portal 規範、ACL、proxy prefix、DB routing、LLM factory 與 static 規則。

## 參考重點

Open Notebook 可借鏡的部分：
- Domain / service / router 分層清楚，避免 HTTP view 包含過多商業邏輯。
- Notebook、Source、Note、ChatSession、Embedding、Insight 等概念清楚。
- ContextBuilder 將來源、筆記、insight、token budget 統一組裝。
- 長任務以 job/command 模式處理，例如 source vectorize、insight extraction。
- AI model provisioning 集中化，支援不同任務使用不同模型。
- Error handling 有一致分類與 API response。

ProjectNotes 必須保留的本地規範：
- 所有頁面與 API 必須使用 `@require_node("projectnotes")` / `@require_node("projectnotes", api=True)`。
- LLM 呼叫必須使用 `webapps.llm.llm_factory.get_chat_model()`。
- DB 必須遵守 `ENV=EXT/INT` 與既有 DB routing，不新增臨時 DB 連線。
- Template 不新增 inline script/style；JS/CSS 放在 `webapps/projectnotes/static/projectnotes/`。
- URL 不硬寫 `/djangoai`，前端 API 路徑走 `apiurl()` 或既有 prefix-aware helper。
- 檔案需 UTF-8 without BOM。

## 現況問題盤點

已觀察到的高優先問題：
- `views.py` 約五萬行級別，包含 ingestion、chunking、retrieval、LLM synthesis、API response、permission 等混合邏輯，維護風險高。
- `_mock_embedding()` 仍在主流程使用，pgvector 查詢結果不具真實語意搜尋能力。
- `management/commands/projectnotes_weekly_report.py` 仍引用 `ProjectNoteAuditLog`，但目前 models 中未見此模型，疑似舊版殘留。
- `api_digests`、`api_messages`、`audit_page`、`metrics_page`、`api_search`、`api_comments`、`api_audit_logs`、`api_metrics` 等目前疑似 stub 或未完整實作。
- encoding/mojibake 修正邏輯已存在，但規則分散且測試不足。
- citation 與 evidence guard 已有雛形，但尚未形成穩定契約與測試基準。

## Phase 0：基線盤點與安全邊界

範圍：
- 不改功能行為，先建立可回歸的現況基線。
- 釐清 ProjectNotes 現有資料表、URL、前端 API、使用者流程。

工作項目：
- 盤點 `views.py` 所有 API endpoint 的 request/response schema。
- 盤點 models 與 migration 是否一致。
- 檢查 management commands 是否仍可執行。
- 建立 smoke test：
  - portal 顯示 ProjectNotes 入口。
  - ProjectNotes 首頁可 render。
  - `projects/`、`sources/`、`chat/` 基本 API 回應格式穩定。
- 記錄現有 mock embedding 行為與限制。

Definition of Done：
- 完成 endpoint 表與資料表表。
- 所有 stub/壞掉 endpoint 有清單與處理決策。
- 基線測試可在 `tests/integration/` 執行。

## Phase 1：模組化重構

目標：
- 將 `views.py` 拆成可測試單元，降低每次修正的回歸風險。

執行紀錄：
- 2026-04-29 已完成第一批低風險抽離：
  - `api_helpers.py`：JSON request/response、API error、safe text、int parsing、UTF-8 body flag。
  - `embedding_service.py`：暫存 mock embedding adapter，為 Phase 3 真實 embedding 替換預留邊界。
  - `text_processing.py`：文字解碼、mojibake 判斷、文字清洗、chunking、label 清理。
  - `views.py` 移除重複 helper，保留 URL/view function 名稱與既有 API 行為。
  - 新增 `tests/unit/test_projectnotes_phase1_services.py`。

建議目標結構：
- `webapps/projectnotes/services/project_service.py`
- `webapps/projectnotes/services/source_service.py`
- `webapps/projectnotes/services/retrieval_service.py`
- `webapps/projectnotes/services/chat_service.py`
- `webapps/projectnotes/services/citation_service.py`
- `webapps/projectnotes/services/context_builder.py`
- `webapps/projectnotes/serializers.py` 或 `schemas.py`
- `webapps/projectnotes/api_errors.py`

工作項目：
- 保留 URL 與 view function 名稱，先把內部邏輯搬到 service。
- 把 JSON body parsing、API error、safe response 統一。
- 把 permission 檢查從 view 抽成 service/helper。
- 將文字解碼、清洗、chunking 抽出，建立 unit tests。
- 移除未使用或已失效的 backup/stub 依賴。

Definition of Done：
- `views.py` 只負責 ACL、HTTP method、request parsing、呼叫 service、回傳 response。
- 核心服務有 unit tests。
- 外部 URL 與前端呼叫不破壞。

## Phase 2：資料模型與 Notebook/Source/Note 概念對齊

目標：
- 參考 Open Notebook 的概念，讓 ProjectNotes 的專案、來源、版本、chunk、conversation、message、citation 契約清楚。

工作項目：
- 對齊現有模型命名與業務語意：
  - `Project` 對應 Notebook。
  - `Source` / `Document` / `DocumentVersion` 對應來源與版本。
  - `DocumentChunk` 對應可檢索 evidence。
  - `Conversation` / `Message` 對應 ChatSession。
  - `MessageCitation` 對應回答引用。
- 修正 management commands 的舊模型參照。
- 明確定義來源刪除策略：
  - 是否 cascade 刪除 document/version/chunk/citation。
  - 是否保留 activity log。
- 補齊 `ActivityLog` 使用規範與查詢 API。

Definition of Done：
- 模型關聯圖與刪除策略寫入文件或 module docstring。
- 壞掉的 management commands 修正或移除。
- migration 狀態與實際 DB schema 一致。

## Phase 3：真實 Embedding 與檢索品質

目標：
- 移除主流程 mock embedding，建立可重建、可檢查、可評估的檢索流程。

工作項目：
- 建立 embedding service，優先使用 AI_TOOLS 既有模型設定與內部 embedding provider。
- 若目前 llm factory 未提供 embedding，先定義 `get_embedding_model()` 或獨立 projectnotes adapter，但不得在 view 中直接 new 外部 client。
- 支援批次 embedding 與重建索引 command。
- 改善 hybrid retrieval：
  - dense vector search。
  - sparse keyword recall。
  - rerank policy。
  - source diversity。
  - token budget。
- 建立 retrieval evaluation set，包含中文、公文、專案名詞、版本衝突、無答案場景。

Definition of Done：
- 新增來源時產生真實 embedding。
- 可用 management command 重建 project/source embedding。
- 檢索結果可輸出 debug metadata：dense score、keyword score、rerank score、source/version。
- mock embedding 僅允許測試或 EXT mock mode 使用，不進正式 INT 流程。

## Phase 4：ContextBuilder 與回答生成重構

目標：
- 參考 Open Notebook `ContextBuilder`，將來源、版本、chunk、conversation history、citation 統一組成 prompt context。

工作項目：
- 新增 `ProjectNotesContextBuilder`：
  - selected project。
  - selected source/version。
  - conversation history。
  - retrieved chunks。
  - citation candidates。
  - token budget。
- 將 `_llm_synthesize_answer` 改成明確輸入/輸出契約。
- 強制回答遵守：
  - 僅根據 evidence。
  - 不足時明確說明找不到依據。
  - 每個關鍵句附 citation。
  - 中文問題優先繁體中文回答。
- citation guard 改成可測試 pipeline，而不是散落在 view。

Definition of Done：
- chat service 可回傳 answer、citations、warnings、retrieval_debug。
- 無 evidence 時不產生幻覺答案。
- citation conflict warning 有測試覆蓋。

## Phase 5：來源處理與背景任務

目標：
- 避免大型檔案、URL 匯入、embedding 重建卡住 HTTP request。

工作項目：
- 定義 ProjectNotes job model 或使用 Django management command + status table。
- 來源匯入流程拆成：
  - 建立 source/document/version。
  - 抽文字。
  - 清洗與 chunk。
  - embedding。
  - 建立 digest/insight。
- 前端支援 job status polling。
- 失敗任務可重試，錯誤可讀。

Definition of Done：
- 大型檔案上傳不造成 request timeout。
- 使用者可看到處理狀態。
- 失敗來源可重新處理。

## Phase 6：前端體驗與 Portal 規範修正

目標：
- 讓 ProjectNotes 前端成為清楚、可追蹤、可操作的知識工作台。

工作項目：
- 檢查 template 是否有 inline script/style，必要時移至 static。
- 所有 API URL 使用 `apiurl()` 或既有 prefix-aware helper。
- 補齊管理頁：
  - project/source list。
  - source version。
  - embedding status。
  - retrieval debug。
  - audit log。
- citation 點擊可顯示來源、版本、chunk 上下文。
- 對長回答、空狀態、錯誤狀態、權限不足狀態做完整 UI。

Definition of Done：
- IIS `/djangoai` prefix 下所有 API 正常。
- 無 inline JS/CSS 新增。
- citation 可追溯到 source/version/chunk。

## Phase 7：測試、監控與驗收

測試配置：
- Unit 70%：
  - chunking。
  - text decode/clean。
  - query rewrite。
  - retrieval rerank。
  - citation guard。
  - context builder。
- Integration 20%：
  - project/source/chat API。
  - ACL。
  - DB routing。
  - embedding rebuild command。
- E2E 10%：
  - 建立 project。
  - 上傳來源。
  - 等待處理完成。
  - 發問。
  - 檢查回答與 citation。

監控項目：
- source ingest 成功率。
- embedding 失敗率。
- chat latency。
- no-evidence rate。
- citation warning rate。
- 每 project/source 的 chunk count 與索引健康狀態。

Definition of Done：
- 測試納入 `H:\AI\AI_TOOLS\tests`。
- INT 模式不 fallback mock data。
- EXT 模式不連實體 DB。
- 上線前有 rollback 策略。

## Sprint 建議

Sprint 1：
- Phase 0 基線盤點。
- 修正壞掉 command/stub。
- 建立 smoke tests。

Sprint 2：
- Phase 1 拆 service。
- 把 chunking、citation、retrieval policy 補 unit tests。

Sprint 3：
- Phase 3 真實 embedding adapter。
- 建立 rebuild command 與 retrieval debug。

Sprint 4：
- Phase 4 ContextBuilder 與 chat response contract。
- 修正 citation 與 no-evidence 行為。

Sprint 5：
- Phase 5 背景任務。
- Phase 6 前端狀態與管理頁。

Sprint 6：
- Phase 7 E2E、監控、文件、上線驗收。

## 主要風險

- Embedding 維度：現有 `VectorField(dimensions=1536)` 必須與實際 embedding model 一致，不一致會導致寫入或查詢失敗。
- 既有資料：重建 embedding 與 migration 需有備份與回復方案。
- 權限：ProjectNotes 內部 project membership 與 portal ACL 是不同層級，不能混用。
- Open Notebook 差異：SurrealDB graph model 不能直接套到 PostgreSQL/pgvector，需轉成 Django ORM 與 service pattern。
- 長任務：若不先做 job 化，大型來源處理會持續造成 request timeout。
# 最新狀態請參考：`projectnotes參考OpenNotebook檢討修正roadmap_status.md`（已完成 / 進行中 / 未開始）
