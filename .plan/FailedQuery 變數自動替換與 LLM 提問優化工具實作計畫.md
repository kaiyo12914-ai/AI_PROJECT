FailedQuery 變數自動替換與 LLM 提問優化工具實作計畫
此計畫旨在開發一個 Django Management Command，能自動解析 nl2sql_failed_query_record 表中待處理（status = 'pending'）記錄之 SQL 語法中的變數佔位符（如 :as_deptno），藉由比對 PostgreSQL 的 data_dictionary 資料字典取得其欄位型態，並透過 db_factory 從實體資料庫中查詢出一個非空的真實範例值，用以取代變數。同時，呼叫 LLM 重新改寫其自然語言提問（question），將抽象描述替換為具體值，最終實現一鍵轉移或更新。

User Review Required
IMPORTANT

變數提取與欄位對應規則：
正則表達式將尋找 :variable_name 或 :AS_xxx 等冒號開頭的變數。
透過語法上下文匹配該變數所對應的欄位名（如 deptno like :as_deptno -> 欄位名 deptno）。
若無法通過上下文取得，預設使用變數去字元後的名稱作為猜測值（如 :as_deptno -> deptno）。
實體資料庫查詢與型態比對：
利用 data_dictionary 取得欄位所屬的 table_name 以及 data_type。
如果 data_type 屬於字串類型，在取代時會自動加上單引號（例如 '01'），數字型態則直接放數值（例如 101）。
使用 db_factory 的 db_query_one（基於該 DataSource 的 db_profile 與 db_type）查詢該實體表，取得一個隨機或第一筆真實非空值。若查詢失敗或查無資料，該筆 Failed Query 將跳過處理。
LLM 提問優化：
使用既有的 get_chat_model() 模型，發送 Prompt 請 LLM 把原始問題中抽象的變數描述（如「指定單位」）修剪為包含實際值的具體描述。
自動批准與轉移選項 (--auto-approve)：
若執行指令時帶有 --auto-approve，且取代後的 SQL 能成功通過 validate_sql (SQL Guard) 的安全性審查，工具會直接將其匯入正式的 TrainingExample (SQL approved examples) 與計算其向量，並將原 Failed 記錄從庫中清除。
Proposed Changes
[Vanna Management Commands Component]
[NEW] 
autofix_failed_queries.py
新增 Django Command autofix_failed_queries：
支援參數：
--dry-run：預覽變數替換結果與 LLM 修正提問，不寫入資料庫。
--auto-approve：若替換成功且通過 SQL Guard，自動匯入正式訓練集並刪除原 Failed 記錄。
--limit：限制處理的筆數，避免批次 LLM 消耗過大。
核心邏輯：
讀取 FailedQueryRecord 中狀態為 pending 的項目。
使用正則表達式尋找 failed_sql 中的所有 :var 變數。
對於每個變數：
偵測或猜測對應的欄位名。
查詢 PostgreSQL 的 data_dictionary 表（利用 Django connection.cursor() 查詢），取得 table_name 與 data_type。
透過 db_factory.db_query_one 從對應的實體庫（如 Oracle T202DB 或是 PostgreSQL mpcdb）中，取得該欄位的第一筆非空值。
依型態（字串/數字）組裝值並進行 SQL 內變數替換，生成 fixed_sql。
呼叫 get_chat_model() 將「原始提問、原始 SQL、變數對應關係、修改後 SQL」傳遞給 LLM，生成優化後的 fixed_question。
更新與轉移：
若為 --auto-approve：驗證 fixed_sql 能否通過 SQL Guard。通過則呼叫 classify_training_sql 類似邏輯（寫入 TrainingExample、計算 embedding、刪除 Failed 記錄）；未通過則保留在 Failed 表中並更新 failed_sql 與 question，狀態設為 pending。
若無 --auto-approve：僅在 FailedQueryRecord 中將 failed_sql 與 question 更新為替換後的內容，以便管理員後續於網頁端手動審查。
Verification Plan
Automated Tests
新建 tests/unit/test_autofix_failed_queries.py 單元測試檔：
測試變數與欄位提取的正則表達式解析。
測試 data_dictionary 型態匹配與單引號包裹邏輯。
Mock db_factory.db_query_one 實體查詢回傳與 LLM 回傳，驗證整體命令 handle 的執行流程。
測試 --dry-run 與 --auto-approve 的分支邏輯。
Manual Verification
執行 python manage.py autofix_failed_queries --dry-run --limit 3：
檢查 console 輸出的變數替換結果（包含 SQL 與 LLM 改寫問題的預覽）。
執行 python manage.py autofix_failed_queries --limit 1：
檢查實體資料庫 nl2sql_failed_query_record 表，確認該筆記錄的 failed_sql 與 question 是否已被就地修正，且狀態依然為 pending。
執行 python manage.py autofix_failed_queries --auto-approve --limit 1：
驗證轉換行為，確認該記錄已從 Failed 表中清除，且在 Vanna UI 的 SQL approved example