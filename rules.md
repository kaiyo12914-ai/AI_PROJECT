# DJANGO 主專案規範（Primary Rules）

版本日期：2026-03-18
適用路徑：F:\AI\AI_TOOLS（並作為其他專案主規範來源）

## 規範層級
1. 本檔（F:\AI\AI_TOOLS\rules.md）為五專案最高規範。
2. 其他專案 rules.md 只能補充，不得與本檔衝突。
3. 發生衝突時，以本檔為準。

## 專案獨立原則
- 每個專案獨立部署、獨立啟動程序、獨立程式碼邊界。
- 禁止以 PYTHONPATH 或直接路徑注入方式跨專案 import 函數。
- 專案間整合僅能透過 API、訊息佇列或明確資料交換流程。

## 共用開發設定
- 共用開發 workspace：F:\AI\AI_TOOLS\openclaw-workspace
- 共用虛擬環境優先：H:\AI\VENV3.12
- 回退環境：H:\AI\venv3.12

## 變更管理
- 任何專案規範調整，先更新本檔，再同步更新其他專案 rules.md。
- 請將長期有效政策同步記錄於：
  F:\AI\AI_TOOLS\openclaw-workspace\LONG_TERM_MEMORY.md
