# FailedQuery 自動清洗與變數替換工具開發 Roadmap

更新日期：2026-06-17  
專案範圍：`./`

---

## 1. 需求分析

### 1.1 背景問題
目前在 Vanna 的訓練流程中，失敗語法精進記錄表（`nl2sql_failed_query_record`）裡累積了許多失敗的 SQL 查詢記錄。這些 SQL 語句中常包含抽象變數佔位符（例如 `:as_deptno`、`:AS001` 等），導致其無法直接執行，自然提問（Question）中也常有「指定服務單位」、「某員工」等抽象描述。
手動去查詢實體資料表以尋找可用實體值，並使用 LLM 修正問題的工作量極大，且容易出錯。

### 1.2 目標使用者
- Vanna 系統管理員 / DBA。

### 1.3 核心需求
- **自動提取變數**：從 `failed_sql` 中自動偵測 `:variable` 風格的變數。
- **欄位與型態分析**：解析變數關聯的欄位，並查詢 PostgreSQL 的 `data_dictionary` 表以確定其 `data_type`。
- **取得實體資料**：使用 `db_factory` 在實體資料表（Oracle / PostgreSQL）中，針對對應欄位取得一個真實非空的範例值（如將 `:as_deptno` 取代為 `'01'`），並依資料型態正確包裹單引號。
- **LLM 同步修正提問**：利用 LLM 重新改寫自然提問（`question`），將抽象描述轉化為包含該實體值的具體問句。
- **一鍵自動轉入訓練集**：提供 `--auto-approve` 參數，在檢測 SQL 通過 SQL Guard 後，自動將其以 approved 狀態寫入正式的 Vanna 訓練範例表中。

---

## 2. 系統開發規劃

### Phase 1：基礎架構與變數提取
- 實作 Django Command：`autofix_failed_queries` 的基本骨架與參數（如 `--dry-run`、`--auto-approve`）。
- 實作正則表達式，提取 `failed_sql` 中的變數佔位符與鄰近欄位。

### Phase 2：資料字典與實體資料查詢
- 串接 `data_dictionary` 表取得欄位型態。
- 整合 `db_factory` 動態建立實體資料庫查詢以獲取真實範例資料，並依型態進行 SQL 字串替換。

### Phase 3：LLM 問句優化與自動轉移
- 整合 `get_chat_model()` 進行 Question 欄位優化。
- 實作自動轉移 TrainingExample 與計算 Embedding 的邏輯，並通過 SQL Guard 驗證。

---

## 3. 完成性進度註記

- **總完成度**：`0%`
- **階段進度**：
  - Phase 1：`[ ] 待開發`
  - Phase 2：`[ ] 待開發`
  - Phase 3：`[ ] 待開發`
- **待辦與阻塞**：無

---

## 4. 驗收標準 (Definition of DoD)

1. **功能完整性**：
   - 能夠成功識別並取代 `failed_sql` 中的 `:as_deptno` 等變數。
   - 能夠利用 LLM 把提問修改為具體帶有取代值的句子。
   - 在執行 `--auto-approve` 時，成功轉移資料且在 Failed 表中刪除。
2. **安全防呆**：
   - 取代後的 SQL 必須能通過 `validate_sql` (SQL Guard) 的 SELECT/WITH 嚴格防禦審查。
3. **測試覆蓋率**：
   - 補齊 unit test，驗證正則匹配、型態單引號處理、以及轉移邏輯。
4. **規範相容性**：
   - 代碼一律使用 UTF-8 無 BOM。
   - 所有資料庫存取皆透過 `db_factory`，不建立獨立連線。
