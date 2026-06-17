# NL2SQL 子系統 DB 重建程序（離線內網）

## 目的

本文件用於重建 NL2SQL / Vanna 2.0 整合子系統所需的 PostgreSQL 資料表。

本子系統資料邊界如下：

- PostgreSQL：僅儲存 Vanna / NL2SQL metadata、schema、training examples、embeddings、ACL、審核與查詢紀錄。
- Oracle：只作為業務資料查詢來源，不在本程序中備份或還原。
- `ENV=EXT`：只產生 SQL，不連線執行 Oracle 查詢。
- `ENV=INT`：SQL Guard 通過後，才允許執行 Oracle 查詢並回傳查詢結果。

## 1. TABLE 重建方式

### 1.1 只建立資料表結構

於 `./` 專案根目錄執行：

```powershell
./\venv\Scripts\python.exe manage.py migrate vanna_integration
```

若已啟用專案虛擬環境，也可執行：

```powershell
python manage.py migrate vanna_integration
```

### 1.2 連同既有資料搬移

來源端匯出：

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes --no-owner --no-privileges -F c -t "nl2sql_training_example1" -f nl2sql_training_example1.dump
```

目標端還原：

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes nl2sql_tables.dump
```

若來源或目標主機、資料庫名稱、帳號不同，請依內網實際環境調整 `-h`、`-p`、`-U`、`-d`。

## 2. 前置條件

### 2.1 PostgreSQL 必須啟用 pgvector

NL2SQL schema / example embeddings 使用 pgvector，目標 PostgreSQL 必須具備 `vector` extension。

可由 DBA 或具權限帳號執行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Django migration 內含 `VectorExtension()`，但若目標資料庫帳號無建立 extension 權限，仍需先由 DBA 建立。

### 2.2 環境設定

- `./\.env` 需指向目標 PostgreSQL。
- Oracle / Sybase / 其他業務 DB 連線設定以 `./\.env_DB_factory` 為準。
- NL2SQL 不使用 `NL2SQL_DB_*` 作為業務 DB 連線來源。
- DB 存取必須走 `webapps/database/db_factory.py`。

確認 migration 狀態：

```powershell
./\venv\Scripts\python.exe manage.py showmigrations vanna_integration
```

## 3. NL2SQL 子系統資料表清單

以下資料表由 `webapps\vanna\migrations\0001_initial.py` 建立：

1. `nl2sql_data_source`：資料來源設定，包含 DB 類型、profile、schema 與用途。
2. `nl2sql_schema_object`：資料表 / view / schema metadata 與 DDL 摘要。
3. `nl2sql_schema_embedding`：schema metadata embedding，供 NL2SQL RAG 檢索使用。
4. `nl2sql_training_example`：Vanna 訓練範例，包含自然語言問題、SQL、狀態與審核資訊。
5. `nl2sql_example_embedding`：training example embedding，供相似範例檢索使用。
6. `nl2sql_vanna_training_sync`：Vanna training sync 紀錄。
7. `nl2sql_business_term`：業務詞彙、同義詞與資料欄位對應。
8. `nl2sql_user_data_source_acl`：使用者對資料來源的存取權限。
9. `nl2sql_table_policy`：資料表層級的允許 / 限制政策。
10. `nl2sql_column_policy`：欄位層級的敏感資料、遮罩與允許政策。
11. `nl2sql_query_log`：自然語言查詢、產生 SQL、Guard 結果與執行紀錄。
12. `nl2sql_review_queue`：SQL 或訓練資料審核佇列。
13. `nl2sql_eval_case`：NL2SQL 評測案例。

## 4. 重建後驗證

確認 Django 設定與 migration：

```powershell
./\venv\Scripts\python.exe manage.py check
./\venv\Scripts\python.exe manage.py showmigrations vanna_integration
```

確認資料表存在：

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'nl2sql_%'
ORDER BY table_name;
```

確認 embedding table 與 pgvector index 建立狀態：

```sql
SELECT indexname, tablename
FROM pg_indexes
WHERE tablename IN ('nl2sql_schema_embedding', 'nl2sql_example_embedding')
ORDER BY tablename, indexname;
```

## 5. Schema / Training Sync

重建資料表後，管理者可由 NL2SQL 頁面執行：

- `同步資料庫結構（Schema Sync）`
- `同步 Vanna 訓練（Vanna Sync）`
- `Vanna 訓練資料集維護`

管理者維護入口僅 `H121356578` 可視。

相關 API：

- `/nl2sql/api/schema/sync/`
- `/nl2sql/api/vanna/sync-training/`
- `/nl2sql/api/vanna/training-dataset/`

注意：

- `ENV=EXT` 不應連線執行 Oracle 查詢；若需同步 Oracle schema，應於 `ENV=INT` 內網環境執行。
- 從舊版 Vanna / Chroma 匯入資料後，需確認 `nl2sql_training_example` 與 `nl2sql_example_embedding` 是否同步完成。
- SQL Guard 必須維持只允許安全 `SELECT` 查詢。

## 6. 離線相依套件

若內網環境需補齊 Vanna 2.0 相關 Python 套件，可由 wheelhouse 安裝：

```powershell
./\venv\Scripts\python.exe -m pip install --no-index --find-links ../WHL -r ./\requirement_vanna.txt
```

安裝後建議重新執行：

```powershell
./\venv\Scripts\python.exe manage.py check
```
