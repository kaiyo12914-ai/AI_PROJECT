import os
import re

# 排除目錄
EXCLUDE_DIRS = {'.git', 'venv3.12', '.venv', 'node_modules', '__pycache__', 'staticfiles', 'media', 'chroma'}
# 檢查後綴
INCLUDE_EXTS = {'.py', '.js', '.css', '.html', '.txt', '.md', '.json', '.env'}

# 常見亂碼特徵 (UTF-8 誤認 CP950 或相反)
MOJIBAKE_PATTERNS = [
    r'\ufffd\ufffd',         # 連續替換字元
    r'锟斤拷',                # 經典 UTF-8 亂碼
    r'燙燙燙',                # 經典 VC++ 未初始化內存亂碼
    r'屯屯屯',
    r's',                   # 常見於編碼不匹配的開頭
]

def check_chinese_mojibake(path):
    issues = []
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        if not raw: return None

        # 1. 檢查 UTF-8 BOM
        if raw.startswith(b'\xef\xbb\xbf'):
            issues.append("UTF-8 with BOM")

        # 2. 嘗試解碼並檢查亂碼特徵
        content_utf8 = ""
        try:
            content_utf8 = raw.decode('utf-8')
            for p in MOJIBAKE_PATTERNS:
                if re.search(p, content_utf8):
                    issues.append(f"Mojibake Pattern Found: {p}")
            
            # 檢查替換字元密度
            repl_count = content_utf8.count('\ufffd')
            if repl_count > 3:
                issues.append(f"High density of Replacement Chars ({repl_count})")
                
        except UnicodeDecodeError:
            # 如果不是 UTF-8，檢查是否為 CP950
            try:
                raw.decode('cp950')
                issues.append("Non-UTF8 (Likely CP950/Big5)")
            except UnicodeDecodeError:
                issues.append("Binary/Invalid Encoding")

        return ", ".join(issues) if issues else None
    except Exception as e:
        return f"Read Error: {e}"

def main():
    root = r'H:\AI\Django'
    print(f"--- 深度檢查 Django 專案中文亂碼與編碼異常 ---")
    print(f"{'異常類型':<40} | {'檔案路徑'}")
    print("-" * 100)
    
    found_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in INCLUDE_EXTS: continue
            
            full_path = os.path.join(dirpath, fn)
            rel_path = os.path.relpath(full_path, root)
            
            issue = check_chinese_mojibake(full_path)
            if issue:
                print(f"{issue:<40} | {rel_path}")
                found_count += 1

    print("-" * 100)
    print(f"掃描結束。共發現 {found_count} 個潛在編碼異常檔案。")

if __name__ == "__main__":
    main()
