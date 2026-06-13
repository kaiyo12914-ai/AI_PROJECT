# meetingreply 子系統 DB 重建程序（內網版）

本文件提供 `meetingreply` 相關資料表的「匯出（含 schema + data）」、「匯入」與 `embedding` 重建步驟。

## 1. 目標資料表

1. `meeting_records`
2. `meetingreply_record_embedding`

說明：
- `meeting_records` 為會議指裁示來源資料表。
- `meetingreply_record_embedding` 為 `meetingreply` 子系統本地 pgvector 索引表。

## 2. 匯出方式（含 schema + data）

### 2.1 匯出單一 dump（建議）

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes --no-owner --no-privileges -t meeting_records -t meetingreply_record_embedding -F c -f meetingreply_tables_full.dump
```

說明：
- `-F c` 為 custom format，含 schema + data。
- 可用 `pg_restore` 做還原。
- 若只想搬來源資料，可只匯出 `meeting_records`。
- 若目標環境要重新計算向量，也可不匯出 `meetingreply_record_embedding`，匯入後再執行 embedding 重建。

## 3. 匯入方式（可重複匯入）

### 3.1 匯入單一 dump（建議）

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes .\meetingreply_tables_full.dump
```

說明：
- `--clean --if-exists`：先刪除舊物件再重建，避免 `relation already exists`。
- 匯入前請確認目標 DB 連線帳號有建表、建索引、寫入權限。

## 4. 只建立 meetingreply 本地表結構

若目標端已有 `meeting_records`，但沒有 `meetingreply_record_embedding`，可只建立 `meetingreply` 子系統自己的本地表：

```powershell
./\venv\Scripts\python.exe manage.py migrate meetingreply
```

若已啟用專案虛擬環境，也可執行：

```powershell
python manage.py migrate meetingreply
```

## 5. embedding 重建程序

### 5.1 全量重建

`meetingreply_record_embedding` 可由既有 `meeting_records` 重新計算產生：

```powershell
./\venv\Scripts\python.exe manage.py rebuild_meetingreply_embeddings --delete-missing
```

### 5.2 小批次驗證

若要先驗證最近 N 筆，可執行：

```powershell
./\venv\Scripts\python.exe manage.py rebuild_meetingreply_embeddings --limit 100
```

說明：
- 全系統 embedding model 依專案規範統一使用 `OLLAMA / snowflake-arctic-embed2`。
- 本機目前 `meetingreply` 已實作 direct HTTP fallback，會優先用可用的遠端 Ollama URL 做 embedding 回填。

## 6. 前置條件

### 6.1 PostgreSQL 必須啟用 pgvector

`meetingreply_record_embedding.embedding` 使用 pgvector，目標 PostgreSQL 必須具備 `vector` extension。

可由 DBA 或具權限帳號執行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 6.2 環境設定

- `./\.env` 需指向目標 PostgreSQL。
- `MEETINGREPLY_ENABLE_EMBEDDING=1`
- `GLOBAL_EMBEDDING_PROVIDER=OLLAMA`
- `GLOBAL_EMBEDDING_MODEL=snowflake-arctic-embed2`
- `GLOBAL_EMBEDDING_DIMENSION=1024`

## 7. 重建後驗證

確認 Django 設定與 migration：

```powershell
./\venv\Scripts\python.exe manage.py check
./\venv\Scripts\python.exe manage.py showmigrations meetingreply
```

確認資料表存在：

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('meeting_records', 'meetingreply_record_embedding')
ORDER BY table_name;
```

確認 pgvector index 建立狀態：

```sql
SELECT indexname, tablename
FROM pg_indexes
WHERE tablename = 'meetingreply_record_embedding'
ORDER BY indexname;
```

確認 embedding 是否已建立：

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS embedded_rows,
    MIN(vector_dims(embedding)) FILTER (WHERE embedding IS NOT NULL) AS min_dim,
    MAX(vector_dims(embedding)) FILTER (WHERE embedding IS NOT NULL) AS max_dim
FROM meetingreply_record_embedding;
```

## 8. 建議重建順序

1. 先用 `pg_restore` 還原 `meeting_records` 與需要保留的 `meetingreply_record_embedding`。
2. 若只還原了 `meeting_records`，執行 `manage.py migrate meetingreply` 建立本地表。
3. 執行 `manage.py rebuild_meetingreply_embeddings --delete-missing` 重建向量資料。
4. 以 `meetingreply/api/rag_only/` 驗證是否能取得 `sources`。
5. 以 `meetingreply/api/build_reply/` 驗證是否能正常產出擬答。

注意：
- 若 embedding 查詢失敗，系統仍會 fallback 到 keyword search，因此功能看似可用，不代表向量索引已建好。
- 若修改全系統 embedding model 或 embedding dimension，必須重新執行 `rebuild_meetingreply_embeddings`。
- `meetingreply_record_embedding` 為衍生表；權威資料來源仍是 `meeting_records`。
