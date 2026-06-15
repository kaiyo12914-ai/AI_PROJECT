# `nl2sql_sync_oracle_schema.py`

用途：從 Oracle 自動擷取 `CT_*`、`DT_*` 這類 TABLE / VIEW / MVIEW 的 DDL 與 COMMENT，建立 NL2SQL 所需的 schema 資料與向量。

寫入目標：

- `nl2sql_schema_object`
- `nl2sql_schema_embedding`

## 執行範例

抓 `CT_`、`DT_` 與 `FT_`：

```powershell
.\venv\Scripts\python.exe .\manage.py nl2sql_sync_oracle_schema --oracle-profile ERP_MPC --table-prefixes CT_,DT_,FT_
```

抓 `VIEW` / `MVIEW`：

```powershell
.\venv\Scripts\python.exe .\manage.py nl2sql_sync_oracle_schema --oracle-profile ERP_MPC --object-types view,mview
```

標準 Django 指令：

```powershell
.\venv\Scripts\python.exe .\manage.py nl2sql_sync_oracle_schema --oracle-profile ERP_MPC
```

只抓 `CT_`：

```powershell
.\venv\Scripts\python.exe .\nl2sql_sync_oracle_schema.py --oracle-profile ERP_MPC --table-prefixes CT_
```

指定 Oracle owner：

```powershell
.\venv\Scripts\python.exe .\nl2sql_sync_oracle_schema.py --oracle-profile ERP_MPC --oracle-owner ERP_MPC
```

先清空後重建：

```powershell
.\venv\Scripts\python.exe .\nl2sql_sync_oracle_schema.py --clear
```

只建 schema object，不建 embeddings：

```powershell
.\venv\Scripts\python.exe .\nl2sql_sync_oracle_schema.py --skip-embeddings
```

```powershell
.\venv\Scripts\python.exe .\manage.py nl2sql_sync_oracle_schema --skip-embeddings
```

## 參數

- `--oracle-profile`
  - Oracle 連線 profile
  - 預設：`ERP_MPC`
- `--oracle-owner`
  - 限定 Oracle owner/schema
- `--table-prefixes`
  - 物件名稱前綴，支援逗號、空白、分號分隔
  - 預設：`CT_,DT_`
- `--object-types`
  - Oracle 物件類型
  - 支援：`table`、`view`、`mview`
  - 預設：`table,view,mview`
- `--data-source-code`
  - NL2SQL `DataSource.code`
  - 預設：`nl2sql_oracle_schema`
- `--data-source-name`
  - NL2SQL `DataSource.name`
  - 預設：`Oracle NL2SQL Schema`
- `--limit`
  - 最多處理幾筆 TABLE
- `--batch-size`
  - embedding 批次大小
- `--skip-embeddings`
  - 只寫 `nl2sql_schema_object`
- `--clear`
  - 先刪除該 data source 的舊 schema 與 embeddings
- `--dry-run`
  - 只列印擷取結果，不寫入資料庫

## 寫入內容

每個 Oracle 物件會建立或更新一筆 `nl2sql_schema_object`，內容包含：

- `schema_name`
- `object_name`
- `description`
- `columns_json`
- `ddl_text`
- `row_estimate`

並建立三種 `nl2sql_schema_embedding`：

- `ddl`
- `columns`
- `documentation`

## 注意事項

- 這支工具使用專案內的 Django ORM 寫入 NL2SQL PostgreSQL tables，不需要另外指定 `PG_DSN`。
- Oracle 連線仍走專案內 `webapps.database.db_factory.db_connect("oracle", profile=...)`。
