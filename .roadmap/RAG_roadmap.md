# RAG_roadmap.md

更新日期：2026-04-21
適用範圍：`./`（projectnotes 為優先落地場域）
標竿目標：以 NotebookLM 體驗為參考，建立「來源中心、精準檢索、可追溯回答、可再製輸出」的 RAG 工作台。

---

## 0. 目標定義（類 NotebookLM）

### 0.1 產品目標
- [ ] 來源中心化：回答以使用者上傳來源為主，不越界臆測。
- [ ] 查詢精準命中：Query understanding + Hybrid retrieval + Rerank。
- [ ] 回答可追溯：回答段落可回指文件/段落/頁碼。
- [ ] 知識再製：摘要、FAQ、心智圖、簡報大綱、測驗、語音稿。
- [ ] 工作流導向：研究、教學、稽核、內訓、知識移轉可直接使用。

### 0.2 完成性進度註記
- 整體進度：`18%`
- 已完成：
  - [x] 對話一問一答同框化
  - [x] LLM 回覆中文保底（含二次繁中改寫）
  - [x] 通用條款來源降權 + 定義型問題加權（第一版）
- 進行中：
- [ ] Query rewrite / decomposition / expansion
  - 已完成 Query rewrite（rule-based v1）；decomposition/expansion 待續。
- 待開始：
  - [ ] Hybrid sparse+dense
  - [x] Rerank（heuristic + diversity v1）
  - [ ] NotebookLM-style 多形式輸出

---

## 1. 系統架構（8 段式）

### 1.1 Ingestion
- [ ] PDF/DOCX/PPTX/HTML/字幕/音訊解析器統一化
- [ ] 結構抽取：標題、章節、頁碼、表格、圖說、時間資訊
- [ ] metadata 標準欄位：來源名、版本、部門、建立時間、段落 ID

### 1.2 Chunking
- [ ] 標題感知切分（H1/H2/H3）
- [ ] 語意單位切分（定義/流程/表格說明）
- [ ] parent-child chunk
- [ ] chunk overlap 策略（可配置）

### 1.3 Query Understanding
- [ ] Intent classification（定義/比較/流程/時序/數值/定位）
- [x] Query rewrite（rule-based v1）
- [ ] Multi-query expansion（3-5 組）
- [ ] Query decomposition（complex query）
- [ ] Constraint extraction（時間/版本/部門/文件型態）

### 1.4 Retrieval
- [ ] Dense retrieval（embedding）
- [ ] Sparse retrieval（BM25 / full-text）
- [ ] Metadata filter（來源、版本、日期）
- [ ] 標題索引加權

### 1.5 Rerank
- [ ] Cross-encoder rerank（top 30~50）
- [ ] LLM rerank（可選，高品質低速）

### 1.6 Context Builder
- [ ] 去重
- [ ] 相鄰 chunk 合併
- [ ] 多來源平衡
- [ ] token budget 控制

### 1.7 Answer Engine
- [ ] Grounded answer（來源不足即明示）
- [ ] Citation-first（結論綁引用）
- [ ] Conflict detection（版本衝突、來源差異）
- [ ] Answer mode（精簡/專家/教學/比較/簡報/FAQ）

### 1.8 NotebookLM-style Outputs
- [ ] 單文件摘要
- [ ] 多文件比較摘要
- [ ] FAQ 自動生成
- [ ] 心智圖
- [ ] 簡報大綱
- [ ] 測驗/抽認卡
- [ ] 語音稿/podcast 草稿

---

## 2. 分階段 Roadmap

### Phase 1：先把「準」做好（核心命中率）
進度：`35%`
- [x] 通用條款來源降權（第一版）
- [x] 定義型 query 加權（第一版）
- [x] Query rewrite（rule-based v1）
- [x] Hybrid search（dense+sparse v1）
- [x] Rerank（heuristic + diversity v1）
- [x] citation answer 強化（句子級補引用 + 來源衝突提示 v1）

KPI：
- Top-5 Recall
- MRR / nDCG
- Citation Accuracy
- Hallucination Rate

### Phase 2：做出「像 NotebookLM」的體驗
進度：`0%`
- [ ] source-centric workspace 強化
- [ ] 單文件/多文件摘要
- [ ] 問題推薦
- [ ] FAQ/心智圖/簡報大綱
- [ ] 語音講稿

### Phase 3：企業知識作業平台化
進度：`0%`
- [ ] 權限隔離與多租戶策略
- [ ] 版本治理與審核追蹤
- [ ] 部門知識庫
- [ ] 評估儀表板
- [ ] 多代理任務流

---

## 3. 提示詞策略（最小可行 5 組）
- [ ] Query Rewrite Prompt
- [ ] Query Decomposition Prompt
- [ ] Retrieval Intent Prompt
- [ ] Relevance Judge Prompt
- [ ] Grounded Answer Prompt

提示詞治理：
- [ ] 版本化（prompt_id + changelog）
- [ ] A/B 比對（命中率、引用率、延遲）
- [ ] 回歸測試集（固定問題集）

---

## 4. 評估機制（Retrieval / Generation 分離）

### 4.1 Retrieval 指標
- [ ] Query Success Rate
- [ ] Top-k 命中率
- [ ] Coverage（是否漏關鍵來源）
- [ ] Latency（P50/P95）

### 4.2 Generation 指標
- [ ] Citation Accuracy
- [ ] Faithfulness
- [ ] Task Completion Rate

### 4.3 每週例行
- [ ] 週報輸出：命中率、引用率、錯誤案例 Top 10
- [ ] 錯誤歸因：Query 問題 / 檢索問題 / 生成問題

---

## 5. 立即執行順序（依序精進）

1. [x] Query rewrite（先上，rule-based v1）
2. [x] Hybrid retrieval（dense+sparse v1）
3. [x] Rerank（heuristic + diversity v1）
4. [x] Citation answer 強化（句子級補引用 + 來源衝突提示 v1）
5. [ ] Semantic + parent-child chunking
6. [ ] FAQ/摘要/心智圖/簡報輸出

---

## 6. 本週執行清單（2026-W17）
- [ ] 完成 Query rewrite 第一版（含 rule + LLM）
  - 已完成：rule-based rewrite
  - 待完成：LLM rewrite
- [x] 加入 sparse 檢索並與 dense 融合排序（v1）
- [ ] 補齊 20 題評估集（定義/比較/流程/時序）
- [ ] 產出第一版評估報表（Recall@5、Citation Accuracy）

---

## 7. Definition of Done
- [ ] 核心查詢命中率達標（以基準集衡量）
- [ ] 回答可追溯且引用可驗證
- [ ] 資料不足時不臆測
- [ ] 延遲落在可接受範圍
- [ ] 主要功能具備測試與回歸機制
