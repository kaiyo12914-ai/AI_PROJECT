# 專案筆記查詢 開發 ROADMAP

## 1. 目標定義
- 在入口頁「美語學習教室」旁新增「專案筆記查詢」。
- 建立「以專案為邊界」的對話式 RAG 工作台，而非一般聊天機器人。
- 核心能力：
  1. `Project` 知識邊界
  2. `Source` 來源治理與手動勾選範圍
  3. `Snapshot/Version` 可重現快照
  4. `Conversation + Citation` 可追溯回答與回跳原文
  5. 證據不足時拒答

---

## 2. 當前已完成（MVP v1）
- 入口卡片新增與 ACL 串接完成。
- 新增 `webapps/projectnotes`：
  - 專案管理 API
  - 來源上傳（txt/md/pdf/docx）
  - chunk 建立與來源啟用/停用
  - 專案內對話問答
  - citation 上下文查詢
  - overview（摘要/FAQ/關鍵詞）
  - 網路搜尋與網址匯入（內容下載後入庫）(已完成)
  - 網頁來源標記為 `reference` 並保存出處 URL (已完成)
  - 對話回答附出處段落（來源/URL/chunk）(已完成)
  - 對話歷史清單與載入 API/UI (已完成)
  - 上傳檔案大小與型別限制 (已完成)
- Django `check` 驗證通過。

---

## 3. 分階段細部工項與驗證

## Phase A：基礎穩定化（先把 MVP 變可靠）
### A1. DB 與 migration 標準化
- 工項：
  1. 套用 migration 到目標環境 (已完成)
  2. 補齊資料表索引檢視（source/chunk/conversation）(已完成)
  3. 確認舊資料庫升級流程文件化 (已完成)
- 驗證：
  1. `python manage.py migrate` 成功
  2. 新建專案、上傳來源、問答流程可完整跑通
  3. `manage.py check` 零錯誤
- 完成標準：INT/EXT 環境可重複部署、資料表一致
  - 補充：`manage.py projectnotes_index_check` 可檢查索引完整性 (已完成)
  - 補充：`documents/projectnotes_舊資料庫升級流程.md` 已建立 (已完成)

### A2. API 例外與輸入防呆
- 工項：
  1. 參數驗證（project_id/source_id/conversation_id）(已完成)
  2. 檔案型別與大小限制 (已完成)
  3. LLM 或解析失敗時回傳一致錯誤格式 (已完成)
- 驗證：
  1. 非法參數不出 500
  2. 不支援檔案型別回 4xx 並有明確錯誤訊息
  3. 壓力下仍可回應拒答而非崩潰
- 完成標準：主要 API 無未處理例外

### A3. 前端互動可靠性
- 工項：
  1. 載入中狀態/按鈕防連點 (已完成)
  2. 錯誤提示統一 (已完成)
  3. citation 面板顯示格式優化 (已完成)
- 驗證：
  1. 連續送出不重覆建立對話
  2. 來源切換後問答範圍正確
  3. 行動版版面可操作
- 完成標準：使用者可無障礙完成「建專案→上傳→提問→查引用」

---

## Phase B：檢索品質升級（接近 NotebookLM 體驗）
### B1. Hybrid Retrieval
- 工項：
  1. 保留關鍵字檢索 (已完成)
  2. 加入 embedding 向量檢索 (已完成)
  3. 合併候選（hybrid merge）與 rerank (已完成)
- 驗證：
  1. 制定 20 題測試集（PRD/會議/API 規格）
  2. 比較 keyword-only vs hybrid 的命中率
  3. 觀察引用內容是否更連續
- 完成標準：測試集命中率提升，錯答率下降

### B2. 上下文補齊策略
- 工項：
  1. 命中 chunk 前後文拼接 (已完成)
  2. 加入 section/title metadata (已完成)
  3. 長段落切分規則校正 (已完成)
- 驗證：
  1. 引用可讀性提升
  2. 回答斷句與脫節現象下降
- 完成標準：引用可直接支撐答案主張

### B3. 拒答與衝突揭露
- 工項：
  1. 證據不足門檻 (已完成)
  2. 來源衝突檢測規則 (已完成)
  3. `not_found_topics` 與 follow-up 問句品質優化 (已完成)
- 驗證：
  1. 無證據問題必拒答
  2. 衝突來源可明確標示雙方引用
- 完成標準：回答可信度可解釋

---

## Phase C：來源治理與版本管理
### C1. Snapshot / Version 管理
- 工項：
  1. 同名來源多版本列表 (已完成)
  2. 支援「僅最新版」或「指定版本」(已完成)
  3. 來源同步操作（手動重建快照）(已完成)
- 驗證：
  1. 舊版/新版回答差異可重現
  2. 同問題在固定快照下輸出穩定
- 完成標準：知識快照可重放、可追溯

### C2. 權限與審計
- 工項：
  1. Project/Source 權限欄位 (已完成)
  2. 查詢審計 log（誰問了什麼、用了哪些來源）(已完成)
  3. 管理者查核頁 (已完成)
- 驗證：
  1. 無權限來源不得進入 context
  2. 稽核記錄完整可追查
- 完成標準：符合內部資料治理要求

---

## Phase D：產品化與營運
### D1. 衍生內容自動生成
- 工項：
  1. 專案摘要 (已完成)
  2. 常見問題 (已完成)
  3. 決策紀錄摘要 (已完成)
- 驗證：
  1. 新專案上傳後可在 30~60 秒內看到導覽內容
  2. 內容可被引用與回跳
- 完成標準：從「問答工具」升級為「專案副駕」

### D2. 觀測指標與品質迭代
- 工項：
  1. 指標：拒答率、引用點擊率、回覆延遲、使用次數 (已完成)
  2. 建立迭代看板與週期回顧 (已完成)
- 驗證：
  1. 每週可輸出品質報表
  2. 有明確改善項與回歸測試
- 完成標準：可持續優化

---

## 4. 測試與驗證清單（每次發版必跑）
- 後端：
  1. `python manage.py check` (已完成：2026-04-15)
  2. migration up/down（測試環境）(已完成：migration up 驗證完成，down 保留測試環境執行)
  3. API smoke test：projects/sources/chat/citation/overview (已完成)
- 前端：
  1. 入口卡片顯示與 ACL 驗證 (已完成)
  2. 專案建立、來源上傳、來源勾選、聊天、引用展開 (已完成)
  3. 手機版（窄寬）可操作 (已完成)
- RAG 品質：
  1. 10 題有答案（須附 citation）(已完成)
  2. 5 題無答案（必拒答）(已完成)
  3. 3 題衝突文件（需揭露衝突）(已完成)

---

## 5. 建議開發順序（短期）
1. 完成 Phase A（穩定性）再上線試點。(已完成)
2. 進入 Phase B（Hybrid + rerank）提升準確率。(已完成)
3. 導入 Phase C（版本與權限治理）對齊企業環境。(已完成)
4. 最後做 Phase D（衍生內容與運營儀表板）。(已完成)

---

## 6. 里程碑交付物
- M1（A 完成）：可穩定運行的 MVP + 基礎測試報告 (已完成)
- M2（B 完成）：檢索品質報告（命中率/錯答率對比）(已完成)
- M3（C 完成）：版本治理與權限審計文件 (已完成)
- M4（D 完成）：產品化功能與運營指標儀表板 (已完成)

---

## 7. 維護更新紀錄
- 2026-04-15：修正「網頁搜尋按鈕無功能」。
- 修正項目：
  1. `api_web_search` 補上 `@csrf_exempt` 與 `@require_node("projectnotes", api=True)`，排除 POST 403。
  2. `api_web_search` 實作 DuckDuckGo HTML 搜尋與前 10 筆結果回傳。
  3. `api_sources_web_import` 實作網址內容抓取、切 chunk、寫入 DB（`reference` 來源）。
  4. `api_projects` / `api_sources` 回傳欄位對齊前端（`source_count`、`title`、`source_version`、`chunk_count`、`reference_url`）。
- 驗證：
  1. `manage.py check` 通過。
  2. `POST /projectnotes/sources/web_search/` 已回 200。
- PostgreSQL 現況：
  1. `projectnotes_db` alias 已存在，並由 `ProjectNotesRouter` 導向 `projectnotes` app。
  2. 已驗證 `connections['projectnotes_db']` 為 PostgreSQL。
  3. 版本：`PostgreSQL 18.3 on x86_64-windows`。
- 本日移交文件：
  1. `../openclaw-workspace/移交工作說明_20260415.md`（已確認路徑可讀）。
