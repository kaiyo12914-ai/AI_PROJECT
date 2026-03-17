import os
import sys
from pathlib import Path
from datetime import datetime

def read_needs_file(webproj_path):
    """讀取 needs.txt 文件並返回需要包含的路徑列表"""
    needs_path = webproj_path / "needed_code.txt"
    if not needs_path.exists():
        print(f"錯誤: {needs_path} 不存在，請確認路徑")
        sys.exit(1)

    with open(needs_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_timestamped_filename():
    """生成含時間戳記的文件名"""
    now = datetime.now()
    timestamp = now.strftime("%d%H%M")  # 格式: DDHHMM
    return Path("needed_code_"+timestamp+".txt").resolve()

def process_path(path_str):
    """處理單個路徑（目錄或文件）"""
    abs_path = Path(path_str).resolve()

    if not abs_path.exists():
        print(f"警告: 路徑不存在 - {abs_path}")
        return None

    # 驗證是有效類型
    valid_extensions = ('.py', '.html')
    if abs_path.is_file() and not abs_path.suffix.lower() in valid_extensions:
        print(f"警告: 非有效文件 - {abs_path}")
        return None

    return abs_path

def write_file_content(abs_path, output_file):
    """將單個文件內容寫入輸出文件"""
    try:
        with open(abs_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            line_count = len(content.split('\n'))

            with open(output_file, 'a', encoding='utf-8') as out_f:
                out_f.write(f"\n\n===== 文件: {abs_path} =====\n")
                out_f.write("=== 代碼內容 ===\n")
                out_f.write(content + "\n")

    except UnicodeDecodeError:
        print(f"警告: 無法解碼 - {abs_path}")
    except Exception as e:
        print(f"錯誤處理 {abs_path}: {str(e)}")

def list_files_with_content(root_dir, needs_paths):
    """列出 needed_code.txt 中指定的目錄和文件"""
    output_file = get_timestamped_filename()

    with open(output_file, 'w', encoding='utf-8') as f:
        # 寫入標題
        now = datetime.now()
        f.write(f"== 需要程式碼清單 ==\n")
        f.write(f"生成時間: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    # 處理所有路徑
    for path_str in needs_paths:
        abs_path = process_path(path_str)
        if not abs_path or not abs_path.exists():
            continue

        if abs_path.is_file():
            write_file_content(abs_path, output_file)
        else:  # 是目錄
            for root, _, files in os.walk(abs_path):
                for filename in sorted(files):
                    full_path = Path(root) / filename
                    if full_path.suffix.lower() in ('.py', '.html'):
                        write_file_content(full_path, output_file)

    print(f"\n成功生成需要程式碼清單到:")
    print(f"文件: {output_file}")
    print(f"大小: {os.path.getsize(output_file)//1024:.1f}KB")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使用方法: python generate_needed_code.py <root_dir>")
        print("\n範例:")
        print("python generate_needed_code.py H:\\AI\\Django")
        print("\n需要文件格式 (needed_code.txt):")
        print('D:\\AI\\Django\\webproj\\settings.py')
        print('D:\\AI\\Django\\webapps\\api')
        sys.exit(1)

    root_dir = Path(sys.argv[1])
    if not root_dir.exists():
        print(f"錯誤: 根目錄不存在 - {root_dir}")
        sys.exit(1)

    needs_paths = read_needs_file(root_dir)
    list_files_with_content(root_dir, needs_paths)