# ProjectNotes 舊資料庫升級流程

## 目的
- 將既有環境（INT/EXT）安全升級到 `projectnotes` 最新 schema。
- 確保 migration、索引、資料一致性都可追蹤。

## 前置檢查
1. 進入專案根目錄：`./`
2. 確認 Python 環境：`../venv3.12/Scripts/python.exe`
3. 確認目前 migration 狀態：
```powershell
& ../venv3.12/Scripts/python.exe manage.py showmigrations projectnotes
```

## 升級步驟
1. 先做資料庫備份（建議）
- SQLite：備份 `db.sqlite3`
- 其他 DB：依既有 DBA 流程做快照

2. 執行 migration
```powershell
& ../venv3.12/Scripts/python.exe manage.py migrate projectnotes
```

3. 執行 Django 檢查
```powershell
& ../venv3.12/Scripts/python.exe manage.py check
```

4. 執行索引檢視
```powershell
& ../venv3.12/Scripts/python.exe manage.py projectnotes_index_check
```

## 升級後驗證（Smoke Test）
1. 建立專案
2. 上傳一份檔案來源
3. 匯入一個網頁來源（reference）
4. 建立對話並提問
5. 確認回答包含「出處」與 citation
6. 確認「載入對話」可重播歷史紀錄

## 回滾策略
1. 若 migration 失敗但未寫入成功：
- 修復程式碼後重跑 `migrate`

2. 若已套用 migration 且需要回退：
```powershell
& ../venv3.12/Scripts/python.exe manage.py migrate projectnotes 0001
```

3. 若資料不一致：
- 以備份還原，重新執行升級步驟

## 發版建議
- 先於測試環境完整跑過升級與 smoke test。
- 正式環境升級後保留 migration 與檢查輸出紀錄。

