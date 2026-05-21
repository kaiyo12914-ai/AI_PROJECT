# 數位孿生知識庫系統 Roadmap

更新日期：2026-05-22  
維護人員：Antigravity & yuanlinwen-cell  
總體完成度：**90%** (基礎核心 100% 完工，進入 Phase 6 進階精進階段)

---

## 1. 需求分析與系統目標

* **背景問題**：工業 4.0 與數位雙生系統中，包含大量的製造業標準（如 ISA-95）、PLC 控制協議、SCADA 數據流與故障維護指南。這些文件極具專業性，且散落於各處，傳統關鍵字檢索無法進行語意關聯問答。
* **目標使用者**：工業雙生系統開發者、現場工藝工程師、系統維運人員。
* **核心需求**：在 `H:\AI\AI_TOOLS` Django 專案中，以 PostgreSQL + `pgvector` 為核心，打造一個**內網實體隔離環境可用**、具備**安全防護控制**與 **ISA-95 層級分類**的數位雙生 RAG 智能問答與 Ingestion 知識庫 Dashboard 平台。

---

## 2. 系統開發規劃與里程碑

### Phase 1：整合與合規化架構 [已完成 - 2026-05-22]
* **開發規劃**：
  - 建立 `webapps\digital_twin_kb` 子系統，URL 掛載於 `/digital-twin-kb/`，杜絕路徑污染。
  - 將 URL、APP 與 ACL 設定統一註冊進 `webproj\settings.py`。
  - **合規性重構**：為所有 Views 與 ViewSets 加上 `@require_node` 權限裝飾器，實施嚴格的安全防護管制。
  - **冗餘清理**：徹底清理並安全移除重複的 `viewsets.py` 遺留技術債。
* **驗收條件**：
  - 系統自檢無編譯錯誤。
  - APIs 拒絕未經授權的跨節點存取。

### Phase 2：資料模型與 pgvector 遷移 [已完成 - 2026-05-22]
* **開發規劃**：
  - 使用 Django ORM 建立 `Document`、`DocumentChunk`、`DigitalTwinCategory`、`QALog`、`KnowledgeNode`、`IngestionJob`、`UserProfile` 模型。
  - DocumentChunk 的 `embedding` 採用 pgvector `VectorField(dimensions=384)`。
  - 建立資料庫 Migration，自動執行 `CREATE EXTENSION IF NOT EXISTS vector;` 並優化向量索引。
* **驗收條件**：
  - 成功執行 Django migration，向量檢索表架構在 PostgreSQL 生效。

### Phase 3：文件 Ingest 與 Embedding 發送 [已完成 - 2026-05-22]
* **開發規劃**：
  - 支援 PDF 解析與批次資料夾 Ingestion。
  - 提供 DRF Multipart 文件上傳接口，設定主題與安全級別。
  - 自動文字清洗、ISA-95 分類、特徵提取與 Embedding 向量寫入。
* **驗收條件**：
  - Ingestion 進度非同步寫入 `IngestionJob`，供前端監控。

### Phase 4：pgvector RAG 智能對話與 LLM 工廠對接 [已完成 - 2026-05-22]
* **開發規劃**：
  - 支援 `security_level`、`twin_level`、`topic` 過濾，實現列級資料安全防護。
  - **工廠重構**：重構 `llm_service.py`，徹底棄用 direct HTTP 請求，調用專案標準的 `get_chat_model()` 工廠，享有 Proxy 隔離、環境適應與動態模型 Fallback 能力。
  - 若 LLM 未啟用，則自動退化至檢索摘要 (Fallback)，保證可用性。
* **驗收條件**：
  - 對話結果包含 `answer`、`sources` 以及檢索到的 chunks 與相似分數，問答紀錄計入 `QALog`。

### Phase 5：前端 Dashboard 控制台 (方案 A) [已完成 - 2026-05-22]
* **開發規劃**：
  - 建立精美 premium、科技感工業風的雙生 RAG 智能 Dashboard。
  - 左側為智能對話與進階檢索面板；右側為預設匯入、單檔拖放上傳、ISA-95 統計卡片與文檔切片管理 Modal。
  - 實作 Ajax 後台 Job 輪詢（Polling）與 `apiurl_factory` 統一路徑。
  - 修改 Portal `index.html` 將「數位雙生知識庫」卡片按鈕正式掛載上線。
* **驗收條件**：
  - 頁面加載流暢，對話、上傳、輪詢與彈窗功能正常運作，熱重載無 TemplateDoesNotExist 錯誤。

---

## 3. Phase 6：系統精進功能規劃 (已修訂入 Roadmap)

為提升數位雙生知識庫的實戰性能與使用者體驗，特規劃以下四項精進功能：

### 🛠️ 精進 1：多維度混合檢索 (Hybrid Search RAG)
* **背景與目標**：工業領域有大量特定的設備代號（如 `PLC-SCADA-01`）與製造標準代碼。純向量語意檢索容易在此類專有名詞上失真。
* **技術方案**：
  - 結合 PostgreSQL 的 **Full-Text Search (TSVector 全文字詞檢索)** 與 **pgvector 向量語意檢索**。
  - 導入 **Reciprocal Rank Fusion (RRF)** 演算法，對兩種檢索管道的結果進行混合排序與重整，截長補短。
* **驗收標準**：
  - 輸入精確設備代碼時，混合檢索結果之 Recall 召回率比純向量檢索提升 30% 以上。

### 📊 精進 2：基於 Graph RAG 的雙生實體關聯決策
* **背景與目標**：當問及「某設備故障如何處理」時，傳統 RAG 僅能撈取單個片段，無法關聯設備底下的子部件與工藝關係。
* **技術方案**：
  - 活化 `KnowledgeNode` 資料表。在 PDF 匯入時，利用 LLM 自動提取實體關係（設備 ─ 屬於 ─ 系統、故障 ─ 導致 ─ 風險）。
  - 在檢索階段，將向量檢索出的 Chunks 作為種子，延伸查詢其在 `KnowledgeNode` 關聯網絡中的 1-hop 實體與關聯文件，一併餵給 LLM。
* **驗收標準**：
  - RAG 回答中能自動列出與問題相關聯的上下游工業實體關係圖譜摘要。

### 📄 精進 3：PDF 在線雙欄對照與 Evidence 高亮定位跳轉
* **背景與目標**：工程師在查看 RAG 回答的引用來源時，需要核對原始文件所在的頁數與外觀樣式，目前彈窗只能看純文字，體驗有待提升。
* **技術方案**：
  - 前端整合 `PDF.js` 閱讀器。
  - 當點擊引用來源（Evidence Chunk）時，右側以雙欄或彈窗展開 PDF，並自動滾動跳轉至該 Chunk 所在的 `page_number`，並在畫面上以半透明黃色高亮標記該文字區域。
* **驗收標準**：
  - 點擊對話框中的「依據來源」，能在 1 秒內無縫開啟並自動跳轉定位至 PDF 對應頁面。

### ⏱️ 精進 4：非同步 Celery 工作隊列與 Ingest 任務即時日誌流
* **背景與目標**：大批量文件 Ingestion 耗時長。目前的執行緒輪詢無法在關閉瀏覽器後重連，且大檔案容易造成超時。
* **技術方案**：
  - 導入輕量非同步隊列（如專案後台 Celery 或 Redis Queue）。
  - IngestionJob 支援暫停、取消與續傳。
  - 透過 Django Channels (Websocket) 或 Server-Sent Events (SSE)，將後台文字提取與向量寫入的即時 Terminal Log 即時串流至前端，供管理員監控。
* **驗收標準**：
  - 支援同時處理 100+ 份 PDF，關閉瀏覽器再重新打開，Dashboard 能正確恢復並顯示當前 Ingesting 任務的即時日誌。

---

## 4. 完成性進度註記

* **Phase 1 至 Phase 5**：**100% 已完工**，各項重構、ACL 防護、LLM 工廠對接、前端 Dashboard 均已上線運作。
* **Phase 6 進階精進功能**：目前處於**規劃與設計階段**，預計於下一 Sprint 逐步啟動開發。