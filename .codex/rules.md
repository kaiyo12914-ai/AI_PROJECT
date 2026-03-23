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
- 共用虛擬環境優先：H:\AI\VENV3.12
- 回退環境：H:\AI\venv3.12

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

### 鐵則 3：所有 API URL 只能經過 `apiurl()`
- HTML / JS / Template 唯一合法入口：`apiurl(path)`
- `apiurl()` 必須來自 `apiurl_factory`

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
{% load static %}
<link rel="stylesheet" href="{% static '<node>/css/<page>.css' %}">
<script defer src="{% static '<node>/js/<page>.js' %}"></script>
```

- 所有資源必須可被 `collectstatic` 收集

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

### 必備 ENV（示例）
```
NO_PROXY=127.0.0.1,localhost,::1,.mpc.mil.tw
FORCE_SCRIPT_NAME=
PROXY_PREFIX=
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
