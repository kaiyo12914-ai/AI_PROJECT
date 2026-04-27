# 會議彙辦事項擬答 - RAG 精進策略 ROADMAP

本文件針對目前「會議彙辦事項擬答 (meetingreply)」模組精準度不佳的問題，提出系統性的 RAG 精進策略與後續實作路線圖。

## 一、 當前痛點與現況分析

檢視目前的實作 (`meetingreply/views.py`)，目前 RAG 架構上存在以下可精進之處：

1. **查詢意圖模糊 (Raw Query Issue)**
   目前直接將「指裁示事項 (directive)」或「參謀想法 (staff)」作為檢索詞 (`rag_query`) 進行相似度比對。當會議紀錄文長或語境複雜時，直接 Embedding 會導致語義稀釋，難以命中精確的法規或過往決議。
2. **缺乏混合檢索與二次排序 (No Hybrid Search / Reranking)**
   目前僅依賴單一向量距離 (`dist <= 0.15` 或 `0.25`) 作為閥值，容易錯失依賴「關鍵字」的硬性匹配 (如法規條號、專案代號)，也沒有利用 Reranker 模型進行語意精細排序。
3. **Chunking 與上下文關聯不足**
   原始文件的切分粒度 (Chunk size) 若過小會遺失會議脈絡；若過大則會灌入無效干擾資訊。沒有有效利用 Metadata 進行時間或部門限縮。
4. **生成提示詞 (Prompt) 缺乏推論過程**
   現有 `_build_prompt_short/long` 直接要求吐出結果，缺乏要求模型「先思考再回答 (Chain of Thought, CoT)」的流程設定，容易造成拼湊或幻覺。

---

## 二、 精進 RAG 策略方案

### 階段一：查詢前置優化 (Query Optimization)
*   **Query Rewrite (查詢重寫)**：讓 LLM 先將冗長的「指裁示事項」提煉成「2-3個具體檢索問題或關鍵字」，再進資料庫檢索，大幅提升命中率。
*   **Query Expansion (同義詞擴充)**：若是專有名詞或軍語/行話，可透過自訂字典或 LLM 擴充檢索字詞。

### 階段二：檢索架構升級 (Advanced Retrieval)
*   **Hybrid Search (混合檢索)**：結合 BM25 (關鍵字匹配) + Vector (語義匹配)，以「雙路檢索」相互補足。這樣既不會錯失具體案號，也能捕捉相近語義。
*   **Cross-Encoder Reranking (二次排序)**：從 Vector DB 撈出 Top 15-20 筆後，透過 Reranker 模型 (如 `bge-reranker`) 重新為文件與查詢的相關度打分，最後只取 Top 2-3 給 LLM。
*   **Metadata Filtering (元數據過濾)**：建議在建立索引時即區分「會議年度」、「部門單位」，並於前端檢索時開放時間過濾機制，避免用太舊的會議記錄來擬答。

### 階段三：改進切割與摘要生成 (Chunking & Generation)
*   **Semantic Chunking (語義分塊)**：改變固定字數的切割法，改以「議題段落」或「一問一答」的方式進行切割。
*   **Prompt 結構化**：
    *   強制規定 LLM 在生成「詳答版」時，必須引用檢索編號 (例如 `[來源1]`)。
    *   給予 **Few-Shot Examples (少樣本範例)**，讓模型熟悉長官喜歡的「軍事風格」或「正確的呈報語氣」。

---

## 三、 實作路線圖 (Action Plan)

| 階段 | 預計工作項目 | 效益評估 |
| :--- | :--- | :--- |
| **Step 1: 短期解法 (Quick Wins)** | 1. 調整 `views.py` 的閥值 (`RAG_BASE_MAX_DIST`)，觀察 Embedding 分數常態分佈。<br>2. 實作 Prompt 內的 Few-Shot (給予一兩個完美擬答範例)。<br>3. 在檢索前加入獨立的 Query Rewrite 函式提煉問題。 | 開發快，立即減少答非所問的狀況。 |
| **Step 2: 中期架構 (Core Upgrades)** | 1. 將底層檢索引擎 (`राग_oracle.retrieve`) 改寫為支援 BM25 + Vector 混合檢索。<br>2. 將會議記錄重新整理 Metadata 並重新建立 Embedding Index (避免髒資料干擾)。 | 提升針對性檢索精度，確保能撈到正確條文。 |
| **Step 3: 長期最佳化 (Advanced RAG)** | 1. 實作 Reranker 機制過濾首輪檢索資料。<br>2. 增加 Contextual Compression，把撈出來的 Chunk 先交給小模型摘出重點，才塞進擬答 Prompt。 | 精準度最大化，徹底根除漏判與無關幻覺。 |

---
**維護建議紀錄：**
未來於 `.env` 中可擴充以下變數來開啟進階功能：
*   `RAG_ENABLE_RERANKER=True`
*   `RAG_REWRITE_QUERY=True` 
*   `MEETING_RAG_BM25_WEIGHT=0.4`
