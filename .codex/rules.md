# AI_TOOLS 專案規範（Primary Rules）

最後更新：2026-06-11  
專案根目錄：`H:\AI\AI_TOOLS`
專案使用Python根目錄：`H:\AI\AI_TOOLS\venv`
---

## 1) 啟動必讀（Mandatory Startup Rule）
1. 每次進入本專案工作前，必讀 `/.codex/rules.md`。
2. 若全域規則與本專案規則衝突，以本檔為準。
3. 每次 session 也要讀取：`H:\AI\openclaw-workspace\LONG_TERM_MEMORY.md`。
4. 重要決策與操作紀錄請寫入 `H:\AI\openclaw-workspace`（檔名建議：`AI_TOOLS_<主題>_YYYY-MM-DD.md`）。

---

## 2) 不可違反規則（MUST NOT MERGE）

### 2.1 URL / Proxy Prefix
1. Django `urls.py` 不可寫入 proxy prefix（例如 `/djangoai`）。
2. 前端 API URL 必須統一透過 `apiurl()` 組合。
3. HTML / JS 不可硬寫 proxy 或 node 前綴。
4. `PROXY_PREFIX`、`FORCE_SCRIPT_NAME`、`PROXY_PREFIX_WRITE_SCRIPT_NAME` 必須一致管理。

### 2.2 前端結構
1. Template 禁止內嵌大量 `<script>` / `<style>`。
2. CSS / JS 必須放在 `webapps/<node>/static/<node>/...`。
3. Script 載入預設使用 `defer`。
4. 頁面邏輯與樣式分離，避免單檔過度膨脹。

### 2.3 DB / LLM
1. DB 存取只能走 `webapps/database/db_factory.py`。
2. LLM 存取只能走 `webapps/llm/llm_factory.py`。
3. Embedding 存取與模型建立只能走 `webapps/llm/embedding_factory.py`。
4. 全系統預設 embedding provider / model 統一為 `OLLAMA / snowflake-arctic-embed2`；新系統不得各自另建 embedding factory。
5. 禁止在功能模組直接建立 DB 連線或模型客戶端。

### 2.4 ACL / require_node
1. 頁面端點必須加 `@require_node("<node>")`。
2. API 端點必須加 `@require_node("<node>", api=True)`。

---

## 3) ENV 與連線政策（Mandatory）

### 3.1 EXT / INT
1. `ENV=EXT`：SQL Server / Oracle / Sybase 依專案政策走 mock（除非明確批准）。
2. `ENV=INT`：必須連實體 DB，不可偷偷 fallback mock JSON。
3. 禁止 EXT/INT 混用 fallback 行為。

### 3.2 NO_PROXY
必須包含：
- `127.0.0.1`
- `localhost`
- `::1`
- 內網網域與必要主機（DB / Ollama / RAG / 內網 API）

---

## 4) 編碼規範（Mandatory）
1. 所有文字檔一律使用 **UTF-8（無 BOM）**。
2. 不得使用 Big5 / CP950 / GB 編碼儲存原始碼與文件。
3. Windows PowerShell 5.1 避免用 `Set-Content -Encoding UTF8` 寫專案檔（會有 BOM 風險）。
4. 優先使用可明確控制編碼的工具／流程，確保 UTF-8 無 BOM。

---

## 5) 測試規範
1. 新功能與重要修正必須補測試。
2. 測試建議目錄：
- `tests/unit/`
- `tests/integration/`
- `tests/e2e/`
3. 至少覆蓋：happy path、邊界條件、錯誤處理。

---

## 6) 資料庫與資料表政策
1. 新增應用資料表必須建立於 PostgreSQL。
2. 資料表變更必須使用 Django migration 管理。
3. 禁止在功能程式中直接建立 ad-hoc table。

---

## 7) 架構政策
1. 新子系統必須整合進既有 Django 專案（`webapps/<subsystem>`）。
2. 禁止建立第二套 Django 專案、第二個 `manage.py`、子專案獨立 `.env` 或 `requirements.txt`。
3. 全專案設定來源統一由 root `.env` + `webproj/settings.py` 管理。

---

## 8) 禁用 Docker（Mandatory）
1. 本專案禁止使用 Docker / Docker Compose / Dockerfile。
2. 開發、測試、部署以本機或內網實體服務為準。

---

## 9) 檔案大小控制
1. 單一來源檔案不得超過 1000 行。
2. 超過 900 行時，後續變更應優先拆模組重構。

---

## 10) 合併門檻
1. 違反本檔 Mandatory 規則，一律 `MUST NOT MERGE`。
2. 任何例外都必須在 PR / commit 記錄理由與範圍。
