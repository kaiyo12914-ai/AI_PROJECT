# Open Notebook 整合 Portal Roadmap

更新日期：2026-04-29

## 目標

將 `webapps/open-notebook-main` 納入 AI_TOOLS portal 的可管控入口，先以獨立服務整合方式上線，再逐步完成反向代理、身分整合、設定集中化與監控。Open Notebook 目前是 FastAPI + Next.js + SurrealDB 專案，不建議第一階段直接改造成 Django app。

## 現況盤點

- Portal：Django app，入口由 `webapps/portal/templates/portal/index.html` 管理，權限由 `settings.PORTAL_ACL` 與 `{% allow %}` 控制。
- Open Notebook：獨立服務，Web UI 預設 `8502`，REST API 預設 `5055`，資料庫使用 SurrealDB `8000`。
- 已完成第一階段 portal 掛載：
  - 新增 `OPEN_NOTEBOOK_PORTAL_URL` 設定，預設 `http://127.0.0.1:8502`。
  - 新增 ACL 節點 `open_notebook`。
  - Portal 首頁新增 Open Notebook 卡片入口。
  - 使用統計預留 `OPEN_NOTEBOOK` 程式代碼。

## Phase 1：入口納管與服務部署

範圍：
- 以 Open Notebook 原生 Docker Compose 或等效服務方式部署。
- Portal 僅提供受 ACL 控制的入口連結，不改動 Open Notebook 原生程式。
- `.env` 設定 `OPEN_NOTEBOOK_PORTAL_URL` 指向正式入口。

需完成項目：
- 確認正式服務位址與 port：Web UI `8502`、API `5055`、SurrealDB `8000`。
- 將 `OPEN_NOTEBOOK_ENCRYPTION_KEY` 改為正式 secret，不可使用範例值。
- 設定持久化資料目錄：`surreal_data`、`notebook_data`。
- 確認 `NO_PROXY` 包含 Open Notebook、SurrealDB、Ollama 或內部模型服務 host。

Definition of Done：
- 使用者從 portal 可看見 Open Notebook 卡片。
- 點擊卡片可在新分頁開啟 Open Notebook。
- 未授權使用者不顯示卡片。
- Open Notebook 重啟後資料仍存在。

## Phase 2：IIS / Reverse Proxy 整合

範圍：
- 將 Open Notebook 服務納入 IIS 或既有反向代理管理。
- 建議路徑：
  - Web UI：`/open-notebook/`
  - REST API：`/open-notebook-api/`

需完成項目：
- 檢查 Next.js 是否支援 basePath 或反向代理 path prefix。
- 若 Open Notebook frontend 不支援子路徑，先以獨立子網域或 port 方式上線。
- 若可支援子路徑，更新 frontend build/runtime 設定與 API base URL。
- 配置 websocket / SSE / streaming response 支援，避免 chat 與 long-running tasks 中斷。

Definition of Done：
- `https://mpcai.mpc.mil.tw/open-notebook/` 可正常載入所有靜態資源。
- REST API docs 或 health endpoint 可透過代理存取。
- 上傳、chat stream、podcast 任務可通過代理運作。

## Phase 3：身分與 ACL 對齊

範圍：
- Portal 控制入口顯示；Open Notebook 內部再補登入或 header-based auth。
- 避免只靠 portal 隱藏卡片作為安全邊界。

需完成項目：
- 盤點 Open Notebook 現有 auth 機制與 password protection。
- 評估 IIS `REMOTE_USER` / header 傳遞到 Open Notebook 的方式。
- 若 Open Notebook 不支援企業 header auth，新增一層 auth gateway 或在 FastAPI middleware 實作。
- 將 `open_notebook` ACL group 納入 Oracle / Django group 管理。

Definition of Done：
- 直接輸入 Open Notebook URL 時仍會要求授權。
- Portal ACL 與 Open Notebook 實際授權策略一致。
- 使用者與群組異動後可在 TTL 內生效。

## Phase 4：AI Provider 與資料治理

範圍：
- 將 Open Notebook 使用的模型、embedding、API key 管理策略與 AI_TOOLS 規範對齊。

需完成項目：
- 評估是否保留 Open Notebook 內建 credential store，或串接 AI_TOOLS `get_chat_model()` / 內部 Ollama。
- 若串接內部模型，設定 OpenAI-compatible endpoint 或 Ollama provider。
- 明確定義資料存放位置、備份策略、附件大小限制與清理政策。
- 敏感資料與 API key 必須以正式 encryption key 加密。

Definition of Done：
- Open Notebook 可使用內部模型或指定外部 provider。
- API key 不落入程式碼與 git。
- 資料備份與還原流程完成演練。

## Phase 5：監控、測試與上線驗收

測試配置：
- Unit：Open Notebook 原生 tests、portal ACL helper。
- Integration：portal 入口顯示、ACL、proxy path、API health。
- E2E：使用者從 portal 開啟 Open Notebook，建立 notebook，上傳來源，發問並取得回答。

需完成項目：
- 新增 smoke test 或 runbook 檢查：
  - Portal home render。
  - Open Notebook Web UI HTTP 200。
  - Open Notebook API health/docs HTTP 200。
  - SurrealDB 可連線。
- 建立服務啟停、log 查詢、資料備份 SOP。

Definition of Done：
- 測試通過並記錄執行方式。
- 服務監控能辨識 Open Notebook Web/API/DB 三層異常。
- 完成上線回復方案：入口下架、proxy rollback、服務停用。

## 風險與決策點

- 子路徑部署風險：Next.js app 若未完整支援 basePath，`/open-notebook/` 會出現靜態資源或 API 路徑錯誤。
- 權限風險：portal 卡片 ACL 只控制入口，不能取代 Open Notebook 服務本身授權。
- 資料風險：Open Notebook 使用獨立 SurrealDB，需獨立備份與容量監控。
- 整合深度決策：若需要與 AI_TOOLS DB_FACTORY / LLM_FACTORY 完全一致，需另開重構專案，不應併入入口納管階段。

