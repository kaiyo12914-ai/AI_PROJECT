# projectnotes 子系統 DB 重建程序（離線內網）

本文目的：在內網離線電腦重建與目前 `projectnotes` 子系統一致的資料庫（含 TABLE 結構）。

## 1. 目前 DB 運用類型（依現行程式）

- Django `default`：`SQLite`（`webproj/settings.py` 的 `db.sqlite3`，主要是 Django 系統資料）。
- `projectnotes`：獨立使用 `PostgreSQL`（alias: `projectnotes_db`，由 `webapps/projectnotes/router.py` 路由）。
- 向量欄位：`pgvector`（`DocumentChunk.embedding = VectorField(dimensions=1536)`）。
- 結論：`projectnotes` 要正常運作，目標機器需要：
  - PostgreSQL（建議 16.x）。
  - DB 端 `vector` extension（`CREATE EXTENSION vector;`）。
  - Python 套件 `pgvector` + PostgreSQL driver（`psycopg2-binary`）。

## 2. 現存帳密與連線資訊（來自 repo 檔案）

以下為「目前檔案內存在」的設定，請在內網重建時依資安規範更換密碼。

- `.env`（`DATABASE_URL`）：
  - `postgres://projectnotes_user:mpcdbadm@192.168.0.137:5432/projectnotes`
  - 帳號：`projectnotes_user`
  - 密碼：`mpcdbadm`
  - DB：`projectnotes`
  - Host：`192.168.0.137`
  - Port：`5432`
- `setup_vector.py`（用於建立 extension 的超級帳號示例）：
  - `postgresql://postgres:Ntou6228@192.168.0.137:5432/projectnotes`
  - 帳號：`postgres`
  - 密碼：`Ntou6228`

注意：
- `projectnotes` 業務資料的 `created_by/user_id` 是字串型登入帳號（來自 IIS/Django 身分），不是 DB 登入密碼表。
- 若要完整複製「可登入使用者」，需另外同步 AD/IIS/Portal ACL，不在本文件範圍。

## 3. 離線下載清單（在可上網機器先抓好）

## 3.1 PostgreSQL 安裝檔

- 下載 PostgreSQL Windows x64 安裝程式（建議 16.x）。
- 若你已有公司內部套件倉，改由內部倉取得同版安裝包。

## 3.2 Python 離線套件（在專案 Python 3.12 環境）

在可上網機器執行（範例輸出到 `H:\AI\WHL`）：

```powershell
python -m pip download pgvector psycopg2-binary sqlalchemy -d H:\AI\WHL
```

如需更完整相依套件，可另外執行：

```powershell
python -m pip download -r requirements.txt -d H:\AI\WHL
```

將 `H:\AI\WHL` 整包複製到離線機。

## 4. 離線安裝與設定（目標內網機）

## 4.1 安裝 PostgreSQL

1. 安裝 PostgreSQL（例如 `C:\Program Files\PostgreSQL\16`）。
2. 記下 superuser（通常 `postgres`）密碼。
3. 確保服務啟動，`5432` 可本機連線。

## 4.2 安裝 Python 套件（離線）

```powershell
python -m pip install --no-index --find-links=H:\AI\WHL pgvector psycopg2-binary sqlalchemy
```

## 4.3 建立 DB 與角色（若全新環境）

以 `psql`（postgres 身分）執行：

```sql
CREATE ROLE projectnotes_user LOGIN PASSWORD '請改成新密碼';
CREATE DATABASE projectnotes OWNER projectnotes_user ENCODING 'UTF8';
\c projectnotes
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL PRIVILEGES ON DATABASE projectnotes TO projectnotes_user;
```

## 4.4 專案環境設定 `.env`

設定 `DATABASE_URL`（示例）：

```env
DATABASE_URL=postgres://projectnotes_user:請改成新密碼@127.0.0.1:5432/projectnotes
```





## 5. TABLE 重建方式（兩種）

## 5.1 只重建結構（空庫）

在專案根目錄執行：

```powershell
python manage.py migrate projectnotes --database projectnotes_db
```

此方式會依 migration 建立 table/index（含 `pn_chunk_vector_idx`）。

## 5.2 複製既有資料（建議）

在來源機器（現行 DB）先備份：

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes -F c -f projectnotes_full.dump
```

在目標離線機還原：

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes projectnotes_full.dump
```

## 用超級使用者連線（例如 postgres）到 projectnotes 資料庫
psql -h 127.0.0.1 -p 5432 -U postgres -d projectnotes 
密碼:NtouXXXX
## 用超級使用者連線（例如 postgres）還原資料庫
pg_restore --clean --if-exists --no-owner --no-privileges -h 127.0.0.1 -p 5432 -U postgres -d projectnotes projectnotes_full.dump

ALTER USER postgres WITH PASSWORD 'YourNewStrongPassword';




建議還原前先確認已執行 `CREATE EXTENSION vector;`。

## 6. 現行 projectnotes TABLE 清單

依 `webapps/projectnotes/migrations/0001_initial.py`：

1. `projectnotes_project`
2. `projectnotes_membership`
3. `projectnotes_source`
4. `projectnotes_document`
5. `projectnotes_document_version`
6. `projectnotes_document_chunk`
7. `projectnotes_citation`
8. `projectnotes_conversation`
9. `projectnotes_message`
10. `projectnotes_message_citation`
11. `projectnotes_comment`
12. `projectnotes_activity_log`

## 7. 重建後驗證

## 7.1 驗證 Django 連線

```powershell
python manage.py shell -c "from django.db import connections; c=connections['projectnotes_db']; print(c.vendor); print(c.settings_dict['NAME'])"
```

預期看到 `postgresql` 與 `projectnotes`。

## 7.2 驗證 extension / table

```powershell
psql -h 127.0.0.1 -U projectnotes_user -d projectnotes -c "SELECT extname FROM pg_extension WHERE extname='vector';"
psql -h 127.0.0.1 -U projectnotes_user -d projectnotes -c "\dt projectnotes_*"
```

## 7.3 驗證筆數（可與來源機比對）

```powershell
psql -h 127.0.0.1 -U projectnotes_user -d projectnotes -c "SELECT 'projectnotes_project' AS t, count(*) FROM projectnotes_project
UNION ALL SELECT 'projectnotes_source', count(*) FROM projectnotes_source
UNION ALL SELECT 'projectnotes_document_chunk', count(*) FROM projectnotes_document_chunk
UNION ALL SELECT 'projectnotes_conversation', count(*) FROM projectnotes_conversation;"
```
psql "host=127.0.0.1 dbname=projectnotes user=projectnotes_user password=你的密碼" -c "SELECT 'projectnotes_project' AS t, count(*) FROM projectnotes_project;"

## 8. 常見問題

- 問題：`relation ... does not exist`  
  原因：未對 `projectnotes_db` 跑 migration。  
  處理：執行 `python manage.py migrate projectnotes --database projectnotes_db`。

- 問題：`type "vector" does not exist`  
  原因：未建立 pgvector extension。  
  處理：以 superuser 執行 `CREATE EXTENSION vector;`。

- 問題：Django 啟動後 projectnotes 無法連線  
  原因：`.env` 的 `DATABASE_URL` 錯誤或密碼不符。  
  處理：修正 `DATABASE_URL`，再重啟服務。

如果你是拿它們來做 **RAG / 向量檢索 / AI 應用**，可以先這樣抓重點：

**PostgreSQL** 是通用型關聯式資料庫。
**Chroma DB** 是偏向 AI 檢索場景的向量資料庫／檢索基礎設施。

PostgreSQL 本身以表格、SQL、交易一致性、索引、擴充能力見長；官方文件把它定位成完整的關聯式資料庫，具備 SQL、索引、並行查詢、併發控制、延伸功能等完整能力。([PostgreSQL][1])
Chroma 則主打把 embeddings、documents、metadata 放進 collection，支援 dense/sparse vector search、metadata filtering，以及文字、圖片等檢索流程。([docs.trychroma.com][2])

## 一句話比較

* **PostgreSQL**：適合「**主系統資料庫** + 需要嚴謹交易 / SQL / 報表 / 權限 / 多種業務資料一起管」
* **Chroma DB**：適合「**AI 檢索層** + 快速做 RAG / 語意搜尋 / embedding 管理」

---

## 核心差異

### 1. 資料模型

PostgreSQL 以 **table / row / column / SQL schema** 為核心，適合結構化資料、交易資料、主檔、歷史紀錄。([PostgreSQL][3])
Chroma 以 **collection** 為核心，裡面放 document、embedding、metadata、id，天然更貼近 LLM/RAG 的資料型態。([docs.trychroma.com][4])

### 2. 查詢方式

PostgreSQL 強在 **SQL 查詢**、JOIN、聚合、排序、交易邏輯。([PostgreSQL][1])
Chroma 強在 **向量相似度查詢**、文字查詢、metadata filter，查詢接口更偏 AI 檢索。([docs.trychroma.com][2])

### 3. 交易與一致性

PostgreSQL 是成熟的 ACID 關聯式資料庫，適合訂單、流程、主資料、稽核紀錄等需要強一致性的場景。官方文件也明確涵蓋 concurrency control、server administration 等完整資料庫能力。([PostgreSQL][1])
Chroma 的重點不是傳統 OLTP 交易處理，而是 AI 檢索效率與使用便利性；如果你要的是企業核心交易庫，通常不會先選 Chroma。這是根據其官方定位可推得出的使用邏輯。([docs.trychroma.com][2])

### 4. 擴充性

PostgreSQL 擴充能力很強，可透過 extension 擴展功能；這也是為什麼很多人會搭配 `pgvector` 讓 PostgreSQL 同時具備向量能力。官方文件明確說明 extensions 可像內建功能一樣運作。([PostgreSQL][5])
Chroma 則是直接把向量檢索當核心能力，不用你先把它改造成向量庫。([docs.trychroma.com][2])

---

## PostgreSQL 優點

### 優點

1. **功能完整**
   SQL、交易、索引、權限、備份、複寫、報表整合都成熟。([PostgreSQL][1])

2. **適合當主資料庫**
   業務資料、使用者、權限、訂單、審計、流程資料可放同一套資料平台。

3. **生態成熟**
   ORM、BI、ETL、備援、監控工具都很多。

4. **可延伸到向量搜尋**
   若加上 `pgvector`，可以把傳統資料與向量資料放一起管理，架構比較集中。這點是實務上很常見的選法，而 PostgreSQL extension 機制本身也支援這類擴展。([PostgreSQL][5])

### 缺點

1. **原生定位不是專用向量資料庫**
   若你的核心需求是大規模 embedding 檢索，PostgreSQL 通常要靠額外 extension 與 tuning。

2. **AI 檢索開發體驗沒那麼直覺**
   collection、embedding pipeline、檢索 API 這些通常要自己拼。

3. **架構容易變重**
   若只是想快速做一個 RAG demo，用 PostgreSQL 可能顯得較重。

---

## Chroma DB 優點

### 優點

1. **對 AI / RAG 很直覺**
   collection、documents、embeddings、metadata 這些概念直接可用。([docs.trychroma.com][4])

2. **檢索能力聚焦**
   官方強調 dense、sparse、full-text、regex、metadata filtering 等檢索能力。([docs.trychroma.com][2])

3. **開發上手快**
   用 Python client 建 collection、add documents、query，很適合快速驗證 RAG。([docs.trychroma.com][4])

4. **更貼近 LLM 應用**
   特別適合文件檢索、知識庫問答、語意搜尋。

### 缺點

1. **不適合取代主交易資料庫**
   它不是拿來當 ERP / MES / CRM 主系統資料庫的首選。

2. **SQL 與複雜商業查詢能力不如 PostgreSQL**
   若你常做多表 JOIN、複雜報表、交易流程，PostgreSQL 明顯更合適。([PostgreSQL][1])

3. **企業治理能力通常較弱**
   在權限模型、既有資料治理、傳統 DBA 維運習慣上，通常不如 PostgreSQL 成熟。

4. **資料分散風險**
   若主資料在 PostgreSQL、向量在 Chroma，會多一層同步與一致性管理成本。

---

## 怎麼選

### 選 PostgreSQL 較適合

* 你要的是 **正式業務系統**
* 有大量 **交易資料 / 關聯資料**
* 需要 **SQL 報表、JOIN、權限、備援**
* 想把 AI 能力加到既有資料平台，而不是另外養一套資料庫

### 選 Chroma 較適合

* 你主要做 **RAG、知識庫問答、語意搜尋**
* 想 **快速做原型**
* 資料以 **文件 + embedding + metadata** 為主
* 不想先處理太多傳統資料庫設計

---

## 實務建議

很多團隊最後不是二選一，而是：

* **PostgreSQL**：放主資料、使用者、權限、流程、業務紀錄
* **Chroma**：放文件向量索引、知識庫檢索

或者另一條路：

* **PostgreSQL + pgvector**：一套系統同時管交易資料與向量資料

如果你的資料量中等、架構想簡化、團隊已熟 PostgreSQL，**PostgreSQL + pgvector** 通常很有吸引力。
如果你要的是 **最快速把 RAG 跑起來**，**Chroma** 往往更省事。這是根據兩者官方定位與能力範圍做出的工程判斷。([docs.trychroma.com][2])

## 給你的簡表

| 面向      | PostgreSQL       | Chroma DB           |
| ------- | ---------------- | ------------------- |
| 核心定位    | 關聯式資料庫           | AI 檢索 / 向量資料庫       |
| 強項      | SQL、交易、關聯查詢、治理   | embedding、相似度搜尋、RAG |
| 適合資料    | 結構化業務資料          | 文件、向量、metadata      |
| 開發速度    | 一般               | 做 AI 檢索通常較快         |
| 當主系統 DB | 很適合              | 不建議                 |
| 做 RAG   | 可做，但常需 extension | 很適合                 |
| 架構複雜度   | 單庫可整合很多需求        | 常作為檢索層              |

如果你是要用在 **Vanna AI / OpenWebUI / 知識庫問答 / 文件檢索**，我可以直接再幫你做一版「**PostgreSQL + pgvector vs Chroma 在你目前環境的選型建議**」。

[1]: https://www.postgresql.org/docs/current/index.html?utm_source=chatgpt.com "PostgreSQL 18.3 Documentation"
[2]: https://docs.trychroma.com/docs/overview/introduction?utm_source=chatgpt.com "Introduction - Chroma Docs"
[3]: https://www.postgresql.org/docs/current/tutorial-concepts.html?utm_source=chatgpt.com "PostgreSQL: Documentation: 18: 2.2. Concepts"
[4]: https://docs.trychroma.com/docs/overview/getting-started?utm_source=chatgpt.com "Getting Started - Chroma Docs"
[5]: https://www.postgresql.org/docs/current/external-extensions.html?utm_source=chatgpt.com "PostgreSQL: Documentation: 18: H.4. Extensions"

---

## 9. 匯出單一 Table 並匯入內網

本節適用於：

- 只想搬一張資料表，不想整庫 `pg_dump`
- 內網主機不能直接連外網，只能用檔案帶入
- 要把某張 table 的資料複製到內網 PostgreSQL

### 9.1 先確認來源與目標

匯出前先確認 4 件事：

1. 來源 DB 主機、帳號、資料庫名稱
2. 要匯出的 table 名稱
3. 內網目標 DB 是否已先建立同名 table 結構
4. 目標 table 是否要先清空再匯入

先查 table 是否存在：

```powershell
psql -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes -c "\dt projectnotes_*"
```

如果只想查單一 table：

```powershell
psql -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes -c "\d englishchat_question_bank"
```

### 9.2 匯出單一 Table：只匯資料

如果內網端已經有相同 schema，最穩定的是只匯資料，不帶建表語句。

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes ^
  -t englishchat_question_bank ^
  --data-only ^
  --inserts ^
  -f englishchat_question_bank_data.sql
```

說明：

- `-t projectnotes_document_chunk`：只匯出這一張 table
- `--data-only`：只匯資料，不匯 `CREATE TABLE`
- `--inserts`：輸出成 `INSERT`，可直接用 `psql` 匯入
- 輸出檔案是純 SQL，適合人工檢查與內網帶檔

### 9.3 匯出單一 Table：含 schema + data

如果內網端還沒有這張 table，可匯出 schema 與資料。

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes ^
  -t englishchat_question_bank ^
  -f englishchat_question_bank_full.sql
```

這種方式會包含：

- `CREATE TABLE`
- 預設值
- 可能的 `COPY` 或 SQL 資料內容

但注意：

- 如果目標端已有同名 table，直接匯入可能報 `relation already exists`
- 若 table 有依賴 index / sequence / constraint，要先確認目標端相容

### 9.4 建議格式：custom dump

若希望匯入時更彈性，建議用 PostgreSQL custom format：

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes ^
  -t englishchat_question_bank ^
  -F c ^
  -f englishchat_question_bank.dump
```

優點：

- 檔案較小
- 可用 `pg_restore` 控制匯入
- 比純 SQL 更適合正式搬移

### 9.5 帶入內網的方式

外網匯出完成後，把檔案複製到內網，例如：

- `projectnotes_document_chunk_data.sql`
- 或 `englishchat_question_bank_full.sql`
- 或 `englishchat_question_bank.dump`

可放到內網主機：

```text
H:\AI\AI_TOOLS\import\
```

### 9.6 內網匯入：匯入純 SQL 資料檔

如果匯出的是 `--data-only --inserts` 的 `.sql` 檔：

```powershell
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -f englishchat_question_bank_data.sql
```

如果目標 table 需先清空：

```powershell
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -c "TRUNCATE TABLE englishchat_question_bank RESTART IDENTITY CASCADE;"
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -f englishchat_question_bank_data.sql
```

說明：

- `RESTART IDENTITY`：重置 sequence
- `CASCADE`：若有 FK 依賴會一併處理，使用前要確認影響範圍

### 9.7 內網匯入：匯入 custom dump

如果匯出的是 `.dump`：

```powershell
pg_restore -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes englishchat_question_bank.dump
```

如果要先刪除既有物件再匯入：

```powershell
pg_restore --clean --if-exists -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes englishchat_question_bank.dump
```

如果只想還原資料，不碰 schema：

```powershell
pg_restore --data-only -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes englishchat_question_bank.dump
```

### 9.8 內網匯入前，先建 schema 的安全作法

如果目標端還沒有該 table，建議先在內網跑 migration 建好結構，再匯資料，不要直接依賴外網 dump 建表。

例如 `projectnotes`：

```powershell
python manage.py migrate projectnotes --database projectnotes_db
```

這樣做的好處：

- 內網 schema 由 Django migration 控制
- 避免外網與內網版本不一致
- 比較不容易出現欄位、constraint、sequence 差異

### 9.9 匯入後檢查

先看筆數：

```powershell
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -c "SELECT count(*) FROM englishchat_question_bank;"
```

再抽查前幾筆：

```powershell
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -c "SELECT question_id, topic_key, mode, level FROM englishchat_question_bank ORDER BY id DESC LIMIT 10;"
```

如果是 Django 專案，也可用 shell 檢查：

```powershell
python manage.py shell -c "from webapps.database.db_factory import db_query_one; print(db_query_one('postgresql', 'SELECT count(*) FROM englishchat_question_bank', profile='ENGLISHCHAT')[0])"
```

### 9.10 最常用範例

#### 範例 A：只搬 `englishchat_question_bank` 資料到內網

外網：

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes ^
  -t englishchat_question_bank ^
  --data-only --inserts ^
  -f englishchat_question_bank_data.sql
```

內網：

```powershell
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -c "TRUNCATE TABLE englishchat_question_bank RESTART IDENTITY CASCADE;"
psql -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes -f englishchat_question_bank_data.sql
```

#### 範例 B：搬單一 table 的完整物件

外網：

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes ^
  -t englishchat_question_bank ^
  -F c ^
  -f englishchat_question_bank.dump
```

內網：

```powershell
pg_restore --clean --if-exists -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes englishchat_question_bank.dump
```

### 9.11 注意事項

- 若 table 名稱有大寫或特殊字元，`-t` 參數要用正確名稱，必要時加雙引號。
- 若 table 有 FK 依賴其他 table，單搬一張 table 可能會遇到 constraint 問題。
- 若只是搬資料，優先用：
  `pg_dump -t <table> --data-only --inserts`
- 若只是內網重建同版系統，優先先跑 migration，再匯資料。
- 若資料很大，`--inserts` 會比較慢，但可讀性高；大量資料可改用 `COPY` 或 custom dump。
