import os
import sys

# 排除目錄
EXCLUDE_DIRS = {'.git', 'venv3.12', '.venv', 'node_modules', '__pycache__', 'staticfiles', 'media', 'chroma'}
# 檢查後綴
INCLUDE_EXTS = {'.py', '.js', '.css', '.html', '.txt', '.md', '.json', '.env'}

def check_file(path):
    issues = []
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        
        if not raw:
            return None

        # 1. 檢查 UTF-8 BOM (Byte Order Mark: \xef\xbb\xbf)
        if raw.startswith(b'\xef\xbb\xbf'):
            issues.append("UTF-8 with BOM")

        # 2. 檢查是否包含亂碼 (含有無法以 UTF-8 解碼的位元組)
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError:
            # 嘗試用 cp950 解碼看看，如果 cp950 可以但 utf-8 不行，通常就是傳統編碼造成的亂碼
            try:
                raw.decode('cp950')
                issues.append("Encoding Issue (Legacy CP950/Big5?)")
            except UnicodeDecodeError:
                issues.append("Binary or Corrupted Characters")

        # 3. 檢查特殊控制字元 (如 \x1a SUB, 常在資料庫匯出出錯時出現)
        if b'\x1a' in raw:
            issues.append("Contains SUB character (\\x1a)")

        return ", ".join(issues) if issues else None
    except Exception as e:
        return f"Read Error: {e}"

def main():
    root = r'H:\AI\Django'
    print(f"--- Scanning Django Project for Encoding Issues ---")
    print(f"{'Issue':<30} | {'File Path'}")
    print("-" * 80)
    
    found_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # 排除目錄
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in INCLUDE_EXTS:
                continue
            
            full_path = os.path.join(dirpath, fn)
            rel_path = os.path.relpath(full_path, root)
            
            issue = check_file(full_path)
            if issue:
                print(f"{issue:<30} | {rel_path}")
                found_count += 1

    print("-" * 80)
    print(f"Scan complete. Found {found_count} files with potential issues.")

if __name__ == "__main__":
    main()
