#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vanna 2.0 Failed SQL 語法完整性診斷工具
適用環境：內網/外網 Django 環境
執行方式：
  1. 啟用虛擬環境：.\venv\Scripts\activate
  2. 執行指令：python check_failed_sqls_tool.py
"""

from __future__ import annotations

import os
import sys
import re
import django

# 設定專案根目錄，使 Django 可順利載入 modules
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# 設定 Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
try:
    django.setup()
except Exception as exc:
    print(f"Django 初始化失敗，請確保在正確的專案根目錄與虛擬環境下執行。錯誤原因: {exc}")
    sys.exit(1)

from webapps.vanna.models import FailedQueryRecord
from webapps.vanna.sql_guard import validate_sql

def check_incomplete(sql: str) -> tuple[bool, str]:
    sql = (sql or "").strip()
    if not sql:
        return True, "SQL 語法為空"
    
    # 1. 括號匹配檢查
    left_count = sql.count("(")
    right_count = sql.count(")")
    if left_count != right_count:
        return True, f"括號不匹配 (左括號 {left_count} 個，右括號 {right_count} 個)"
        
    # 2. SQL Guard 語意與開頭檢查 (必須是 SELECT 或 WITH SELECT)
    is_safe, err = validate_sql(sql)
    if not is_safe:
        return True, f"SQL Guard 阻擋: {err}"
        
    # 3. 未清洗之 Oracle 綁定變數檢查 (例如 :as_deptno) - 依需求不視為語意不完整，故跳過此判定
    # vars_found = re.findall(r'(?<!\w):([a-zA-Z_][a-zA-Z0-9_]*)', sql)
    # if vars_found:
    #     return True, f"包含未替換之綁定變數: {', '.join(set(vars_found))}"
        
    # 4. 檢查是否有 FROM 關鍵字 (DQL 結構完整度)
    if " FROM " not in f" {sql.upper()} ":
        return True, "缺少 FROM 關鍵字"

    return False, ""

def main():
    print("==================================================")
    print("  Vanna 2.0 Failed SQL 語意完整性檢查工具 (內網版)")
    print("==================================================")
    
    records = FailedQueryRecord.objects.all().order_by("id")
    total_count = records.count()
    print(f"目前資料庫中總共有 {total_count} 筆 Failed 記錄。")
    print("開始分析中，請稍候...")
    
    incomplete_list = []
    for rec in records:
        is_inc, reason = check_incomplete(rec.failed_sql)
        if is_inc:
            incomplete_list.append({
                "id": rec.id,
                "question": rec.question,
                "reason": reason,
                "error_message": rec.error_message,
                "failed_sql": rec.failed_sql
            })
            
    print(f"分析完成！共發現 {len(incomplete_list)} 筆語意不完整或包含未替換變數的 SQL 語法。\n")
    
    # 輸出成 Markdown 報告
    md_lines = []
    md_lines.append("# SQL 語法不完整之失敗語法精進記錄清單")
    md_lines.append(f"\n本報告列出 `nl2sql_failed_query_record` 資料表中所有 `failed_sql` 欄位語法不完整或無法直接執行的紀錄，共發現 **{len(incomplete_list)}** 筆（總 Failed 記錄筆數：{total_count}）。\n")
    
    for item in incomplete_list:
        md_lines.append(f"## 記錄 ID: {item['id']}")
        md_lines.append(f"* **自然語言提問**: {item['question']}")
        md_lines.append(f"* **判定為不完整的原因**: {item['reason']}")
        md_lines.append(f"* **原始錯誤訊息**: {item['error_message']}")
        md_lines.append("* **完整失敗 SQL 語法**:")
        md_lines.append("```sql")
        md_lines.append(item["failed_sql"])
        md_lines.append("```")
        md_lines.append("\n---")
        
    # 建立 .md 資料夾並寫入
    output_dir = os.path.join(BASE_DIR, ".md")
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "incomplete_sqls_report.md")
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        print(f"已成功將報告輸出至相對路徑：./.md/incomplete_sqls_report.md")
        print(f"絕對路徑為：{report_path}")
    except Exception as exc:
        print(f"寫入報告失敗: {exc}")

if __name__ == "__main__":
    main()


# .\venv\Scripts\python.exe check_failed_sqls_tool.py
