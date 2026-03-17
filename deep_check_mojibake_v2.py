import os
import re
import sys

# 強制輸出為 UTF-8 避免終端機列印亂碼報錯
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

EXCLUDE_DIRS = {'.git', 'venv3.12', '.venv', 'node_modules', '__pycache__', 'staticfiles', 'media', 'chroma'}
INCLUDE_EXTS = {'.py', '.js', '.css', '.html', '.txt', '.md', '.json', '.env'}

# 修正後的亂碼特徵
MOJIBAKE_PATTERNS = [
    (r'\ufffd\ufffd', "連續替換字元 (Replacement Chars)"),
    (r'锟斤拷', "經典 UTF-8 誤認亂碼 (Kun-Jin-Kao)"),
    (r'燙燙燙', "記憶體未初始化亂碼 (Tang-Tang-Tang)"),
    (r'屯屯屯', "記憶體未初始化亂碼 (Tun-Tun-Tun)"),
    (r'ï»¿', "誤將 UTF-8 BOM 視為文字"),
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

        # 2. 檢測 UTF-8
        try:
            content_utf8 = raw.decode('utf-8')
            for p, desc in MOJIBAKE_PATTERNS:
                if re.search(p, content_utf8):
                    issues.append(f"{desc}")
            
            # 檢查替換字元密度
            repl_count = content_utf8.count('\ufffd')
            if repl_count > 3:
                # 排除特定的過濾代碼檔案
                if "doc_index_bootstrap.js" not in path:
                    issues.append(f"高密度替換字元 ({repl_count})")
                
        except UnicodeDecodeError:
            # 3. 檢測是否為 Big5/CP950 但檔案應為 UTF-8
            try:
                raw.decode('cp950')
                issues.append("非 UTF-8 編碼 (可能是 Big5/CP950)")
            except UnicodeDecodeError:
                issues.append("二進位或嚴重損毀編碼")

        return ", ".join(set(issues)) if issues else None
    except Exception as e:
        return f"讀取錯誤: {e}"

def main():
    root = r'H:\AI\Django'
    print(f"{'異常類型':<35} | {'檔案路徑'}")
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
                print(f"{issue:<35} | {rel_path}")
                found_count += 1

    print("-" * 100)
    print(f"掃描結束。共發現 {found_count} 個潛在編碼異常檔案。")

if __name__ == "__main__":
    main()
