-- 1) 驗證 extension（此腳本不會建立 extension）
SELECT extname, extversion FROM pg_extension ORDER BY extname;

-- 2) 驗證 table 是否存在
SELECT to_regclass('public.meeting_records');

-- 3) 驗證欄位結構
SELECT column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='meeting_records'
ORDER BY ordinal_position;

-- 4) 驗證主鍵
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='public.meeting_records'::regclass AND contype='p';


`public.meeting_records` 這張表本身**沒有 chunk 欄位**（沒有 `chunk_index/chunk_no/chunk_text`）。  
在目前腳本裡，它是「1 筆會議資料 = 1 筆紀錄」。

可這樣讀：

```sql
SELECT
  doc_id,        -- 例如 meeting_{CaseID}_{ItemNo}
  case_id,
  item_no,
  title,
  directive,
  status,
  dept_name,
  dept_code,
  updated_at
FROM public.meeting_records
ORDER BY updated_at DESC
LIMIT 100;
```

若你要把它當「chunk文字」來用，可組一欄：

```sql
SELECT
  doc_id,
  concat_ws(E'\n', title, directive, status) AS chunk_text
FROM public.meeting_records
ORDER BY updated_at DESC
LIMIT 100;
```

先確認表結構：

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND table_name='meeting_records'
ORDER BY ordinal_position;
```

如果你要真正的多段 chunk（有 `chunk_index`），要另建 chunk table 或改同步腳本，我可以直接幫你改。
