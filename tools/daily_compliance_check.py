import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 強制 UTF-8 輸出
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
RULES_FILE = os.path.join(PROJECT_ROOT, '.codex', 'rules.md')

def check_rules():
    report = []
    report.append(f"🔍 Django 專案規範稽核報告 ({datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')})")
    report.append("-" * 30)

    # 1. 檢查 URL & Proxy 鐵則 (urls.py 禁止硬寫 /djangoai)
    report.append("【URL & Proxy 檢查】")
    urls_violation = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        if any(ex in root for ex in ['venv', 'node_modules', '.git']): continue
        for fn in files:
            if fn == 'urls.py':
                path = os.path.join(root, fn)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if '/djangoai' in content:
                        urls_violation.append(os.path.relpath(path, PROJECT_ROOT))
    if urls_violation:
        report.append(f"❌ 違反: urls.py 含有硬寫前綴: {', '.join(urls_violation)}")
    else:
        report.append("✅ 通過: 未發現硬寫 URL 前綴。")

    # 2. 檢查 DB_FACTORY 唯一入口
    report.append("\n【DB 入口檢查】")
    db_violation = []
    for root, dirs, files in os.walk(os.path.join(PROJECT_ROOT, 'webapps')):
        if 'database' in root or '__pycache__' in root: continue
        for fn in files:
            if fn.endswith('.py'):
                path = os.path.join(root, fn)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if 'pyodbc.connect' in content or 'oracledb.connect' in content:
                        db_violation.append(os.path.relpath(path, PROJECT_ROOT))
    if db_violation:
        report.append(f"❌ 違反: 發現跳過 db_factory 自建連線: {', '.join(db_violation)}")
    else:
        report.append("✅ 通過: 所有 DB 存取皆符合規範。")

    # 3. 檢查編碼規範 (UTF-8 No BOM)
    report.append("\n【文件編碼檢查】")
    bom_files = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        if any(ex in root for ex in ['venv', 'node_modules', '.git', 'staticfiles', 'media']): continue
        for fn in files:
            if fn.endswith(('.py', '.js', '.html', '.css', '.md')):
                path = os.path.join(root, fn)
                with open(path, 'rb') as f:
                    if f.read(3) == b'\xef\xbb\xbf':
                        bom_files.append(os.path.relpath(path, PROJECT_ROOT))
    if bom_files:
        report.append(f"❌ 違反: 發現帶有 BOM 之檔案: {len(bom_files)} 筆")
    else:
        report.append("✅ 通過: 所有程式碼皆為無 BOM 格式。")

    return "\n".join(report)

if __name__ == "__main__":
    result = check_rules()
    # 將結果存入專案下的臨時稽核檔，供 Cron 回報讀取
    audit_log = os.path.join(PROJECT_ROOT, 'ref', 'daily_audit_report.txt')
    os.makedirs(os.path.dirname(audit_log), exist_ok=True)
    with open(audit_log, 'w', encoding='utf-8') as f:
        f.write(result)
    print(result)
