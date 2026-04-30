# ProjectNotes Phase 0 Baseline

更新日期：2026-04-30

## 1) `views.py` API Endpoint 盤點（request/response schema）

| Endpoint | Method | Request（重點欄位） | Response（重點欄位） | 狀態 |
|---|---|---|---|---|
| `/projectnotes/projects/` | GET | 無 | `ok`, `projects[]`, `can_manage_projects` | 已實作 |
| `/projectnotes/projects/` | POST | `name`, `description` | `ok`, `project{id,name}` | 已實作 |
| `/projectnotes/sources/` | GET | `project_id` | `ok`, `sources[]` | 已實作 |
| `/projectnotes/sources/` | POST | form-data: `project_id`, `title`, `file` | `ok`, `source`, `document`, `detected_encoding`, `chunk_count` | 已實作 |
| `/projectnotes/sources/<id>/` | DELETE/POST | path `source_id` | `ok`, `deleted`, `summary` | 已實作 |
| `/projectnotes/sources/versions/` | GET | `project_id` | `ok`, `items[]` | 已實作 |
| `/projectnotes/sources/<id>/content/` | GET | path `source_id` | `ok`, `source`, `chunks[]` | 已實作 |
| `/projectnotes/sources/<id>/toggle/` | POST | path `source_id` | `ok/error` | Stub（Not implemented） |
| `/projectnotes/sources/<id>/resync/` | POST | path `source_id` | `ok/error` | Stub（Not implemented） |
| `/projectnotes/conversations/` | GET | `project_id` | `ok`, `conversations[]` | 已實作 |
| `/projectnotes/conversations/` | POST | `project_id`, `title` | `ok`, `conversation` | 已實作 |
| `/projectnotes/conversations/` | PATCH/PUT | `conversation_id`, `title` | `ok`, `conversation` | 已實作 |
| `/projectnotes/conversations/` | DELETE | `conversation_id` | `ok`, `deleted` | 已實作 |
| `/projectnotes/chat/` | POST | `project_id`, `question/query`, `conversation_id?`, `selected_source_ids?` | `ok`, `conversation_id`, `answer`, `citations[]`, `turn` | 已實作 |
| `/projectnotes/messages/` | GET | `conversation_id` | `ok`, `conversation`, `messages[]` | 已實作 |
| `/projectnotes/citation_click/` | POST | `project_id`, `source_id`, `chunk_index?`, `conversation_id?`, `ref?` | `ok` | 已實作 |
| `/projectnotes/citation/` | GET/POST | - | `ok/error` | Stub（Not implemented） |
| `/projectnotes/overview/` | GET | `project_id` | `ok`, `overview{summary,faq,keywords,decisions}` | 已實作 |
| `/projectnotes/audit_logs/` | GET | `project_id?`, `user_id?`, `limit?` | `ok`, `rows[]` | 已實作 |
| `/projectnotes/metrics_api/` | GET | `project_id?`, `days?` | `ok`, `days`, `metrics{...}` | 已實作 |
| `/projectnotes/digests/` | GET/POST | - | `ok/error` | Stub（Not implemented） |

## 2) Models 與 Migration 一致性

執行：

```powershell
.\venv\Scripts\python.exe manage.py makemigrations projectnotes --check --dry-run
```

結果：

- `No changes detected in app 'projectnotes'`
- 判定：`models.py` 與 migration 定義一致（至少在 Django schema diff 層面無差異）。

## 3) Management Commands 可執行性

執行：

```powershell
.\venv\Scripts\python.exe manage.py projectnotes_index_check
.\venv\Scripts\python.exe manage.py projectnotes_weekly_report --days 7
```

結果摘要：

- `projectnotes_index_check` 可執行，回報目前 DB 中：
  - `projectnotes_conversation` 存在且索引檢查通過（`project_id`, `updated_at`）。
  - `projectnotes_document_chunk` / `projectnotes_message` / `projectnotes_activity_log` 顯示 `table missing`（屬於目前資料庫現況，不是 command 執行失敗）。
- `projectnotes_weekly_report --days 7` 可執行，並輸出 usage/query/latency 指標。

## 4) Smoke Test 基線

新增檔案：

- `tests/integration/test_projectnotes_phase0_smoke.py`

覆蓋項目：

- portal template 含 ProjectNotes 入口（ACL + URL）。
- ProjectNotes 首頁可 render。
- `projects` API 有基礎 success schema。
- `sources` 與 `chat` 在缺參數情境會回傳標準 error schema（`ok=false` + `error`）。

驗證命令：

```powershell
.\venv\Scripts\python.exe -m pytest tests/integration/test_projectnotes_phase0_smoke.py
```

結果：`4 passed`
