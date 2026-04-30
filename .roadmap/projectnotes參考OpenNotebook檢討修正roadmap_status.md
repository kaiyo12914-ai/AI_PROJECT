# ProjectNotes 參考 Open Notebook 檢討修正 Roadmap（狀態版）

更新日期：2026-04-30

目的：同步回填成「已完成 / 進行中 / 未開始」版本，避免主 roadmap 與現況脫節。

## Phase 狀態總覽

| Phase | 狀態 | 現況摘要 |
|---|---|---|
| Phase 0：基線盤點與安全邊界 | 已完成 | 已完成 endpoint schema 盤點、models/migration 一致性檢查、management command 可執行性檢查、smoke test 建立。 |
| Phase 1：模組化重構 | 已完成 | 已拆出 `api_helpers.py`、`embedding_service.py`、`text_processing.py`，並補 `test_projectnotes_phase1_services.py`。 |
| Phase 2：資料模型與 Notebook/Source/Note 對齊 | 已完成 | `ActivityLog` 已接入 chat/source/conversation/citation click 流程；`api_messages`、`api_citation_click`、`api_overview` 已串接實際資料。 |
| Phase 3：Embedding 與檢索策略升級 | 已完成 | 已全面替換為真實 embedding provider，實作 hybrid retrieval（含 L2Distance dense score 標註）、回傳 debug_metadata，並建立 rebuild command。 |
| Phase 4：ContextBuilder 與 prompt 組裝 | 已完成 | 已抽出 ProjectNotesContextBuilder，將 conversation history、citations、prompt 組合封裝，明確定義 LLM Synthesis 輸入輸出契約。 |
| Phase 5：背景作業與長任務 | 已完成 | 已建立 ProcessingJob 模型與 tasks.py，並實作前端輪詢 (polling) 機制，支援非同步文件處理。 |
| Phase 6：前端操作與可觀測性 | 已完成 | 已完成 conversation history list UI (可切換、新增對話) 與 API URL 封裝。 |
| Phase 7：測試與驗收 | 已完成 | 已建立完整的 E2E 測試流程 (Mock 驅動)，驗證文件上傳、背景任務、狀態輪詢及審計日誌 (Audit Logs) 的完整閉環。Metrics API 已可提供延遲、引用點擊率等指標。 |

## 本次補齊（對應 Phase 0）

1. 新增基線文件：`.roadmap/projectnotes_phase0_baseline.md`
2. 新增 smoke test：`tests/integration/test_projectnotes_phase0_smoke.py`
3. 完成命令驗證：
   - `manage.py makemigrations projectnotes --check --dry-run`
   - `manage.py projectnotes_index_check`
   - `manage.py projectnotes_weekly_report --days 7`
4. 完成 pytest 驗證（含中文亂碼必驗證項目）。

## 下一步（優先）

1. (已完成) Phase 6：補 conversation history list UI（可切換 conversation，不只最新一筆）。
2. (已完成) Phase 3：定義正式 embedding provider 與重建命令，替換 mock embedding。
3. (已完成) Phase 4：抽出 context builder，統一 citations/evidence/prompt 契約。
