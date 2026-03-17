# test_db_connection.py
import sys
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent  # 從 tests 文件夾向上移動兩級到項目根
sys.path.append(str(project_root))

try:
    from webapps.database.db_factoryold import DatabaseFactory, get_db, db_connect
    conn = DatabaseFactory.create("sqlserver")
except ImportError as e:
    print(f"导入错误: {str(e)}")
    sys.exit(1)

def print_header(message):
    """打印分隔线和标题"""
    line = "=" * 50
    print(f"\n{line}")
    print(f"{message:^40}")
    print(line + "\n")

def test_sql_server():
    print_header("Testing SQL Server Connection")

    # 獲取數據庫實例
    db = get_db("sqlserver")

    try:
        # 嘗試連接
        conn = db.connect()
        if not conn:
            raise RuntimeError("Connection returned None unexpectedly")

        print("✅ 成功建立 SQL Server 連線")

        # 執行簡單查詢
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT TOP 10 * FROM sys.tables")
                result = cursor.fetchone()
                if result:
                    print("\n🔍 執行測試查詢 (SELECT TOP 10 * FROM sys.tables) 成功")
                    print(f"  第一個表的名稱: {result[0]}")
                else:
                    print("  查询返回空结果，可能是权限问题或没有可访问的表")

        except Exception as e:
            print(f"\n⚠️ 測試查詢時發生錯誤: {str(e)}")
            print("  但這不影響基本連線功能")

    except Exception as e:
        print(f"❌ SQL Server 連線失敗: {str(e)}")
    finally:
        if 'conn' in locals():
            try:
                conn.close()
                print("\n已關閉 SQL Server 連線")
            except:
                pass

def test_oracle():
    print_header("Testing Oracle Connection")

    # 獲取數據庫實例
    db = get_db("oracle")

    try:
        # 嘗試連接
        conn = db.connect()
        if not conn:
            raise RuntimeError("Connection returned None unexpectedly")

        print("✅ 成功建立 Oracle 連線")
        print(f"  連線狀態: {conn.version}")

        # 執行簡單查詢
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM v$version WHERE rownum = 1")
                result = cursor.fetchone()
                if result:
                    print("\n🔍 執行測試查詢 (SELECT * FROM v$version) 成功")
                    print(f"  Oracle 版本: {result}")
                else:
                    print("  查询返回空结果，可能是权限问题或没有可访问的视图")

        except Exception as e:
            print(f"\n⚠️ 測試查詢時發生錯誤: {str(e)}")
            print("  但這不影響基本連線功能")

    except Exception as e:
        print(f"❌ Oracle 連線失敗: {str(e)}")
    finally:
        if 'conn' in locals():
            try:
                conn.close()
                print("\n已關閉 Oracle 連線")
            except:
                pass

def test_direct_connection():
    print_header("Testing Direct Connection Function")

    try:
        # 直接獲取連接
        conn = db_connect("sqlserver")
        print("✅ 直接連線測試 (db_connect) 成功")
        # print(f"  連線狀態: {conn.connected}")
        conn.close()
    except Exception as e:
        print(f"❌ 直接連線失敗: {str(e)}")

def main():
    # 確保有 .env 文件配置
    if not sys.argv or "--skip-env-check" not in sys.argv:
        try:
            import os
            from dotenv import load_dotenv

            print("⚠️ 注意: 請確保已設定適當的 .env 文件")
            print(f"    所需變數: SQL_SERVER_* 或 ORA_*")
        except:
            pass

    # 執行測試
    test_direct_connection()
    test_sql_server()
    test_oracle()

if __name__ == "__main__":
    main()