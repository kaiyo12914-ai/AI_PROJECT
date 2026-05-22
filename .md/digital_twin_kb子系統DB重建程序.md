# digital_twin_kb 子系統 DB 重建程序（離線內網）

本文目的：在內網離線電腦重建與目前 `digital_twin_kb`（數位雙生 RAG 知識庫）子系統一致的資料庫（含 TABLE 結構）。

## 1. TABLE 重建方式（兩種）

## 1.1 只重建結構（空庫）

在專案根目錄執行：

```powershell
python manage.py migrate digital_twin_kb
```

此方式會依 migration 建立 `digital_twin_kb` 的所有 table/index。

## 1.2 複製既有資料（建議）

在來源機器（現行 DB）先備份整個資料庫或指定 `digital_twin_kb` 資料表：

**僅備份 `digital_twin_kb` 的所有資料表：**

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes -F c -t "digital_twin_kb_*" -f digital_twin_kb_tables.dump
```

在目標離線機還原：

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges -h 127.0.0.1 -p 5432 -U projectnotes_user -d projectnotes digital_twin_kb_tables.dump
```

---

## 2. 現行 digital_twin_kb TABLE 清單

依 `webapps/digital_twin_kb/migrations/0001_initial.py`：

1. `digital_twin_kb_document` — 已匯入文檔資產庫主表
2. `digital_twin_kb_documentchunk` — 文檔切片與 pgvector 嵌入向量表 (dim: 384)
3. `digital_twin_kb_digitaltwincategory` — 數位雙生層級/分類定義表
4. `digital_twin_kb_qalog` — 歷史 RAG 問答紀錄表
5. `digital_twin_kb_knowledgenode` — 忿生實體/關聯知識節點表
6. `digital_twin_kb_ingestionjob` — 後台批量解析/匯入工作記錄表
7. `digital_twin_kb_userprofile` — 使用者角色與安全等級表
