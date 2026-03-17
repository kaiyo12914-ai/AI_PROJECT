# Project

本專案使用 Codex / Agent 輔助開發。

## Agent 規範
- 系統提示：`.codex/system.md`
- 專案規範：`.codex/rules.md`
- 可用技能：`.codex/skills.md`

請勿在未更新上述規範的情況下，變更 Agent 行為。

## 公文查詢子程式（指定 IP）API 對照

### 端點
1. `POST/GET /djangoai/doc/api/sybase/query/search/`
2. `POST/GET /djangoai/doc/api/sybase/query/file/`
3. `POST/GET /djangoai/doc/api/sybase/query/preview/`

### 查詢結果四區塊與實體公文系統對應
1. `draft_docs`（簽、稿主檔清單，DF BLOB）
   對應實體公文系統「文件種類 / 流程資訊」主體列（簽、呈、令、函、便籤）。
2. `draft_attachments`（簽、稿附件清單，DF BLOB）
   對應實體公文系統「附件種類 / 附件檔名」區（非主體格式檔）。
3. `incoming_docs`（來文主旨清單）
   對應實體公文系統上方「電子來文」主旨 / 相關號資訊。
4. `incoming_attachments`（來文附件清單，EF BLOB）
   對應實體公文系統下方「電子來文附件」區。

### Oracle（205/209/401）查詢模式
- 當有 `grsno` 時，系統採三區塊檢索架構（主檔 / 主檔附件 / 來文附件）。
- `query.query_mode = "oracle_three_blocks"` 表示目前回應已採三區塊模式。
- 三區塊模式的目的為降低過度去重造成的筆數缺漏。
