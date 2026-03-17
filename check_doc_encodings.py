import os

# 只針對 DOC 子系統目錄
DOC_ROOT = r'H:\AI\Django\webapps\doc'
INCLUDE_EXTS = {'.py', '.js', '.css', '.html', '.txt', '.md', '.json'}

def check_chinese_corruption(path):
    issues = []
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        if not raw: return None

        # 1. 檢查 UTF-8 BOM
        if raw.startswith(b'\xef\xbb\xbf'):
            issues.append("UTF-8 with BOM")

        # 2. 核心檢查：UTF-8 解碼與中文完整性
        try:
            content = raw.decode('utf-8')
            # 檢查是否有常見亂碼特徵：如 "锟斤拷" (UTF-8 誤認出的常見亂碼) 或大量問號
            if '\ufffd' in content: # 替換字元 (Replacement Character)
                issues.append("Contains Unicode Replacement Chars (Potential Corruption)")
        except UnicodeDecodeError:
            # 如果 utf-8 失敗，嘗試 cp950
            try:
                raw.decode('cp950')
                issues.append("Non-UTF8 Encoding (Legacy Big5/CP950)")
            except UnicodeDecodeError:
                issues.append("Invalid Encoding / Corrupted")

        return ", ".join(issues) if issues else None
    except Exception as e:
        return f"Read Error: {e}"

def main():
    print(f"--- Scanning [DOC Subsystem] for Chinese Encoding Issues ---")
    print(f"{'Issue':<45} | {'File Path'}")
    print("-" * 100)
    
    found_count = 0
    for dirpath, dirnames, filenames in os.walk(DOC_ROOT):
        if '__pycache__' in dirnames:
            dirnames.remove('__pycache__')
        
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in INCLUDE_EXTS: continue
            
            full_path = os.path.join(dirpath, fn)
            rel_path = os.path.relpath(full_path, r'H:\AI\Django')
            
            issue = check_chinese_corruption(full_path)
            if issue:
                print(f"{issue:<45} | {rel_path}")
                found_count += 1

    print("-" * 100)
    print(f"DOC Subsystem Scan complete. Found {found_count} files with potential issues.")

if __name__ == "__main__":
    main()
