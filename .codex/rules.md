# AI_TOOLS 專案規範（Primary Rules）

更新日期：2026-04-20  
適用範圍：`H:\AI\AI_TOOLS`

---

## 1) Mandatory Startup Rule（每次新 session 必做）
1. 進入本專案後，第一步必須讀取：`/.codex/rules.md`。
2. 不可跳過，不可改讀其他 rules 檔替代。
3. `/.codex/rules.md` 為唯一規範來源；專案根目錄不得再維護第二份 `rules.md`。
4. 讀完本檔後，需再讀取：`H:\AI\openclaw-workspace\LONG_TERM_MEMORY.md`。
5. 每個 session 需在 `H:\AI\openclaw-workspace` 建立工作記錄檔：
   - 檔名：`AI_TOOLS_工作記錄_YYYY-MM-DD.md`

---

## 2) 不可破壞之核心規則（MUST NOT MERGE）

### 2.1 URL / Proxy Prefix
1. Django URL 必須支援 proxy prefix（例如 `/djangoai/...`）。
2. 前端 API 路徑一律使用 `apiurl()` 產生，不可硬寫絕對路徑。
3. 不可在 middleware 對 HTML/JS 回應內容做字串替換 prefix。
4. `PROXY_PREFIX`、`FORCE_SCRIPT_NAME`、`PROXY_PREFIX_WRITE_SCRIPT_NAME` 必須一致運作。

### 2.2 前端資源載入
1. HTML 禁止塞大量 inline `<script>` / `<style>`。
2. CSS / JS 應放在 `webapps/<node>/static/<node>/`。
3. Template 需透過 `custom_static`（或專案既有等價 helper）載入靜態資源。
4. 內網工具頁入口腳本禁止使用 `<script type="module">`。內網受管制瀏覽器、舊版核心、代理或 static header 差異，可能導致 module 腳本完全不執行，表現為「按鈕無反應」。
5. 工具頁入口腳本一律使用 `defer` 載入：
   `<script defer src="{% custom_static '<node>/js/<page>.js' %}"></script>`
6. 若確實需要模組能力，優先在一般 `defer` 腳本內使用動態 `import()`；不得以 module script 當作頁面入口。

### 2.3 DB / LLM 工廠
1. DB 連線與查詢統一走 `DB_FACTORY`（`webapps/database/db_factory.py`）。
2. 禁止在功能模組自行 new DB 連線。
3. LLM 呼叫統一走 `get_chat_model()`（`webapps/llm/llm_factory.py`）。
4. 禁止在各模組直接 new OpenAI/Ollama 客戶端。

### 2.4 ACL / require_node
1. 頁面必須加 `@require_node("<node>")`。
2. API 必須加 `@require_node("<node>", api=True)`。
3. 不可繞過 ACL 直接開放端點。

---

## 3) ENV / 執行模式（Mandatory）

### 3.1 EXT / INT DB Mode（強制）
1. `ENV=EXT`：禁止連實體 DB，必須使用 mock 資料。
2. `ENV=INT`：必須連實體 DB，禁止 fallback 到本地/mock JSON。
3. `ENV=INT` 查詢失敗時，必須明確回錯，不可改走 mock。
4. EXT/INT 不可混用，不可「半 fallback」。

### 3.2 NO_PROXY（強制）
下列目標需包含在 `NO_PROXY/no_proxy`：
1. `127.0.0.1`、`localhost`、`::1`
2. 內網服務主機（DB / Ollama / RAG / 內部 API）

---

## 4) 公文子系統防呆（Mandatory）
1. Perspective Logic：LLM 前必須經 `_preprocess_incoming_text`，將相對稱謂替換為具體名稱。
2. Buffer Integrity：前端隱藏欄位清空要同時做：
   - `.value = ""`
   - `.setAttribute("value", "")`
3. case 切換時必須觸發 `resetFocusPick`。
4. `views_parse.py` 的 `out_files` 生成必須 idempotent 且唯一，避免重複計數。

---

## 5) SQL 與分層
1. SQL 應集中於 service/repository 層。
2. View/template 不可直接拼接 SQL。
3. 若為 legacy 特例，需維持可測、可追蹤，且不得再擴散。

---

## 6) UTF-8 / BOM（Mandatory）
1. 全專案文字檔必須使用 UTF-8（無 BOM）。
2. Windows PowerShell 5.1 禁用：`Set-Content -Encoding UTF8`（會寫入 BOM）。
3. 請使用無 BOM 寫法：

```powershell
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
```

4. PowerShell 7 可用 `-Encoding utf8NoBOM`。
5. VS Code 預設編碼需為 `UTF-8`（非 `UTF-8 with BOM`）。
6. 禁止使用 Big5/CP950/GB 作為專案檔案儲存編碼。

---

## 7) 測試規範（vibe coding）
1. 新增或修改功能時，必須同步產出測試。
2. 新子系統開發必須依 `H:\AI\AI_TOOLS\tests` 現有架構，同步補三層測試，不可只寫單層測試後宣稱完成：
   - `tests\unit\`
   - `tests\integration\`
   - `tests\e2e\`
3. 三層測試要求如下：
   - Unit：驗證純函式、service、formatter、validator、權限判斷等可局部隔離邏輯
   - Integration：驗證 view、service、DB_FACTORY、ACL、request/response、mock 外部依賴整合行為
   - E2E：驗證使用者關鍵流程與主要入口行為
4. 新子系統若未附三層測試骨架與對應測試案例，視為未完成，不得合併。
5. 測試採金字塔：
   - Unit 約 70%
   - Integration 約 20%
   - E2E 約 10%
6. 每個測試主題至少含：
   - happy path
   - boundary case
   - error handling
7. 涉及外部 API / DB / 檔案 / 第三方時，優先使用 mock/stub/fake；不得讓 unit test 直接依賴真實外部服務。
8. 測試檔集中於：`H:\AI\AI_TOOLS\tests`
   - `tests\unit\`
   - `tests\integration\`
   - `tests\e2e\`
9. 檔名：`test_<功能名稱>.py`，框架優先 `pytest`。

---

## 8) 變更原則
1. 變更前先確認是否違反本檔任一 Mandatory 規則。
2. 若規則衝突，以本檔為準；無規範時採「最小破壞、可回滾、可測試」原則。
3. 任何會影響 proxy、ACL、DB mode、編碼規則的修改，都需在 PR/commit 說明中明確列出。

---

## 9) Roadmap 管理規範（Mandatory）
1. 新子系統開發時，必須先做需求分析，並在 `H:\AI\AI_TOOLS\.roadmap\` 建立對應 roadmap 檔。
2. 檔名規則：
   - 一般子系統：`<系統名稱>roadmap.md`（例：`XXX系統roadmap.md`）
   - 檔名包含 `roadmap` 或 `ROADMAP` 的文件，一律放在 `.roadmap` 資料夾，不可留在專案根目錄或其他資料夾。
3. roadmap 內容最少必須包含：
   - 需求分析（背景問題、目標使用者、核心需求、非功能需求）
   - 系統開發規劃（Phase/Sprint/里程碑）
   - 完成性進度註記（總完成度、階段進度、待辦與阻塞）
   - 驗收標準（Definition of Done）
4. 進度維護規則：
   - 每次有功能完成、需求變更、風險調整時，必須同步更新對應 roadmap。
   - 更新內容至少要反映完成項目、剩餘風險、下一步計畫。
5. 若 roadmap 與實作狀態不一致，視同規範違反，該變更不得合併（MUST NOT MERGE）。

---

## 附錄 A）舊版 rules.md 完整原文（保留）

```markdown
# DJANGO 主專案規範（Primary Rules）

版本日期：2026-03-23
適用路徑：H:\AI\AI_TOOLS（並作為其他專案主規範來源）

## 規範層級
1. 本檔（H:\AI\AI_TOOLS\.codex\rules.md）為五專案最高規範。
2. 其他專案 rules.md 只能補充，不得與本檔衝突。
3. 發生衝突時，以本檔為準。

## 專案獨立原則
- 每個專案獨立部署、獨立啟動程序、獨立程式碼邊界。
- 禁止以 PYTHONPATH 或直接路徑注入方式跨專案 import 函數。
- 專案間整合僅能透過 API、訊息佇列或明確資料交換流程。

## 共用開發設定
- 共用開發 workspace：H:\AI\openclaw-workspace


## 變更管理
- 任何專案規範調整，先更新本檔，再同步更新其他專案 rules.md。
- 請將長期有效政策同步記錄於：
  H:\AI\openclaw-workspace\LONG_TERM_MEMORY.md

# 專案系統架構與開發規範（精簡強制版）

本文件為強制規範（Mandatory Rules）。
任何違反者，程式碼不得合併（MUST NOT MERGE）。

## 一、適用範圍
- Django 多節點系統（portal / doc / comment / meetingreply / …）
- 前端 JS / HTML Template / Static 資源
- IIS Reverse Proxy（含 proxy prefix）
- DB_FACTORY / LLM_FACTORY
- ACL / require_node / DEV Login

## 二、URL 與 Proxy 規範（核心鐵則）

### 鐵則 1：Django 永遠不寫 proxy prefix
- `urls.py` 不得包含 `/djangoai` 或任何 proxy 前綴
- `PROXY_PREFIX` 只用於 render 與反向代理路徑組裝，不得寫死進 app 路由

```python
# 正確
path("incoming_lookup/", ...)
# 錯誤
path("djangoai/incoming_lookup/", ...)
```

### 鐵則 2：前端不得硬寫任何 prefix / node
- 禁止 `/djangoai/...`
- 禁止 `/doc/...`
- 禁止自行拼接 base URL
- 禁止在 middleware 中用字串替換 response 內容來補 prefix
- 任何 prefix 補齊都必須在 URL / template 生成階段完成，不能事後改 response body

### 鐵則 3：所有 API URL 只能經過 `apiurl()`
- HTML / JS / Template 唯一合法入口：`apiurl(path)`
- `apiurl()` 必須來自 `apiurl_factory`

### 鐵則 4：靜態資源 prefix 由模板標籤控制
- `FORCE_SCRIPT_NAME` 決定 Django 的 `script_name` / 反代基底
- 靜態資源是否輸出 prefix 由 `PROXY_PREFIX_WRITE_SCRIPT_NAME` 控制
- `PROXY_PREFIX_WRITE_SCRIPT_NAME=0` 時，靜態資源輸出不得再次加 prefix
- 靜態資源一律透過自訂模板標籤 `custom_static` 產生，不得直接硬寫 `staticfiles`
- 禁止直接把 IIS 靜態連結指向 `staticfiles` 來取代 Django static 流程

## 三、apiurl_factory 規範（唯一真相）

### 強制規則
- JS 只能讀取 `document.body.dataset.baseUrl`
- 禁止存取：
  - `window.__FORCE_SCRIPT_NAME__`
  - `window.__PROXY_PREFIX__`
  - 任何 ENV prefix
  - 任何硬寫 `/djangoai`

### Template 必須注入
```html
<body data-base-url="{{ request.script_name }}">
```

### 唯一允許的組合邏輯
```js
function apiurl(path) {
  const base = document.body.dataset.baseUrl || "";
  if (!path.startsWith("/")) path = "/" + path;
  return base + path;
}
```

## 四、前端 Static 資源規範（強制）
- HTML 內禁止 `<style>`
- HTML 內禁止大量 `<script>`
- CSS / JS 一律放 `static/`
- 只允許少量 inline 設定注入（≤10 行、無邏輯）

### Static 結構（強制）
```
webapps/<node>/static/<node>/
  css/<page>.css
  js/<page>.js
```

### HTML 標準寫法
```django
{% load custom_tags %}
<link rel="stylesheet" href="{% custom_static '<node>/css/<page>.css' %}">
<script defer src="{% custom_static '<node>/js/<page>.js' %}"></script>
```

- 所有資源必須可被 `collectstatic` 收集
- 靜態資源的實際 URL 必須與 `PROXY_PREFIX_WRITE_SCRIPT_NAME` 相容，不能因本機 8090 直連而多疊 prefix

## 五、DB_FACTORY 規範（強制）
- 禁止自行建立 DB 連線
- 禁止使用舊版 db_factory
- 一律使用 `webapps/database/db_factory.py`
- 僅允許：`db_query_one` / `db_query_all` / `db_execute`

## 六、LLM_FACTORY 規範（強制）
- 禁止直接 new OpenAI / Ollama
- 一律使用 `get_chat_model()`
- 模型切換只能由 ENV 控制

## 七、Settings / ENV 規範
- 所有環境判斷只能在 `settings.py`
- 各模組不得自行判斷 proxy / env / login 行為
- `.env` 必須區分開發與發佈設定，且不得把本機直連 8090 與 IIS 反代部署混用成同一組靜態 prefix 行為
- `PROXY_PREFIX`、`FORCE_SCRIPT_NAME`、`PROXY_PREFIX_WRITE_SCRIPT_NAME` 必須成對維護，不得分散在其他模組手動補字串
- IIS rewrite 導向 8090 時，後端不得再把 prefix 疊加第二次；本機直連與正式反代必須使用不同的 ENV 配置

### 必備 ENV（示例）
```
NO_PROXY=127.0.0.1,localhost,::1,.mpc.mil.tw
FORCE_SCRIPT_NAME=
PROXY_PREFIX=
PROXY_PREFIX_WRITE_SCRIPT_NAME=0
DEV_LOGIN_USER=
DEV_LOGIN_NAME=
```

## 八、NO_PROXY 規範（強制）
必須包含：
- localhost / 127.0.0.1 / ::1
- 內網網域尾碼
- DB / Ollama / RAG host

## 九、ACL / require_node 規範（強制）
- 所有頁面：`@require_node`
- 所有 API：`@require_node(api=True)`
- ACL 判斷集中管理，禁止分散實作

## 十、DEV Login 規範
- 正式環境：只信任 IIS RemoteUser
- DEBUG：允許 `DEV_LOGIN_USER`
- DEV fallback 只能存在於 middleware / utils_login

## 十一、編碼規範（強制）
- 全專案一律 UTF-8（不含 BOM）
- 禁止 Big5 / CP950 / GB 系列
- 不得在 service / view 層進行任何二次 encode/decode

### Sybase 中文處理
- 中文欄位 SQL 必須使用 `CONVERT(VARBINARY)`
- 亂碼問題只能回溯修正 DB_FACTORY / Driver / DSN

## 十二、SQL 集中原則（DOC）
- 所有 SELECT SQL 集中於 service
- View / 子模組不得散落 SQL
- 呼叫端只呼叫 service method

## 十三、DB / Mock 規範
- `ENV=EXT`：停用外部 DB，改用 mock JSON
- `ENV=INT`：一律使用實體 DB
- 不得自行切換 mock 行為
- ENV設定請避免內外網差異，請於系統中進行ENV區隔並同時滿足內外網需求

## Mandatory Startup Rule
- 每次進入本專案（新對話/新 session）必須先讀取 `/.codex/rules.md`，再開始其他工作。
- 每次進入本專案（新對話/新 session）在讀完 `/.codex/rules.md` 後，必須再讀取 `H:\AI\openclaw-workspace\LONG_TERM_MEMORY.md` 最新內容，才可開始其他工作。
- 每次進入本專案（新對話/新 session）在開始開發前，必須再讀取 `H:\AI\openclaw-workspace` 中最新一筆「交接記錄檔」（例如：`AI_TOOLS_交接報告_YYYY-MM-DD.md`）後，方可接續開發。

## UTF-8 / BOM Rule
- 專案文字與程式碼檔案一律使用 UTF-8（無 BOM）。
- 在 Windows PowerShell 5.1，避免使用 `Set-Content -Encoding UTF8`（會寫入 BOM）。
- 請改用：
  `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`
- 在 PowerShell 7 可使用 `-Encoding utf8NoBOM`。
- VS Code 預設編碼請使用 `UTF-8`，不要使用 `UTF-8 with BOM`。

## ENV DB Mode Rule (Mandatory)
- ENV=EXT: MUST NOT connect to physical DB. MUST always use MOCK DATA.
- ENV=INT: MUST always connect to physical DB. MUST NOT use MOCK DATA.
- ENV=INT: MUST NOT fallback to local/mock JSON when DB query fails; return explicit error instead.
- No fallback or mixed mode is allowed between EXT and INT.

## Encoding Rule (Mandatory)
- Avoid PowerShell write methods that may produce UTF-8 with BOM by default.
- Do not use `Set-Content -Encoding UTF8` in Windows PowerShell 5.1 for project files.
- Use no-BOM writing instead:
  - `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))`
  - In PowerShell 7+, prefer `-Encoding utf8NoBOM`.
- VS Code default encoding must be UTF-8 (without BOM).
```
