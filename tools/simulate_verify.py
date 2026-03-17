
import os
import django
import sys
import json

# 強制輸出為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# 設定 Django 環境
sys.path.append('H:/AI/DJANGO')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webproj.settings')
django.setup()

from webapps.doc.views_parse import _inject_org_level_point

def simulate_verification():
    print("START_SIMULATION: 開始後端邏輯模擬驗證...")
    
    test_cases = [
        {
            "name": "1. 上級來文 (函)",
            "org": "國防部參謀本部通信電子資訊參謀次長室",
            "level": "FROM_SUPERIOR",
            "date": "民國114年12月26日",
            "no": "國通軟資字第1140372867號",
            "type": "函",
            "subject": "重要資訊服務系統備援機制"
        },
        {
            "name": "2. 直屬上級 (令)",
            "org": "國防部軍備局",
            "level": "FROM_SUPERIOR",
            "date": "民國114年12月3日",
            "no": "國備獲管字第1140012345號",
            "type": "令",
            "subject": "修頒「○○規定」辦理"
        },
        {
            "name": "3. 平行單位 (函)",
            "org": "內政部資訊署",
            "level": "FROM_PEER",
            "date": "民國114年12月3日",
            "no": "內信字第1140000001號",
            "type": "函",
            "subject": "修正條文配合辦理"
        },
        {
            "name": "4. 下級單位 (函)",
            "org": "第205廠",
            "level": "FROM_SUBORDINATE",
            "date": "民國114年12月3日",
            "no": "廠獲字第1140000999號",
            "type": "函",
            "subject": "函報執行情形"
        }
    ]

    print("\n[重點一驗證報告]")
    print("-" * 50)
    for tc in test_cases:
        res = _inject_org_level_point(
            summary_text="AI 重點...",
            org=tc["org"],
            level=tc["level"],
            doc_date=tc["date"],
            doc_no=tc["no"],
            doc_type=tc["type"],
            doc_subject=tc["subject"],
            full_text_for_search=tc["subject"]
        )
        point_one = next((line for line in res.splitlines() if line.startswith("重點1：")), "FAIL")
        print(f"類型：{tc['name']}")
        print(f"產出：{point_one}")
        print("-" * 50)

if __name__ == "__main__":
    simulate_verification()
