專案系統架構與開發規範（正式版｜修訂）

文件目的
本文件定義本專案在 Django + IIS 反向代理 + 多節點（portal / doc / meetingreply / comment …）架構下，
關於 URL 組合、前端資源、資料庫存取、LLM 使用、環境設定、ACL 權限、Proxy 行為的唯一正確實作規範。
本文件屬於「強制規範（Mandatory Rules）」，任何違反本規範之程式碼不得合併（MUST NOT MERGE）。

一、適用範圍（Scope）
本規範適用於：
- Django 專案（portal / doc / comment / meetingreply / …）
- 前端 JavaScript（fetch / XHR）
- 前端 HTML Template（Django templates）與靜態資源（static）
- IIS 反向代理（Reverse Proxy）
- USE_X_FORWARDED_HOST / FORCE_SCRIPT_NAME / request.script_name
- ACL / require_node / 登入身分機制
- DB_FACTORY / LLM_FACTORY

二、URL 組合規範（核心｜必遵）
2.1 URL 的三個層級（必須明確區分）
- 使用者可見 URL：Reverse Proxy（含 proxy prefix，例如 /djangoai/）
- 瀏覽器實際請求 URL：Browser Network → Request URL（唯一事實來源）
- Django 內部路徑：urls.py（永遠不包含 proxy prefix）

2.2 URL 組合鐵則（違反一定出錯）
鐵則 1：Django urls.py 不得包含 proxy prefix
✅ 正確：path("incoming_lookup/", views.incoming_lookup)
❌ 錯誤：path("djangoai/incoming_lookup/", views.incoming_lookup)

鐵則 2：前端 JS 不得寫死任何 proxy / node 前綴
❌ 禁止：fetch("/djangoai/doc/incoming_lookup/");
✅ 正確：fetch(apiurl("doc/incoming_lookup/"));

鐵則 3：所有 API URL 必須經過單一入口函式
不論 HTML / JS / Template，唯一合法入口：apiurl()（由 apiurl_factory 提供）

2.3 環境別 URL 行為對照
(1) 本機開發（一律使用 IIS 反向代理）
- 使用者 URL：http://127.0.0.1/djangoai/doc/
- Proxy Prefix：/djangoai
- JS 呼叫：apiurl("doc/incoming_lookup/")
- Network URL：/djangoai/doc/incoming_lookup/
- Django urls.py：path("incoming_lookup/", …)

(2) 反向代理（/djangoai，IIS）
- 使用者 URL：https://example.gov.tw/djangoai/doc/
- Proxy 行為：/djangoai/* → 127.0.0.1:8000/*
- JS 呼叫：apiurl("doc/incoming_lookup/")
- Network URL：/djangoai/doc/incoming_lookup/
- Django 感知：Django 不需要知道 /djangoai 存在

三、apiurl_factory（全專案唯一允許 URL 組合器）
3.1 核心規則（唯一真相）
每個子系統 JS 都只讀：document.body.dataset.baseUrl
不得碰任何 window 全域 prefix：
- window.__FORCE_SCRIPT_NAME__
- window.__PROXY_PREFIX__
- ENV_PROXY_PREFIX
- 任何硬寫 /djangoai

3.2 Template 強制注入（所有頁面必須）
<body data-base-url="{{ request.script_name }}">
- 本機（IIS 反代）：request.script_name == "/djangoai"
- 反代（/djangoai，IIS）：request.script_name == "/djangoai"

3.3 唯一允許的組合函式（由 apiurl_factory 提供）
規範要求單一入口，全專案統一呼叫 apiurl(...)
function apiurl(path) {
  const base = document.body.dataset.baseUrl || "";
  if (!path.startsWith("/")) path = "/" + path;
  return base + path;
}

3.4 放置位置（全專案共用）
允許放在：portal/static/portal/js/apiurl_factory.js
必須滿足：
- 所有子系統頁面都能引用到
- 引用順序必須在各子系統頁面 JS 之前

四、前端靜態資源分離規範（強制）
4.1 鐵則（Mandatory Rules）
- HTML 禁止內嵌 <style>
- HTML 禁止內嵌大量 <script>
- CSS 必須外掛 static
- JS 必須外掛 static
- Inline script 僅限設定注入（≤10 行）
允許的 inline 例外（僅限設定注入、不得含邏輯）：
- <body data-base-url="{{ request.script_name }}">
- 少量 window.__CFG__ = {...}（不含邏輯、不可做 prefix 推導）

4.2 Static 目錄結構（統一）
webapps/<node>/static/<node>/
├─ css/
│   └─ <page>.css
└─ js/
    └─ <page>.js
禁止：
- 相對硬指 ../static/...
- HTML 內寫實體路徑
- JS 分散於 app 根目錄

4.3 HTML 標準寫法
{% load static %}
<link rel="stylesheet" href="{% static '<node>/css/<page>.css' %}">
<script defer src="{% static '<node>/js/<page>.js' %}"></script>

4.4 Static 發佈規範
- 所有 CSS / JS 必須可被 collectstatic 收集
- 反代（IIS）僅服務 STATIC_ROOT
- Static 404 → 只看 Network → Request URL

五、DB_FACTORY 規範（強制）
5.1 鐵則
- 禁止自行建立 DB 連線
- 外部 DB 一律走 webapps/database/db_factory.py
- 僅允許 db_query_one / db_query_all / db_execute
- 禁止舊版 db_factory

5.2 合法用法
from webapps.database.db_factory import db_query_one
row = db_query_one("oracle", "SELECT ...", {"id": "A123"})

六、LLM_FACTORY 規範（強制）
6.1 鐵則
- 禁止直接 new OpenAI / Ollama
- 一律使用 get_chat_model()
- 模型切換僅由 ENV 控制

6.2 標準用法
from webapps.llm.llm_factory import get_chat_model
llm = get_chat_model()

七、settings.py / ENV 規範
- 所有環境判斷集中於 settings.py
- 各模組不得自行判斷核心行為
必備 ENV（示例｜IIS 反代）：
NO_PROXY=127.0.0.1,localhost,.mpc.mil.tw
FORCE_SCRIPT_NAME=
PROXY_PREFIX=
DEV_LOGIN_USER=（本機 DEBUG 才用）
DEV_LOGIN_NAME=（本機 DEBUG 才用）

八、NO_PROXY 規範（強制）
必須包含：
- 127.0.0.1 / localhost / ::1
- 內網網域尾碼（如 .mpc.mil.tw）
- DB / Ollama / RAG host

九、ACL / require_node 規範（強制）
- 所有頁面必須 @require_node
- 所有 API 必須 @require_node(api=True)
- ACL 判斷集中

十、DEV Login 規範（僅本機）
- 正式環境：只信任 IIS RemoteUser
- DEBUG：允許 DEV_LOGIN_USER
- DEV fallback 僅能存在於 middleware / utils_login

十一、錯誤排查標準流程（SOP）
401 / 403
1) DEV_LOGIN_USER
2) middleware 注入是否生效
3) ACL 設定 / require_node

500 / 502
1) Django 是否在 127.0.0.1:8000 正常運行
2) Reverse Proxy upstream 設定（IIS）
3) MODEL_TYPE / NO_PROXY 是否正確

Static 404
1) Network → Request URL 是否含 prefix
2) 是否指向 STATIC_ROOT
3) 是否執行 python manage.py collectstatic --noinput

十二、規範總結（README 可貼）
- URL 一律由 apiurl() 組合（由 apiurl_factory 提供）
- Django 永遠不寫 proxy prefix
- DB / LLM 一律走 Factory
- ACL 集中、DEV 僅限 DEBUG
- 除錯只看 Network → Request URL
- HTML 禁止內嵌 CSS/JS；必須拆至 static 並經 collectstatic 發佈

十三、編碼規範（強制）
Sybase 中文編碼處理規範（更新）
本專案已統一使用「原廠 Sybase ASE ODBC Driver」，並於 `DB_FACTORY` 層完成正確字元集設定。
因此：所有查詢結果回傳之文字資料，視為已正確解碼之 Unicode，`doc` / `service` / `view` 層不得進行任何二次轉碼或容錯 decode。
檔名、描述文字一律直接使用 DB 回傳值；若出現亂碼問題，僅允許回溯至 `DB_FACTORY` / Driver / DSN 設定修正，禁止於子系統中以 encode/decode workaround 處理。
- 本專案所有程式碼、設定檔與規範文件一律使用 UTF-8 存檔（不使用 Big5/CP950/GB0/ UTF-8 WITH BOM）。
- 新增或修改檔案後，需確認編碼為 UTF-8，避免出現亂碼或跨環境顯示差異。
- 若遇到既有檔案為非 UTF-8，應先轉成 UTF-8 後再修改並提交。

十四、SELECT 語法整合原則
請參考 `class docService()`：
- DOC 子系統中所有被引用的 SQL SELECT 語法，必須集中定義於 `docService`，並加註用途說明。
- 呼叫端統一透過 `docService` 的方法取得資料，不得在各子模組/視圖自行散落 SQL。
- 參考 `views_sybase_import.py` 中 `query_import_from_template` 的呼叫方式，作為統一範例。

十五、Sybase 中文欄位 SQL 規範
目的：避免 Sybase ODBC 對中文欄位錯誤解碼導致亂碼或空白。
- 只適用 Sybase（SQL Server/Oracle 不需套用）。
- 所有可能含中文的欄位，SQL 必須使用 `CONVERT(VARBINARY(4000), <欄位>)`。
- 常見欄位：TM_NAME、TM_RSTP、TD_FORMAT、TD_SUBJ、DF_NAME、EF_NAME，以及 COALESCE(...) 產生的中文欄位。
- BLOB 欄位（DF_DATA/EF_DATA）不需轉換。
- 取回 bytes 後，程式端以正確編碼解碼（例如 `SYBASE_CHARSET=cp950`，必要時嘗試 `utf-16le`）。

範例
SELECT
  CONVERT(VARBINARY(4000), TM.TM_NAME) AS TM_NAME,
  CONVERT(VARBINARY(4000), TM.TM_RSTP) AS TM_RSTP,
  CONVERT(VARBINARY(4000), TD.TD_FORMAT) AS TD_FORMAT,
  CONVERT(VARBINARY(4000), TD.TD_SUBJ) AS TD_SUBJ,
  CONVERT(VARBINARY(4000), DF.DF_NAME) AS DF_NAME,
  CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME
FROM ...

十六、DB及mock JSON引用規範
ENV=EXT 時停用外部 DB，改用 mock JSON（SQLTEST_output.json）。
    ENV=INT 一律使用實體 DB（忽略 FORCE_MOCK_DB）。
    """
