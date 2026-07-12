# AI_TOOLS 專案規範（Primary Rules）

最後更新：2026-06-13  
專案根目錄：`./`
專案使用 Python 根目錄：`.venv/` 或 `venv/`
---

## 1) 啟動必讀（Mandatory Startup Rule）
1. 每次進入本專案工作前，必讀 `/.codex/rules.md`。
2. 若全域規則與本專案規則衝突，以本檔為準。
3. 每次 session 也要讀取：`../openclaw-workspace/LONG_TERM_MEMORY.md`（若存在）。
4. 重要決策與操作紀錄請寫入同層的 `../openclaw-workspace/`（檔名建議：`AI_TOOLS_<主題>_YYYY-MM-DD.md`）。
5. 閱讀本檔時，須同步閱讀並遵循 PB Web 化專案規範：[AGENTS.md](file:///H:/AI/PB_Source/.agents/AGENTS.md)。

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

### 2.5 路徑表示規範
1. 全專案中之說明文件、程式碼、測試案例與範例，均不得使用硬編碼絕對路徑（例如 `H:\AI\AI_TOOLS\...`）。
2. 所有內部路徑均應採用相對於專案根目錄的相對路徑表示（例如 `./git-push.ps1`）。
3. 對於與本專案相鄰之外部目錄（例如 `H:\AI\openclaw-workspace`），應優先以相對路徑方式表達（例如 `../openclaw-workspace`），以避免依賴磁碟機代號與絕對路徑。
4. 當不同 Windows 磁碟機代號之間無法以通用相對路徑表示時（例如本專案位於 `H:`、外部目錄位於 `D:`），得採用環境變數、設定檔參數或磁碟機代號路徑進行表示。

### 2.6 版本同步規範
1. 每次執行 `git commit` 後，必須立即完成版本同步作業，不得僅停留於本地提交。
2. 版本同步應優先使用專案根目錄工具，且同步順序應依下列方式執行：
   - 先執行：`& './git-push.ps1' -Remote upstream`（目標為 `https://github.com/kaiyo12914-ai/AI_PROJECT.git`）
   - 再執行：`& './git-sync.ps1' -Remote upstream`

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

---

## 11) 版本同步工具（Mandatory）
1. 本專案版本同步優先使用專案根目錄工具：
   - `./git-push.ps1`
   - `./git-sync.ps1`

路徑表示規則：請遵循第 2.5 節路徑表示規範，禁止使用絕對路徑，應使用相對於專案根目錄的相對路徑。
2. 每次執行 `git commit` 後，必須立即執行版本同步作業，不得只停留在本地提交。
3. 一般同步順序：
   - 先執行：`& './git-push.ps1' -Remote upstream`（目標為 `https://github.com/kaiyo12914-ai/AI_PROJECT.git`）
   - 再執行：`& './git-sync.ps1' -Remote upstream`
4. 若預設 `origin` 因 GitHub 權限或憑證問題無法推送，改用已驗證可寫入遠端 `upstream`：
   - `& './git-push.ps1' -Remote upstream`（目標為 `https://github.com/kaiyo12914-ai/AI_PROJECT.git`）
   - `& './git-sync.ps1' -Remote upstream`
5. 本機 Git 若出現 SSL 憑證鏈或撤銷檢查問題，可在本 repo local config 設定：
   - `git config --local http.sslBackend schannel`
   - `git config --local http.schannelCheckRevoke false`
6. 同步完成判定：
   - `git rev-list --left-right --count HEAD...upstream/main` 應為 `0 0`。
   - `git status --short --branch` 應顯示 `main...upstream/main` 且無未提交檔案。
7. 若 `origin/main` 仍顯示 ahead，但 `upstream/main` 已同步，需在回報中明確說明：`origin` 不可用或無權限，實際同步目標為 `upstream`。

---

## 12. 路徑規範

1. 程式碼中不得硬編碼專案根路徑，例如 `H:\AI\PB_Source`、`D:\AI\PB_Source`。
2. 專案根目錄與子目錄一律優先使用相對路徑，或透過共用解析器取得。
3. `.env` 只保留可切換的根目錄設定，例如 `PB_SOURCE_ROOT=.`, `PB_MPCPBL_ROOT=MPCPBL`。
4. Python 工具若需專案根目錄，優先使用共用函式，不得各自寫死磁碟機代號。
5. 文件與範例命令預設使用相對路徑，除非是跨專案或外部環境明確需要絕對路徑。
6. 若因內外網環境不同需要切換根目錄，只能透過 `.env` 或環境變數覆寫，不得直接修改程式常數。

---

## 13. PB Web 查詢框版面規範

1. 後續 PB Web 化頁面之查詢框，必須先查原始 PBL 查詢視窗或主視窗控制宣告，依 DataWindow / window control 的資料格式、控制型別、座標與 width 設計 Web 查詢欄位。
2. 不得將單一查詢欄位預設設為滿版寬度；應依 PBL 原系統設計換算成合理固定寬度，並以 `max-width: 100%` 支援小螢幕收斂。
3. 查詢條件區預設內容寬度以 `900px` 為上限；查詢區本身不得因輸入框過寬產生左右卷軸。
4. 查詢結果表格可依欄位數保留水平卷軸，但查詢框與查詢條件面板不得要求使用者左右拖曳才能操作。
5. 若 PBL 控制宣告有明確輸入格式或 display-only 設定，Web 端需同步反映，例如固定長度代碼、工令號、製令號、年度、日期、下拉選單或唯讀欄位。
6. 所有起始查詢窗之版面配置，必須一律比照 J2352 起始窗的 PB 座標式版面設計模版實作；查詢條件欄位需依原 PBL / DataWindow 座標與 width 換算，不得改用一般 `a-row` / `a-col` 響應式排版取代。

## 14. PB Web 長碼查詢欄位清單規範

1. 後續 PB Web 化程式若主要查詢條件欄位的 PBL / DataWindow data type 或實際欄位長度超過 10 碼，例如工令號、料號、製令號、專案號，除依 PBL 控制項宣告呈現欄位寬度外，必須額外提供可搜尋的可用值清單或下拉選單。
2. 長碼查詢清單可在使用者點選程式、進入頁面或開啟查詢區時預先載入，但不得自動帶入第一筆資料；查詢條件預設應維持空白，讓使用者自行選取或輸入。
3. 清單資料來源應優先使用原 PBL 查詢 DataWindow 的主要來源表或關聯表，並依查詢值去重後回傳 `{ value, label }`；`label` 可附帶關聯欄位輔助辨識，但 `value` 必須保持原查詢欄位值。
4. 若清單資料量可能過大，API 必須支援關鍵字與筆數上限，前端下拉選單必須支援搜尋與清除，且不得因下拉元件寬度造成查詢區左右卷軸。

---

## 15) PB Web 化 Plan 模板使用規範（Mandatory）
1. 每一隻 PB 程式在開始進行 Web 化開發前，必須先建立對應的 `<程式代號>_plan.md`，以對齊 PB Source 的行為與欄位結構。
2. 全系統以以下兩類模板為**主要模板**（必須優先使用與對齊）：
   - **查詢、唯讀與報表型**：使用 [PB_Query_Plan_Template.md](file:///H:/AI/PB_Source/docs/PB_Query_Plan_Template.md)（相對路徑：`../PB_Source/docs/PB_Query_Plan_Template.md`）。
   - **新增、修改、刪除與交易型**：使用 [PB_Maintenance_Plan_Template.md](file:///H:/AI/PB_Source/docs/PB_Maintenance_Plan_Template.md)（相對路徑：`../PB_Source/docs/PB_Maintenance_Plan_Template.md`）。
3. 針對特定特殊情境，可引用以下四類**標準化輔助模板**進行設計輔助與規格化：
   - **共用下拉選單與查找彈窗 (Lookup/DDDW)**：使用 [PB_Lookup_Plan_Template.md](file:///H:/AI/PB_Source/docs/PB_Lookup_Plan_Template.md)（相對路徑：`../PB_Source/docs/PB_Lookup_Plan_Template.md`）。
   - **長時或批次計算背景任務 (Batch Processing)**：使用 [PB_Batch_Processing_Plan_Template.md](file:///H:/AI/PB_Source/docs/PB_Batch_Processing_Plan_Template.md)（相對路徑：`../PB_Source/docs/PB_Batch_Processing_Plan_Template.md`）。
   - **公文套印、PDF產製與實體列印樣式 (Print Layout)**：使用 [PB_Print_Layout_Plan_Template.md](file:///H:/AI/PB_Source/docs/PB_Print_Layout_Plan_Template.md)（相對路徑：`../PB_Source/docs/PB_Print_Layout_Plan_Template.md`）。
   - **外部檔案上傳解析與批次匯入 (File Import)**：使用 [PB_File_Import_Plan_Template.md](file:///H:/AI/PB_Source/docs/PB_File_Import_Plan_Template.md)（相對路徑：`../PB_Source/docs/PB_File_Import_Plan_Template.md`）。
4. 開發前建立之 Plan 必須符合標準骨架，任何與 PB 原始 Source 行為之差異，皆須明列於 Plan 中的「差異與例外清單」中，不得靜默修正。
