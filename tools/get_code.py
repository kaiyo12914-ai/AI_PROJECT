import os
import sys
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple, Set


# ----------------------------
# Config
# ----------------------------
VALID_EXTENSIONS = {".py", ".html"}
DEFAULT_EXCLUDES = {
    ".git", ".svn", ".hg",
    "__pycache__",
    "node_modules",
    "venv", ".venv",
    "env", ".env",
    "dist", "build",
    ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode",
}


# ----------------------------
# Helpers
# ----------------------------
def read_needs_file(root_dir: Path) -> List[str]:
    """讀取 root_dir/webproj/needed_code.txt 文件並返回需要包含的路徑列表"""
    needs_path = root_dir / "needed_code.txt"
    if not needs_path.exists():
        print(f"錯誤: {needs_path} 不存在，請確認路徑")
        sys.exit(1)

    with open(needs_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def get_timestamped_filename(prefix: str = "needed_code") -> Path:
    """生成含時間戳記的文件名"""
    now = datetime.now()
    timestamp = now.strftime("%d%H%M")  # 格式: DDHHMM
    return Path(f"{prefix}_{timestamp}.txt").resolve()


def is_excluded_dir(path: Path, exclude_names: Set[str]) -> bool:
    """判斷該 path（資料夾）是否需要排除"""
    return path.name in exclude_names


def safe_read_text(p: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    讀檔：
    - 優先 utf-8-sig
    - fallback utf-8
    回傳 (content, error)
    """
    try:
        return p.read_text(encoding="utf-8-sig"), None
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding="utf-8"), None
        except Exception as e:
            return None, f"無法解碼: {e}"
    except Exception as e:
        return None, f"讀取失敗: {e}"


def write_file_content(abs_path: Path, output_file: Path) -> Tuple[bool, str]:
    """將單個文件內容寫入輸出文件，回傳 (ok, message)"""
    if not abs_path.exists():
        return False, f"不存在: {abs_path}"

    if abs_path.suffix.lower() not in VALID_EXTENSIONS:
        return False, f"略過(副檔名不符): {abs_path}"

    content, err = safe_read_text(abs_path)
    if err:
        return False, f"{err} - {abs_path}"
    if content is None:
        return False, f"空內容/讀取失敗: {abs_path}"

    with open(output_file, "a", encoding="utf-8") as out_f:
        out_f.write(f"\n\n===== 文件: {abs_path} =====\n")
        out_f.write("=== 代碼內容 ===\n")
        out_f.write(content)
        if not content.endswith("\n"):
            out_f.write("\n")
    return True, f"OK: {abs_path}"


def collect_by_needs_list(root_dir: Path, needs_paths: List[str], exclude_names: Set[str]) -> List[Path]:
    """依 needed_code.txt 收集檔案"""
    picked: List[Path] = []
    for path_str in needs_paths:
        abs_path = Path(path_str).resolve()
        if not abs_path.exists():
            continue

        if abs_path.is_file():
            if abs_path.suffix.lower() in VALID_EXTENSIONS:
                picked.append(abs_path)
            continue

        # dir
        for root, dirs, files in os.walk(abs_path):
            # 排除資料夾
            dirs[:] = [d for d in dirs if d not in exclude_names]
            for filename in sorted(files):
                fp = Path(root) / filename
                if fp.suffix.lower() in VALID_EXTENSIONS:
                    picked.append(fp)

    return picked


def collect_by_name_patterns(root_dir: Path, patterns: List[str], exclude_names: Set[str]) -> List[Path]:
    """
    全專案掃描，依檔名 pattern（如 urls.py, views.py）收集
    patterns 支援 fnmatch：例如 'urls.py' / '*urls.py' / 'views*.py'
    """
    picked: List[Path] = []
    for dirpath, dirs, files in os.walk(root_dir):
        # 排除
        dirs[:] = [d for d in dirs if d not in exclude_names]

        for fn in files:
            for pat in patterns:
                if fnmatch.fnmatch(fn, pat):
                    fp = Path(dirpath) / fn
                    if fp.suffix.lower() in VALID_EXTENSIONS:
                        picked.append(fp)
                    break
    return picked


def collect_by_globs(root_dir: Path, globs: List[str], exclude_names: Set[str]) -> List[Path]:
    """
    依 glob 收集，例如 '**/urls.py'、'webapps/**/urls.py'
    注意：glob 會掃到排除資料夾，所以我們後面再過濾一次 path parts
    """
    picked: List[Path] = []
    for g in globs:
        for fp in root_dir.glob(g):
            if not fp.is_file():
                continue
            # 排除路徑中含排除資料夾名稱
            if any(part in exclude_names for part in fp.parts):
                continue
            if fp.suffix.lower() in VALID_EXTENSIONS:
                picked.append(fp)
    return picked


def unique_sorted(paths: List[Path]) -> List[Path]:
    """去重 + 排序（依字串路徑）"""
    seen = set()
    out = []
    for p in paths:
        s = str(p)
        if s in seen:
            continue
        seen.add(s)
        out.append(p)
    out.sort(key=lambda x: str(x).lower())
    return out


# ----------------------------
# Main
# ----------------------------
def main():
    """
    用法：
      1) 依 needed_code.txt（原本模式）
         python generate_needed_code.py H:\\AI\\Django

      2) 全系統抓所有 urls.py
         python generate_needed_code.py H:\\AI\\Django --pattern urls.py

      3) 多 pattern
         python generate_needed_code.py H:\\AI\\Django --pattern urls.py --pattern views.py

      4) 用 glob
         python generate_needed_code.py H:\\AI\\Django --glob "**/urls.py" --glob "webapps/**/views.py"

      5) 快捷：抓全系統所有 urls.py
         python generate_needed_code.py H:\\AI\\Django --all-urls
    """
    if len(sys.argv) < 2:
        print("使用方法: python generate_needed_code.py <root_dir> [options]")
        print("\n常用範例:")
        print("  python tools/generate_needed_code.py .")
        print("  python tools/generate_needed_code.py . --pattern urls.py")
        print("  python tools/generate_needed_code.py . --pattern urls.py --pattern views.py")
        print('  python tools/generate_needed_code.py . --glob "**/urls.py"')
        print("  python tools/generate_needed_code.py . --all-urls")
        sys.exit(1)

    root_dir = Path(sys.argv[1]).resolve()
    if not root_dir.exists():
        print(f"錯誤: 根目錄不存在 - {root_dir}")
        sys.exit(1)

    # 解析參數（不引入 argparse，保持你原本簡潔）
    patterns: List[str] = []
    globs: List[str] = []
    prefix = "needed_code"
    exclude_names = set(DEFAULT_EXCLUDES)

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--pattern":
            i += 1
            if i >= len(args):
                print("錯誤: --pattern 後面要接檔名樣式，例如 urls.py")
                sys.exit(1)
            patterns.append(args[i])
        elif a == "--glob":
            i += 1
            if i >= len(args):
                print('錯誤: --glob 後面要接 glob，例如 "**/urls.py"')
                sys.exit(1)
            globs.append(args[i])
        elif a == "--all-urls":
            patterns.append("urls.py")
        elif a == "--all-settings":
            patterns.append("settings.py")
        elif a == "--all-views":
            patterns.append("views.py")
        elif a == "--prefix":
            i += 1
            if i >= len(args):
                print("錯誤: --prefix 後面要接輸出檔名前綴")
                sys.exit(1)
            prefix = args[i].strip() or prefix
        elif a == "--exclude":
            i += 1
            if i >= len(args):
                print("錯誤: --exclude 後面要接要排除的資料夾名稱")
                sys.exit(1)
            exclude_names.add(args[i])
        else:
            print(f"警告: 未識別參數 {a}（已忽略）")
        i += 1

    output_file = get_timestamped_filename(prefix=prefix)

    # Header
    with open(output_file, "w", encoding="utf-8") as f:
        now = datetime.now()
        f.write("== 需要程式碼清單 ==\n")
        f.write(f"根目錄: {root_dir}\n")
        f.write(f"生成時間: {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"排除資料夾: {', '.join(sorted(exclude_names))}\n")
        f.write(f"模式: needed_code.txt + patterns/globs\n\n")

    logs: List[str] = []

    # 1) 原本模式：needed_code.txt
    needs_paths = []
    try:
        needs_paths = read_needs_file(root_dir)
        picked = collect_by_needs_list(root_dir, needs_paths, exclude_names)
    except SystemExit:
        # 如果沒有 needed_code.txt 就不強制退出（改成允許只用 patterns）
        picked = []
        logs.append("提示：找不到 webproj/needed_code.txt，已略過清單模式（改用 patterns/globs）。")

    # 2) 新增：patterns 掃全專案
    if patterns:
        picked += collect_by_name_patterns(root_dir, patterns, exclude_names)

    # 3) 新增：glob 收集
    if globs:
        picked += collect_by_globs(root_dir, globs, exclude_names)

    picked = unique_sorted(picked)

    # Write
    ok_count = 0
    for fp in picked:
        ok, msg = write_file_content(fp, output_file)
        logs.append(msg)
        if ok:
            ok_count += 1

    # Footer log
    with open(output_file, "a", encoding="utf-8") as f:
        f.write("\n\n===== 統計 =====\n")
        f.write(f"輸出檔案數: {ok_count}\n")
        f.write(f"總候選數: {len(picked)}\n")
        f.write("\n===== 處理紀錄 =====\n")
        for line in logs:
            f.write(line + "\n")

    print("\n成功生成需要程式碼清單到:")
    print(f"文件: {output_file}")
    print(f"檔案數: {ok_count}")
    print(f"大小: {os.path.getsize(output_file)//1024:.1f}KB")


if __name__ == "__main__":
    main()
