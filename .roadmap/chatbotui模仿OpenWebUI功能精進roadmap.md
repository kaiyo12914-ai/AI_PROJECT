# chatbotui 模仿 Open WebUI 功能精進 Roadmap

更新日期：2026-05-05
範圍：`webapps/chatbotui`

---

## 0. 目標

建立一個掛載於 Portal 的通用對話機器人入口，介面與使用習慣接近 Open WebUI，但遵守本專案既有規範：
- Django 子系統化
- ACL / `require_node`
- `llm_factory.get_chat_model()` 統一 LLM 邊界
- Portal 卡片入口與 proxy prefix 相容
- UTF-8 無 BOM

這份 roadmap 用來追蹤 `chatbotui` 從目前的最小可用版，逐步精進成可正式使用的企業內部 AI 對話入口。

---

## 1. 現況 Baseline

目前已完成：
- `chatbotui` 獨立 node 已建立
- Portal 已有入口卡片
- 單頁聊天 UI 已可使用
- 後端已有 `page` 與 `chat api`
- 前端可在 `localStorage` 保存多組對話
- 後端回覆已走 `llm_factory.get_chat_model()`
- 已有基本 integration test

目前缺口：
- 對話沒有 DB 持久化
- 沒有模型切換 UI
- 沒有 system prompt / 參數控制
- 沒有 Markdown / code block 渲染
- 沒有知識庫 / RAG / 檔案上傳
- 沒有管理面板與使用監控
- 沒有多使用者對話隔離的正式資料模型

---

## 2. 精進原則

- 先做可維護的共用能力，再做炫技功能。
- 優先補足 Open WebUI 的核心體驗，不急著複製所有周邊。
- 所有 LLM 呼叫都留在 service/factory 邊界，不把 vendor client 散到 view。
- 先做單純文字對話穩定，再擴充多模態。
- 每個 phase 都要有可驗證的 Definition of Done。

---

## 3. Phase 規劃

## Phase 1：MVP 穩定化

### 目標
- 把目前的最小版整理成可持續迭代的穩定基線。

### 功能
- 對話頁面 UX 微調
- 明確 loading / error / retry 狀態
- Debug 面板只在 DEBUG 顯示
- 回覆區支援基本段落與換行
- 使用者可清空當前對話
- Portal 卡片文案與樣式一致化

### 技術工作
- 抽出 `chat_service.py`，不要讓 view 直接堆 prompt
- 統一 request / response schema
- 補 `safe_text` / prompt builder / error mapping
- log `model_type`、latency、error type

### 測試
- API happy path
- invalid json / missing message
- LLM failure -> 502
- 前端 smoke test 規劃

### Definition of Done
- 頁面可穩定發問、回覆、顯示錯誤
- `pytest tests/integration/test_chatbotui.py -q` 通過
- `py_compile` 通過

---

## Phase 2：正式對話資料模型

### 目標
- 不再只靠 `localStorage`，建立伺服器端正式對話資料。

### 功能
- 建立 Conversation / Message 資料表
- 新增對話列表 API
- 新增建立、重新命名、刪除對話
- 重新整理頁面後可保留歷史
- 依使用者隔離自己的對話

### 建議資料模型
- `ChatbotConversation`
  - `id`
  - `user_id`
  - `title`
  - `created_at`
  - `updated_at`
  - `is_archived`
- `ChatbotMessage`
  - `id`
  - `conversation_id`
  - `role`
  - `content`
  - `model_type`
  - `latency_ms`
  - `created_at`

### 技術工作
- repository / service 分層
- view 改為薄層 CRUD + chat endpoint
- title generation 策略服務化

### 測試
- conversation CRUD integration test
- 權限隔離測試
- repository unit test

### Definition of Done
- 使用者重新整理後仍能看到歷史對話
- 不同帳號不能讀到彼此對話
- DB 存取集中在 repository/service

---

## Phase 3：Open WebUI 核心互動體驗

### 目標
- 讓使用體驗真正接近 Open WebUI 的日常聊天介面。

### 功能
- Markdown 渲染
- code block 樣式與 copy 按鈕
- assistant / user message avatar 區分
- 自動滾動與停止自動滾動邏輯
- 重新送出上一題
- 編輯使用者訊息後重送
- conversation 搜尋
- 釘選 / 封存對話

### 技術工作
- 前端 message renderer 模組化
- 對話列表狀態管理整理
- response metadata 顯示區

### 測試
- renderer unit test
- message edit / resend integration test

### Definition of Done
- 程式碼回覆可讀性明顯提升
- 長對話操作不混亂
- 對話列表能支援大量歷史而不失控

---

## Phase 4：模型與 Prompt 管理

### 目標
- 補足 Open WebUI 常見的模型切換與 system prompt 控制能力。

### 功能
- 模型切換下拉選單
- system prompt 編輯區
- temperature / timeout 基本控制
- 預設 prompt 模板
- 每個對話記錄最後使用的模型設定

### 技術工作
- 建立允許的 model type 白名單
- 前端與後端 schema 增加設定欄位
- service 層保存 conversation config

### 風險
- 不同模型回傳格式差異
- 使用者亂改 prompt 造成品質不穩

### Definition of Done
- 使用者可在同頁切換模型並得到正確回覆
- 設定不會污染其他對話
- log 能追蹤每則回覆使用哪個模型

---

## Phase 5：檔案上傳與上下文增強

### 目標
- 從純聊天升級為可處理工作資料的內部助手。

### 功能
- 上傳文字檔 / PDF / DOCX
- 將附件文字抽取後附加到對話上下文
- 顯示本輪引用哪些附件
- 對話中可切換是否帶入附件內容

### 技術工作
- 抽檔流程 service 化
- 附件 metadata 與 message 關聯
- 大檔截斷與大小限制

### 測試
- 附件解析 happy path
- unsupported file type
- oversized file error

### Definition of Done
- 使用者可在聊天前後附加文件內容
- 錯誤類型可清楚回報
- 不把超長文件整包無限制灌進 prompt

---

## Phase 6：知識庫 / RAG 模式

### 目標
- 提供類似 Open WebUI knowledge / retrieval 的工作模式。

### 功能
- 對話切換為一般聊天 / RAG 聊天
- 可選知識來源
- 顯示引用片段與來源
- 回覆附 citation

### 技術工作
- 串接現有 `projectnotes` 或 `rag_oracle` 能力
- 建立 `chatbotui_rag_service.py`
- 來源片段格式標準化

### 依賴
- 現有知識檢索服務穩定
- ACL 與資料來源權限一致

### Definition of Done
- 使用者可明確知道答案是模型生成還是知識庫引用
- 引用來源可追查
- RAG 失敗時不靜默冒充引用成功

---

## Phase 7：管理、觀測與治理

### 目標
- 讓 `chatbotui` 能成為正式內部入口，而不是只有 demo。

### 功能
- 使用量統計
- 每模型呼叫次數 / 錯誤率 / latency
- fallback / error dashboard
- 管理員檢視熱門 prompt 類型
- 軟刪除與清理機制

### 技術工作
- 結構化 logging
- metrics aggregation
- 後台管理頁或 usage API

### Definition of Done
- 能回答「誰在用、怎麼用、哪裡慢、哪裡常錯」
- 問題排查不需要直接翻原始 console log

---

## 4. 優先順序

1. Phase 1：先把現有 MVP 穩定化
2. Phase 2：補正式 conversation/message 資料模型
3. Phase 3：把互動體驗做成真正可用
4. Phase 4：補模型與 prompt 管理
5. Phase 5：補附件上下文
6. Phase 6：接 RAG / 知識庫
7. Phase 7：補治理與觀測

---

## 5. 風險清單

| 風險 | 說明 | 緩解方式 |
| --- | --- | --- |
| LLM 回覆不穩 | 模型可能超時、503、空字串 | retry、error mapping、明確 fallback |
| 對話資料暴增 | message 與附件內容快速膨脹 | 分頁、截斷、保留策略 |
| 權限隔離不足 | 使用者看到不屬於自己的對話 | conversation owner 檢查 + integration test |
| Prompt 污染 | 使用者任意 system prompt 造成品質下降 | 預設模板、白名單、管理策略 |
| RAG 冒充答案 | 檢索失敗但仍回一般模型答案 | 明確 mode 標記與 citation 檢查 |

---

## 6. 建議第一輪實作切片

### Sprint 1
- Phase 1 全部
- Phase 2 的 Conversation / Message model
- 對話列表 API

### Sprint 2
- Phase 2 剩餘 CRUD
- Phase 3 的 markdown / code block / copy

### Sprint 3
- Phase 4 模型切換與 system prompt
- Phase 5 附件上傳基礎版

---

## 7. Definition of Success

- Portal 中出現一個可正式使用的通用 AI 對話入口
- 一般問答、程式協助、文字草稿整理都可在同一介面完成
- 對話歷史可保存、搜尋、整理
- 後端能追蹤模型、錯誤、延遲
- 後續要接 RAG、附件、多模型時，不需要推倒重做

---

## 精進現況（2026-05-06）

### 已完成
- 修正 webapps/llm/llm_factory.py 縮排問題，排除 IndentationError，get_chat_model() 可正常載入。
- 修正設定 API 參數不一致：ChatbotUIService.update_conversation_config() 已補上 chat_mode、ag_source。
- 修正附件刪除後仍被引用風險：
  - 後端附件提示查詢改為綁定 user_id + conversation_id + is_archived + is_deleted。
  - 前端刪除附件後改為重新向後端拉取清單，避免 UI 與 DB 狀態不同步。
- 新增 PostgreSQL 使用者個人化設定表 chatbotui_user_profile（user_id 為 PK）。
- 已串接個人化設定流程：
  - 建立新對話時套用使用者預設。
  - 儲存設定/切換模型時同步回寫使用者預設。

### 進行中
- 明確區分「使用者預設設定（profile）」與「單一對話覆寫設定（conversation）」的展示與行為。

### 下一步
1. 補 chatbotui_user_profile 的 repository/service 整合測試（含 upsert、建立新對話套用）。
2. API 增加設定來源標記（profile / conversation_override）。
3. UI 增加「恢復個人預設」操作與提示。
## 精進現況更新（2026-05-07）

### Phase 3：大致完成，持續開發
- 已完成：對話主區互動、重送/重生、訊息區主要功能可用。
- 新增：前端訊息 meta 顯示可帶出附件/RAG 用量欄位（attachment_count、citation_count、rag_reason）。
- 待完成：訊息操作 UX 細節（例如 toast/複製回饋一致性）與更多前端互動測試覆蓋。

### Phase 5：核心已完成
- 已完成：附件上傳/刪除/提示注入流程可用。
- 已修復：附件刪除一致性問題（前端刪除後回補後端清單，後端列表查詢加上 user/conversation/is_deleted/is_archived 條件）。
- 持續精進：附件錯誤提示文案與大檔案/異常類型細緻化。

### Phase 6：部分完成，持續精進
- 已完成：RAG 入口與 chatbotui_rag_service.py 接入。
- 已完成：API meta 回傳 ttachment_used、ttachment_count、ag_used、citation_count、ag_reason。
- 已完成：前端已將上述 usage meta 套用到最新 assistant 訊息顯示。
- 待完成：citation 明細展示 UI、RAG 來源可視化與更多檢索品質測試。

### 本次驗證
- 
ode --check webapps/chatbotui/static/chatbotui/js/index.js：通過。
- 
ode --test tests/unit/test_chatbotui_ui_hooks.mjs：2 passed。
- pytest -q tests/integration/test_chatbotui_actions.py：12 passed。