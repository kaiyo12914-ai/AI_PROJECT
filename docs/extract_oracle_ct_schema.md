# `extract_oracle_ct_schema.py`

用途：從 Oracle 依照表名前綴抓出指定 TABLE 的 DDL、TABLE COMMENT、COLUMN COMMENT，並逐表寫入 PostgreSQL 的 `TACLE_SCHEMA`。

## 執行範例

只抓 `CT_` 開頭的表：

```powershell
.\venv\Scripts\python.exe .\extract_oracle_ct_schema.py --oracle-profile ERP_MPC
```

同時抓 `CT_` 與 `DT_`：

```powershell
.\venv\Scripts\python.exe .\extract_oracle_ct_schema.py --oracle-profile ERP_MPC --table-prefixes CT_,DT_
```

指定 Oracle owner，並輸出到自訂 PostgreSQL 表名：

```powershell
.\venv\Scripts\python.exe .\extract_oracle_ct_schema.py `
  --oracle-profile ERP_MPC `
  --oracle-owner ERP_MPC `
  --table-prefixes CT_,DT_ `
  --pg-table-name TACLE_SCHEMA
```

僅檢視，不寫入 PostgreSQL：

```powershell
.\venv\Scripts\python.exe .\extract_oracle_ct_schema.py --dry-run
```

## 參數

- `--oracle-profile`
  - Oracle 連線 profile
  - 預設：`ERP_MPC`
- `--oracle-owner`
  - 限定 Oracle owner/schema
  - 空值代表不限制
- `--table-prefix`
  - 主要表名前綴
  - 預設：`CT_`
- `--table-prefixes`
  - 額外表名前綴
  - 支援逗號、空白、分號分隔
  - 例：`CT_,DT_`
- `--pg-dsn`
  - PostgreSQL 連線字串
- `--pg-table-name`
  - 目標 PostgreSQL 表名
  - 預設：`TACLE_SCHEMA`
- `--limit`
  - 最多處理幾筆 Oracle TABLE
- `--dry-run`
  - 只顯示結果，不寫入 PostgreSQL

## PostgreSQL 連線環境變數

工具會依序讀取以下設定：

1. `POSTGRES_DSN`
2. `PG_DSN`
3. `DATABASE_URL`
4. `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD`

若有設定 `PGHOST` 組合方式，會自動組出：

```text
postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

## Oracle 連線

Oracle 連線不直接讀 `.env` 的 DB 參數，而是交給專案內的 `webapps.database.db_factory.db_connect("oracle", profile=...)`。

因此 Oracle 端主要由：

- `--oracle-profile`
- 專案內的 DB profile 設定

共同決定。

## 輸出內容

每一筆寫入 PostgreSQL `TACLE_SCHEMA` 的資料會包含：

- `table_schema`
- `table_name`
- `ddl_text`
- `comment_sql_text`
- `schema_text`
- `table_comment`
- `column_comments_json`
- `source_profile`
- `source_owner`
- `updated_at`

