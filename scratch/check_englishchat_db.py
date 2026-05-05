import os
import sys

sys.path.append(r'H:\AI\AI_TOOLS')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')

import django
django.setup()

from webapps.englishchat.repository import EnglishChatQuestionBankRepository

repo = EnglishChatQuestionBankRepository()

# 1. 取得總數與啟用數
sql_total = """
SELECT COUNT(*) as total_count,
       SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_count
FROM englishchat_question_bank;
"""
total_rows = repo.query_all(sql_total, [], profile=repo.profile)
print("=== 總覽 ===")
if total_rows and len(total_rows) > 0:
    r = total_rows[0]
    print(f"總題數: {r[0]}")
    print(f"已啟用題數: {r[1]}")
else:
    print("無法取得總數或無資料。")

# 2. 依照主題、模式、等級分組統計
sql_group = """
SELECT topic_key, mode, level, COUNT(*) as count,
       SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_count
FROM englishchat_question_bank
GROUP BY topic_key, mode, level
ORDER BY topic_key, mode, level;
"""
group_rows = repo.query_all(sql_group, [], profile=repo.profile)
print("\n=== 分組統計 (主題 / 模式 / 等級) ===")
for r in group_rows:
    print(f"Topic: {r[0]:15} | Mode: {r[1]:10} | Level: {r[2]:10} | 總數: {r[3]:3} | 啟用: {r[4]:3}")

# 3. 檢查重要欄位的空值狀況
sql_nulls = """
SELECT 
    SUM(CASE WHEN prompt_text IS NULL OR prompt_text = '' THEN 1 ELSE 0 END) as null_prompt,
    SUM(CASE WHEN mode = 'choice' AND (choices_json IS NULL OR choices_json::text = '[]' OR choices_json::text = '') THEN 1 ELSE 0 END) as null_choices,
    SUM(CASE WHEN answer_text IS NULL OR answer_text = '' THEN 1 ELSE 0 END) as null_answer
FROM englishchat_question_bank;
"""
null_rows = repo.query_all(sql_nulls, [], profile=repo.profile)
print("\n=== 空值/異常檢查 ===")
if null_rows and len(null_rows) > 0:
    r = null_rows[0]
    print(f"缺少 prompt_text 的題數: {r[0]}")
    print(f"mode 為 choice 但缺少 choices_json 的題數: {r[1]}")
    print(f"缺少 answer_text 的題數: {r[2]}")
