# tools/generate_needed_code.py
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
from datetime import datetime


def read_needs_file(root_dir: Path, needs_rel: str = "tools/needed_code.txt"):
    """讀取 needed_code.txt 文件並返回需要包含的路徑列表"""
    needs_path = Path(needs_rel)
    target = needs_path if needs_path.is_absolute() else (root_dir / needs_path).resolve()

    if not target.exists():
        print(f"錯誤: {target} 不存在，請確認路徑")
        sys.exit(1)

    with open(target, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def get_timestamped_filename(root_dir: Path) -> Path:
    """生成含時間戳記的文件名，固定輸出到 tools/"""
    now = datetime.now()
    timestamp = now.strftime("%m%d_%H%M")  # MMDD_HHMM
    tools_dir = root_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return (tools_dir / f"needed_code_{timestamp}.txt").resolve()


def process_path(root_dir: Path, path_str: str):
    """處理單個路徑（目錄或文件）"""
    s = (path_str or "").strip()
    if not s:
        return None

    p = Path(s)
    abs_path = p.resolve() if p.is_absolute() else (root_dir / p).resolve()

    if not abs_path.exists():
        print(f"警告: 路徑不存在 - {abs_path}")
        return None

    valid_extensions = (".py", ".html", ".js")
    if abs_path.is_file() and abs_path.suffix.lower() not in valid_extensions:
        print(f"警告: 非有效文件 - {abs_path}")
        return None

    return abs_path


def write_file_content(abs_path: Path, output_file: Path):
    """將單個文件內容寫入輸出文件"""
    try:
        with open(abs_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        with open(output_file, "a", encoding="utf-8") as out_f:
            out_f.write(f"\n\n===== 文件: {abs_path} =====\n")
            out_f.write("=== 代碼內容 ===\n")
            out_f.write(content + "\n")

    except UnicodeDecodeError:
        print(f"警告: 無法解碼 - {abs_path}")
    except Exception as e:
        print(f"錯誤處理 {abs_path}: {str(e)}")


def list_files_with_content(root_dir: Path, needs_paths):
    """列出 needed_code.txt 中指定的目錄和文件"""
    output_file = get_timestamped_filename(root_dir)

    with open(output_file, "w", encoding="utf-8") as f:
        now = datetime.now()
        f.write("== 需要程式碼清單 ==\n")
        f.write(f"生成時間: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    for path_str in needs_paths:
        abs_path = process_path(root_dir, path_str)
        if not abs_path:
            continue

        if abs_path.is_file():
            write_file_content(abs_path, output_file)
        else:
            for root, _, files in os.walk(abs_path):
                for filename in sorted(files):
                    full_path = Path(root) / filename
                    if full_path.suffix.lower() in (".py", ".html", ".js", ".css"):
                        write_file_content(full_path, output_file)

    print("\n成功生成需要程式碼清單到:")
    print(f"文件: {output_file}")
    print(f"大小: {os.path.getsize(output_file) / 1024:.1f}KB")


if __name__ == "__main__":
    # 用法：
    # python tools\generate_needed_code.py H:\AI\Django
    # python tools\generate_needed_code.py H:\AI\Django tools\needed_code.txt
    if len(sys.argv) not in (2, 3):
        print(r"使用方法: python tools\generate_needed_code.py <root_dir> [needs_file]")
        sys.exit(1)

    root_dir = Path(sys.argv[1]).resolve()
    if not root_dir.exists():
        print(f"錯誤: 根目錄不存在 - {root_dir}")
        sys.exit(1)

    needs_rel = sys.argv[2] if len(sys.argv) == 3 else "tools/needed_code.txt"
    needs_paths = read_needs_file(root_dir, needs_rel)
    list_files_with_content(root_dir, needs_paths)

# 將 needed_code.txt 指定的程式碼併為文字檔(有超長文問題)
# python tools\generate_needed_code.py H:\AI\Django tools\needed_code.txt