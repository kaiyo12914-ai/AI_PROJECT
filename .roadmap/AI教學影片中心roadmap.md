# AI教學影片中心roadmap

狀態：規劃中（待 Sprint 1 開始）
適用專案：`H:\AI\AI_TOOLS`
子系統名稱：`videolearning`（教學影片中心）

## 1. 目標與範圍

本系統先不做大型影音平台，第一階段定位為：

- 內網 AI 教學影片知識庫
- 影片管理
- 章節檢索
- AI 問答
- 權限控管

核心原則：

- 先能用、可維護、可擴充
- 先完成骨架與低風險落地，再逐步加推薦、學習紀錄、測驗、儀表板

## 2. 專案規範對齊

沿用既有 AI_TOOLS / Django Portal 規範，不另起新架構：

- ACL：`@require_node("videolearning")`、`@require_node("videolearning", api=True)`
- Proxy Prefix：前端不可硬寫 `/djangoai`，必須走 prefix-aware helper（如 `apiurl()`）
- LLM：只能經由 `webapps/llm/llm_factory.py`
- DB：只能經由 `webapps/database/db_factory.py` 與既有 routing
- ENV：遵守 `ENV=EXT/INT`，內網 INT 模式限制 provider（OLLAMA/LM_STUDIO）
- Static：不得新增 inline script/style，資源放 `webapps/videolearning/static/videolearning/`
- 編碼：UTF-8 without BOM
- 測試：新增功能需同步補 `H:\AI\AI_TOOLS\tests` 下 pytest（正常/邊界/錯誤）

## 3. 建議目錄

```text
webapps/videolearning/
  urls.py
  views.py
  models.py
  services/
  templates/videolearning/
  static/videolearning/
```

## 4. MVP 功能（第一期）

1. 影片庫：上傳、登錄、封面、分類、標籤
2. 課程/播放清單：多影片組課程
3. 播放：章節跳轉與播放紀錄
4. 逐字稿：上傳字幕或轉錄文本
5. 章節切分：AI/規則切分章節
6. AI 問答：影片或課程範圍問答
7. 搜尋：標題/標籤/逐字稿/章節
8. 權限：部門/角色/群組控制

## 5. 資料模型草案

- VideoCategory
- VideoTag
- VideoAsset
- VideoTranscript
- VideoChapter
- VideoPlaylist
- VideoPlaylistItem
- VideoEmbeddingChunk
- VideoChatSession
- VideoChatMessage
- VideoCitation
- VideoViewLog
- VideoProcessingJob

`VideoAsset.status` 建議值：

- `draft`
- `processing`
- `ready`
- `failed`
- `archived`

## 6. AI 設計重點

1. Transcript 來源
- 手動上傳：`.txt/.srt/.vtt`
- 預留 adapter：LocalWhisper/OpenAIWhisper/Manual

2. 章節產生
- 先 rule-based fallback
- 再接 LLM 章節生成（必須走 `llm_factory`）

3. 問答檢索優先序
- 目前影片章節 chunk
- 目前影片 transcript chunk
- 同課程其他影片 chunk
- 使用者指定範圍

4. 回答需附 citation
- 影片名稱
- 章節
- 時間碼（start/end）

## 7. Phase Roadmap

### Phase 0：基線與規格盤點

交付：
- app skeleton
- URL/ACL/選單入口
- 儲存路徑與 INT/EXT 差異
- 上傳大小與串流策略確認
- smoke test

DoD：
- Portal 可見入口
- 首頁可開啟
- 權限不足不可進入
- EXT 不碰正式 DB/檔案區

### Phase 1：影片管理 MVP

交付：
- `VideoAsset` + Category/Tag
- 上傳 API / 清單頁 / 詳細頁 / 基本播放
- metadata 編輯

測試重點：
- 建立影片正常
- title 空白錯誤
- 權限不足
- 影片不存在

### Phase 2：課程 / 播放清單

交付：
- Playlist / PlaylistItem
- 排序
- 課程頁與連續播放
- 基礎進度紀錄

### Phase 3：逐字稿與章節

交付：
- Transcript model/API
- txt/srt/vtt parser
- Chapter model
- 章節跳轉

### Phase 4：Embedding 與搜尋

交付：
- chunking
- embedding service adapter
- `VideoEmbeddingChunk`
- rebuild embeddings command
- keyword/semantic/hybrid search API

注意：
- embedding 維度必須與模型一致
- INT 不可用 mock embedding

### Phase 5：AI 問答

交付：
- ChatSession/Message/Citation
- ContextBuilder（集中組 prompt context）
- citation guard / no-evidence response

### Phase 6：背景任務

交付：
- ProcessingJob
- polling
- transcript/embedding jobs
- retry/可讀錯誤

### Phase 7：學習紀錄與儀表板

交付：
- ViewLog / completion rate
- 熱門影片/熱門問題
- 無答案問題清單
- 教材缺口分析

## 8. Sprint 建議（6 個）

1. Sprint 1：Skeleton + Portal 掛入
2. Sprint 2：影片管理 MVP
3. Sprint 3：課程/播放清單
4. Sprint 4：Transcript/Chapter
5. Sprint 5：Embedding/搜尋
6. Sprint 6：AI 問答/citation/驗收

## 9. 第一個執行任務（建議）

先做低風險骨架，不做 AI/embedding/上傳：

- 建立 `webapps/videolearning` app skeleton
- 首頁 view + `urls.py`
- `templates/videolearning/index.html`
- `static/videolearning/videolearning.css`、`videolearning.js`
- 頁面加 `@require_node("videolearning")`
- API 預留 health endpoint + `@require_node("videolearning", api=True)`
- 新增 smoke test（首頁/health）

## 10. 追蹤方式

- 每個 Phase 完成後，同步更新狀態檔（可另建 `AI教學影片中心roadmap_status.md`）
- 每個 Sprint 結束需回填：
  - 修改檔案
  - migration 影響
  - 測試覆蓋
  - 未覆蓋風險
