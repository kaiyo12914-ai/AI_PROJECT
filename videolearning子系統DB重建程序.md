# videolearning 子系統 DB 重建程序（內網版）

本文件僅提供 `videolearning` 相關資料表的「匯出（含 schema + data）」與「匯入」步驟。

## 1. 目標資料表

1. `videolearning_category`
2. `videolearning_tag`
3. `videolearning_asset`
4. `videolearning_asset_tags`
5. `videolearning_playlist`
6. `videolearning_playlist_item`
7. `videolearning_transcript`
8. `videolearning_chapter`

## 2. 匯出方式（含 schema + data）
### 匯出單一 dump（建議）

```powershell
pg_dump -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes -t videolearning_category -t videolearning_tag -t videolearning_asset -t videolearning_asset_tags -t videolearning_playlist -t videolearning_playlist_item -t videolearning_transcript -t videolearning_chapter -F c -f videolearning_tables_full.dump
```

說明：
- `-F c` 為 custom format，含 schema + data。
- 可用 `pg_restore` 做還原。

## 3. 匯入方式 可重複匯入
###  匯入 單一 dump（建議）

```powershell
pg_restore --clean --if-exists --no-owner --no-privileges -h 192.168.0.137 -p 5432 -U projectnotes_user -d projectnotes .\videolearning_tables_full.dump
---

說明：
- `--clean --if-exists`：先刪除舊物件再重建，避免 `relation already exists`。
- 匯入前請確認目標 DB 連線帳號有建表/建索引/寫入權限。


