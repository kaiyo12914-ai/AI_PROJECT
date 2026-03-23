# 公文處理相關 Skills（正式版 v2）

---

## 一、核心原則

* Skills 僅代表「**能力白名單**」，不代表一定會執行
* Agent **不得自行發明技能**
* 未列入本清單者，一律視為 **禁止**
* **所有操作必須遵守 `.codex/rules.md` 強制規範**

---

## 二、多廠區 DB 路由架構（必讀）

DOC 子系統支援多廠區，不同廠對應不同 DB 類型與 Schema：

| 廠區代碼 | DB 類型  | Owner/Schema | 權限       | 備註           |
|----------|----------|-------------|------------|----------------|
| MPC      | Sybase   | dbo         | **唯讀**   | 預設廠區       |
| 202      | Sybase   | dbo         | **唯讀**   |                |
| 205      | Oracle   | MNDQ        | **唯讀**   |                |
| 209      | Oracle   | MNDV        | **唯讀**   |                |
| 401      | Oracle   | MNDI        | **唯讀**   |                |

> ⚠️ **所有廠區 DB 皆為唯讀權限（SELECT ONLY）。**
> 不具備 INSERT / UPDATE / DELETE 權限，任何寫入操作會直接被 DB 拒絕。

### 路由機制
- **使用者→廠區**：透過 Oracle `CT_EMPLOY.FACTORY_PLANT` 欄位，由 `oracle_emp.py` 解析
- **廠區→DB**：由 `doc_db_router.py` 的 `resolve_doc_db_target()` 決定
- **docService** 初始化時自動取得 `plant` → `db_type` + `owner` + `db_profile`

### ⚠️ 各廠 DB 差異注意事項

| 差異項目         | Sybase (MPC/202)                        | Oracle (205/209/401)                |
|------------------|-----------------------------------------|-------------------------------------|
| 中文欄位         | `CONVERT(VARBINARY(4000), col)`         | `TO_CHAR(col)`                      |
| 分頁限制         | `SELECT TOP N`                          | `WHERE ROWNUM <= N`                 |
| 參數風格         | 位置型 `?`                              | 具名型 `:param_name`               |
| 字元集           | cp950/Big5 (需 best-effort decode)      | UTF-8 (直接讀取)                    |
| BLOB 長度        | `DATALENGTH(col)`                       | `DBMS_LOB.GETLENGTH(col)`          |
| Owner 前綴       | `dbo.TableName` 或由連線 DB 決定        | `MNDQ.TableName` 等                |
| NULL 合併        | `COALESCE(...)`                         | `NVL(...) / COALESCE(...)`          |

**鐵則**：Agent 不得自行撰寫 SQL，所有查詢必須透過 `docService` 方法，由 service 層處理 Sybase/Oracle 雙軌 SQL。

---

## 三、核心資料表

| 資料表              | 別名 | 說明                     |
|---------------------|------|--------------------------|
| `DCS3_TRST_MST`     | TM   | 公文主檔（收發文號、日期、承辦人）|
| `DCS3_TRST_DAT`     | TD   | 公文資料（格式、主旨、路徑）    |
| `DCS0_DOC_FILE`     | DF   | 文件檔案（DF_DATA BLOB）       |
| `DCS1_EMAL_TMP`     | EM   | 來文暫存（電子郵件匣）         |
| `DCS1_IN_MAST`      | IM   | 來文主檔                       |
| `DCS1_EMAL_FILE`    | EF   | 來文附件（EF_DATA BLOB）       |
| `CT_EMPLOY`         | —    | 員工資料（Oracle，含 FACTORY_PLANT）|

### 關鍵欄位對照

| 欄位         | 說明                   | 存取限制                    |
|--------------|------------------------|-----------------------------|
| `TM_PSID`    | 承辦人 ID              | 必須 = login_user           |
| `IM_PSID`    | 來文承辦人 ID          | 必須 = login_user           |
| `EM_PSID`    | 電子來文承辦人 ID      | 必須 = login_user           |
| `TM_GRSNO`   | 收發文號               | 查詢用主鍵                  |
| `EM_GRSNO`   | 來文收發文號           | 查詢用主鍵                  |
| `TD_SUBJ`    | 公文主旨               | Sybase 需 VARBINARY 解碼    |
| `EF_DATA`    | 附件二進位資料         | 不得直接修改                |
| `DF_DATA`    | 文件二進位資料         | 不得直接修改                |

---

## 四、使用者身份與權限鏈

```
Request → middleware (login_user/login_user_name)
    → utils_login.get_login_user_idno()
    → oracle_emp.get_factory_plant_by_id() → plant
    → doc_db_router.resolve_doc_db_target() → DocDBTarget(plant, db_type, owner, db_profile)
    → docService(plant=...) → 自動路由到正確的 DB
```

### Ownership 驗證
- `docService.check_ownership(login_user, key_type, key_val)`
  - key_type `"EF"` → 檢查 EM_PSID/IM_PSID = login_user
  - key_type `"DF"` → 檢查 TM_PSID = login_user
- **所有附件下載/預覽必須通過 ownership 檢查**

---

## 五、允許的公文處理 Skills

### 1️⃣ 讀取與查詢類（Read-only）

#### `read_document`

**用途**：讀取單筆或多筆公文資料（不含附件內容）

* 來源：`docService.search_trst_advanced()` / `docService.search_incoming_advanced()`
* 行為：SELECT only
* 適用：公文主檔、來文資訊、欄位說明
* ⚠️ 自動依使用者廠區路由到對應 DB

```text
read_document(doc_id)
read_document(filters)      # grsno, subject, psids, days_ago, limit
```

---

#### `read_document_content`

**用途**：讀取公文本文（文字）

* Sybase：需經 `_decode_bytes_best_effort()` 處理 cp950/Big5
* Oracle：直接 `TO_CHAR()` 讀取 UTF-8
* 不含二進位附件本體

```text
read_document_content(doc_id)
```

---

#### `read_attachment_metadata`

**用途**：讀取附件清單（不讀實體檔）

* 來源：`docService.lookup_incoming()` / `docService.list_files_by_ef_id()`
* 回傳：EF_ID, EF_NAME, EF_PAGE, EF_DATA_LEN

```text
read_attachment_metadata(doc_id)
```

---

#### `download_attachment`

**用途**：下載指定附件（EF/DF）

* **必須通過 `check_ownership` 驗證**
* 來源：`docService.get_file_by_ef_id()` / `docService.get_file_by_df_path()`
* Sybase BLOB 經 `api_sybase_blob_stash` 暫存後供前端下載

```text
download_attachment(attach_key)     # EF:{ef_id} 或 DF:{df_path}
```

---

#### `todo_lookup`

**用途**：查詢個人待辦公文

* 來源：`todoService.list_items()`
* 限制：`IM_PSID / EM_PSID = login_user` 且 `IM_CNCDT IS NULL`（未結案）
* 支援依 plant 路由

```text
todo_lookup(login_user, q?, plant?)
```

---

### 2️⃣ 分析與整理類（LLM 合法用途）

#### `summarize_document`

**用途**：公文摘要（不新增事實）

* 僅可根據既有內容整理
* 不得補寫不存在資訊
* 使用 `get_chat_model()` 產生

```text
summarize_document(doc_id)
```

---

#### `classify_document`

**用途**：公文分類／主旨判斷

* 僅回傳分類結果
* 不改寫原文
* TD_FORMAT 對應：簽呈、令、呈、函、便籤

```text
classify_document(doc_id)
```

---

#### `extract_key_fields`

**用途**：擷取欄位（主旨、來文機關、日期、承辦單位）

* 來源可為 LLM 解析或 DB 欄位直讀
* 支援 `api_parse_attachments` / `api_parse_attachments_focus`

```text
extract_key_fields(doc_id)
```

---

### 3️⃣ 回覆與擬稿輔助（非自動送出）

#### `draft_reply`

**用途**：協助擬定回文草稿（不直接寫入 DB）

* 僅產出文字建議
* 最終送出需人工確認
* 使用 `draft_reply_service.py` + `draft_tone_rules.json`
* 支援三層級語氣：`FROM_SUPERIOR` / `FROM_PEER` / `FROM_SUBORDINATE`
* 來文機關層級由 `org_level_map.json` 判斷

**⚠️ 公文擬稿強制規則：**
1. **擬稿前必須先確認來文層級**：`FROM_SUPERIOR` / `FROM_PEER` / `FROM_SUBORDINATE`
2. **若未提供來文層級，必須先詢問，不得自行判斷**
3. 擬稿時必須嚴格遵守對應層級的語氣規範（`draft_tone_rules.json`）
4. **不得混用不同層級的語氣或用詞**
5. 各層級語氣定義：
   - `FROM_SUPERIOR`：對方為上級單位，本單位為下級回覆方（回報／說明式）
   - `FROM_PEER`：對方為平行單位，雙方無指揮關係（協調／會辦式）
   - `FROM_SUBORDINATE`：對方為下級單位，本單位為上級回覆方（指導／要求式）

```text
draft_reply(doc_id, from_level, instruction?, doc_meta?, doc_text?, context?)
```

---

#### `draft_meeting_reply`

**用途**：會議結論 / 會辦意見草稿

```text
draft_meeting_reply(doc_id, meeting_context)
```

---

### 4️⃣ 範例庫管理

#### `manage_templates`

**用途**：管理公文範例庫（CRUD via Django ORM `DocumentTemplate`）

* 來源：`views_templates.py`
* 支援：列表 / 新增 / 更新 / 刪除
* 寫入 DB：允許（僅限 Django SQLite 範例庫，非公文 DB）

```text
manage_templates(action, template_data?)
```

---

#### `import_template_from_sybase`

**用途**：從 Sybase/Oracle 既有公文匯入為範例

* **限制 TM_PSID = login_user（僅能匯入本人承辦公文）**
* 來源：`docService.query_import_from_template()`
* 含附件文字擷取：`_extract_text_by_ext()`
* 匯入後存入 Django `DocumentTemplate`

```text
import_template_from_sybase(grsno, plant?)
```

---

### 5️⃣ LLM 公文生成

#### `generate_document`

**用途**：根據範例 + 指示產生公文草稿

* 來源：`views_generate.py` → `api_generate`
* 使用 `get_chat_model()` + `build_prompt_v2()`
* 支援 RAG context（Chroma knowledge base）
* **僅產出草稿，不寫入公文 DB**

```text
generate_document(template_id?, instruction?, doc_type?)
```

---

### 6️⃣ 規範與一致性檢查（Guard Skills）

#### `check_format_compliance`

**用途**：檢查公文格式是否符合內部規範

* 不自動修正
* 僅回報問題清單

```text
check_format_compliance(doc_id)
```

---

#### `check_policy_conflict`

**用途**：檢查是否違反內部規範或流程

```text
check_policy_conflict(doc_id)
```

---

### 7️⃣ 記錄與說明類（安全）

#### `explain_decision`

**用途**：說明摘要、分類、擬稿依據

* 僅說明 reasoning，不涉及模型內部 prompt

```text
explain_decision(doc_id)
```

---

## 六、明確禁止的行為（即使技術上可行）

🚫 以下行為 **不屬於任何 skill，視為違規**：

* 自動送出公文
* 自動變更公文狀態（結案、核定、退文）
* 對公文 DB（Sybase/Oracle）進行 INSERT / UPDATE / DELETE（**DB 本身也無寫入權限**）
* 變更附件內容或檔名
* 以 LLM 捏造不存在的法規、依據或來文
* 代替承辦人作出正式行政決定
* 任何未經人工確認的對外發文行為
* **跨廠區存取他人公文（繞過 PSID 限制）**
* **自行撰寫 raw SQL（必須透過 docService）**
* **繞過 `@require_node` 權限裝飾器**
* **直接操作 DB 連線（必須走 DB_FACTORY）**
* **未確認來文層級即進行擬稿（必須先詢問）**
* **混用不同層級的語氣或用詞**

---

## 七、與系統規範的對齊聲明（給 Agent 看）

```md
本 skills 僅提供「輔助處理能力」。
所有公文最終決定權、送出權、核定權，均屬人員職權，
Agent 僅能提供建議，不得自動執行。

多廠區注意事項：
1. 所有廠區 DB 皆為唯讀權限（SELECT ONLY），無 INSERT/UPDATE/DELETE 權限
2. 不同廠區使用不同 DB (Sybase/Oracle)，SQL 語法有差異
3. 使用者與廠區的關聯由 CT_EMPLOY.FACTORY_PLANT 決定
4. 所有查詢必須透過 docService，由 service 層處理雙軌 SQL
5. 附件 BLOB 在 Sybase 需特殊編碼處理 (cp950/Big5)
6. Oracle 廠區直接使用 UTF-8，無需額外解碼
7. 嚴禁硬編碼廠區或 owner，必須由 doc_db_router 動態解析
8. 可寫入的僅有 Django 本地 SQLite（範例庫 DocumentTemplate）
```
