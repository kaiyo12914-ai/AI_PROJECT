# 美語學習教室roadmap

## 目的

將 `webapps/englishchat` 從單一 AI 對話頁，逐步擴充為「對話練習、填充測驗、句型重組、翻譯練習、學習追蹤」的美語學習教室。

本 roadmap 以不破壞現有 `start/`、`chat/` API 為前提，優先補足可快速落地、可測試、可逐步擴充的學習模式。

## 現況基線

目前已有：

- 主題選擇與自訂主題。
- 程度選擇：`beginner`、`intermediate`、`advanced`。
- AI 開場對話：`POST /englishchat/start/`。
- AI 對話回覆與修正：`POST /englishchat/chat/`。
- 前端句型建議、卡關提示、修正區。
- LLM 呼叫統一走 `get_chat_model()`。
- 頁面與 API 已使用 `@require_node("englishchat")` / `@require_node("englishchat", api=True)`。

## 原則

- Django URL 不加入 proxy prefix。
- 前端 API 呼叫必須走既有 `apiurl_factory`。
- LLM 呼叫只走 `webapps.llm.llm_factory.get_chat_model()`。
- HTML 不新增大量 inline script/style，功能放在 `static/englishchat/js/index.js` 與 `static/englishchat/css/index.css`。
- 新 API 需維持 JSON-only response，錯誤回應格式包含 `ok: false` 與 `error`。
- 新功能先以 session/front-end state 運作，第二階段再導入 DB 學習紀錄。

## Phase 1：填充測驗 MVP

### 目標

新增「填充測驗」模式，讓使用者依主題與程度練習常用句型、文法與詞彙。

### 功能

- 前端新增模式切換：
  - 對話練習
  - 填充測驗
- 產生填充題：
  - 題目句子。
  - 3 個選項。
  - 正確答案。
  - 繁中解析。
  - 可套用句型。
- 使用者作答後顯示：
  - 正確 / 錯誤。
  - 正解。
  - 簡短解析。
  - 下一題按鈕。

### API

新增：

```text
POST /englishchat/quiz/fill_blank/
POST /englishchat/quiz/check/
```

建議 response：

```json
{
  "ok": true,
  "question_id": "local-generated-id",
  "question": "I usually ____ coffee in the morning.",
  "choices": ["drink", "drinks", "drinking"],
  "answer": "drink",
  "explanation_zh": "主詞 I 搭配原形動詞 drink。",
  "pattern": "I usually + V ..."
}
```

### 技術落點

- `webapps/englishchat/views.py`
  - `api_fill_blank_quiz`
  - `api_check_fill_blank`
- `webapps/englishchat/urls.py`
  - `path("quiz/fill_blank/", ...)`
  - `path("quiz/check/", ...)`
- `webapps/englishchat/static/englishchat/js/index.js`
  - 模式切換。
  - 題目渲染。
  - 選項作答。
- `webapps/englishchat/static/englishchat/css/index.css`
  - quiz panel、choice button、result state。

### 測試

- Unit：prompt 產生與 JSON parse fallback。
- Integration：`quiz/fill_blank/` 回應 schema。
- Integration：`quiz/check/` 能判斷正誤。

### Definition of Done

- 使用者可在同頁切到填充測驗。
- 可依目前主題與程度產生題目。
- 作答後能看到正誤、正解與中文解析。
- LLM 失敗時仍有 fallback 題目。
- `pytest` 最少覆蓋新增 API happy path 與 invalid JSON。

## Phase 2：句型重組與翻譯練習

### 目標

加入更主動的輸出練習，讓使用者從選答案進階到組句與翻譯。

### 功能

- 句型重組：
  - AI 產生亂序單字。
  - 使用者點選 chip 組句。
  - AI 或規則檢查自然度。
- 翻譯練習：
  - 顯示中文情境句。
  - 使用者輸入英文。
  - AI 回覆自然說法、錯誤點與替代表達。

### API

新增：

```text
POST /englishchat/quiz/reorder/
POST /englishchat/quiz/translate/
POST /englishchat/quiz/evaluate/
```

### 技術落點

- 建議新增 `webapps/englishchat/services.py`，避免 `views.py` 過大。
- 將 prompt 拆為：
  - `build_fill_blank_prompt`
  - `build_reorder_prompt`
  - `build_translate_prompt`
  - `build_evaluation_prompt`
  - `parse_llm_json`

### 測試

- Unit：各模式 prompt builder。
- Integration：各 quiz API response schema。
- Frontend smoke：模式切換不破壞既有 chat。

### Definition of Done

- 使用者可完成句型重組與翻譯練習。
- AI 回饋不只判斷文法，也提供自然美語替代表達。
- 前端在手機寬度不重疊、不溢出。

## Phase 3：學習追蹤與複習建議

### 目標

讓系統能記錄學習狀態，提供個人化複習。

### 功能

- 本次練習統計：
  - 題數。
  - 正確率。
  - 常錯項目。
  - 建議複習句型。
- 初期可用 front-end state 或 session。
- 後續導入 DB：
  - 練習紀錄。
  - 題目紀錄。
  - 錯誤類型。
  - 使用者進度。

### 建議資料模型

```text
EnglishPracticeSession
EnglishPracticeAttempt
EnglishLearningWeakness
```

### 測試

- Unit：正確率與弱點分類。
- Integration：紀錄寫入與查詢。
- 權限：只能讀取自己的學習紀錄。

### Definition of Done

- 使用者可看到本次練習摘要。
- 系統能列出 3 個建議複習方向。
- DB 模式符合專案 ENV 規範。

## Phase 4：聽說練習

### 目標

擴充為聽、說、讀、寫整合的美語教室。

### 功能

- TTS：播放 AI 句子美式發音。
- 跟讀：使用者錄音或語音輸入。
- STT：轉文字後交給 AI 評估。
- 回饋：
  - 用詞自然度。
  - 發音提醒。
  - 可替換句型。

### 技術注意

- 若接內網語音服務，需加入 `NO_PROXY`。
- 任何 LLM/STT/TTS client 都應走統一 factory 或 service 層。
- 前端需提供明確 loading/error state。

### Definition of Done

- 可播放 AI 回覆。
- 使用者可語音輸入。
- 系統可產生短句回饋。

## Phase 5：教材與情境包

### 目標

建立可重複使用的主題包，降低每次都依賴 LLM 即時生成的成本。

### 建議主題包

- 自我介紹。
- 旅遊。
- 工作會議。
- 電話應對。
- 餐廳點餐。
- 軍職/公務情境。
- 面試。
- 簡報。

### 每個主題包包含

- 常用句型。
- 常見錯誤。
- 填充題模板。
- 翻譯題模板。
- 對話開場。

### Definition of Done

- 至少 5 個主題包可供選擇。
- 無 LLM 時仍能產生基本練習題。
- LLM 只負責變化題目與評語，不承擔全部教材來源。

## 風險與對策

| 風險 | 對策 |
| --- | --- |
| LLM 回傳非 JSON | 使用 `_extract_json` 與 fallback 題目 |
| LLM 回覆過難 | prompt 強制依 `LEVEL_PROFILE` 控制 |
| 前端模式太多變複雜 | Phase 1 只做填充測驗，模式切換保持簡單 |
| API URL 在 proxy 下錯誤 | 一律使用 `apiurl_factory` |
| 測驗答案外洩 | Phase 1 可先前端顯示答案；Phase 3 再改 session/server-side |
| 學習紀錄涉及個資 | DB 階段加 owner 欄位與 ACL 驗證 |

## 建議優先順序

1. Phase 1：填充測驗 MVP。
2. Phase 2：翻譯練習優先於句型重組。
3. Phase 3：本次練習摘要先不進 DB。
4. Phase 5：建立少量主題包，降低 LLM 依賴。
5. Phase 4：最後再做語音，因環境與瀏覽器權限變數較多。

## 第一個 Sprint 建議

### Sprint 1 範圍

- 新增填充測驗 API。
- 新增前端「填充測驗」模式。
- 新增 fallback 題目。
- 新增 API 測試。

### Sprint 1 不做

- DB 學習紀錄。
- 語音。
- 大量教材庫。
- 使用者長期統計。

### Sprint 1 DoD

- `py -3 -m pytest tests/unit tests/integration -q` 至少相關測試通過。
- 本機 `/englishchat/` 可操作對話與填充測驗。
- proxy prefix 下 API URL 不寫死。
- LLM 失敗時頁面不崩潰。
