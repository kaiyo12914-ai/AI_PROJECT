import os
import pyodbc
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

try:
    # 从环境变量获取配置（优先使用 .env 中的值）
    config = {
        'host': os.getenv('SQL_SERVER_HOST', 'mssql1.mpc.mil.tw'),
        'database': os.getenv('SQL_SERVER_DATABASE', 'CaseManager'),
        'user': os.getenv('SQL_SERVER_USER', 'sa'),
        'password': os.getenv('SQL_SERVER_PASSWORD', 'Aa123456')
    }

    # 构建连接字符串
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={config['host']}\\mpcsqlserver;"
        f"DATABASE={config['database']};"
        f"UID={config['user']};"
        f"PWD={config['password']};"
    )

    # 建立连接
    conn = pyodbc.connect(conn_str)
    print("✅ 连接 SQL Server 成功！")
    print(pyodbc.drivers())

    with conn.cursor() as cursor:
        # 1. 查询服务器信息
        cursor.execute("SELECT @@VERSION")
        version_info = cursor.fetchone()[0]
        print(f"\n🛠️ 服务器版本: {version_info}")

        cursor.execute("SELECT GETDATE() AS ServerTime")
        server_time = cursor.fetchone()[0]
        print(f"⏰ 服务器时间: {server_time}")

        # 2. 查询指定表的结构
        tables_to_query = [
            'CASE_ITEMS', 'CaseItem_Matches', 'CaseItemRecs',
            'CASES', 'ITEMS_ASSIGN', 'Items_Recs', 'ManagerVerify_Recs'
        ]

        query_structure = f"""
        SELECT
            t.name AS 表名,
            c.name AS 列名,
            ty.name AS 数据类型,
            c.max_length,
            CASE WHEN c.is_nullable=1 THEN '是' ELSE '否' END AS 可空性
        FROM
            sys.tables t
        JOIN
            sys.columns c ON t.object_id = c.object_id
        JOIN
            sys.types ty ON c.system_type_id = ty.system_type_id
        WHERE
            t.type = 'U'
            AND t.name IN ({','.join([f"'{table}'" for table in tables_to_query])})
        ORDER BY
            t.name, c.column_id;
        """

        cursor.execute(query_structure)
        columns = [col[0] for col in cursor.description]
        print("\n📋 表结构信息:")
        print("-" * 80)

        # 打印标题行
        header = f"{'表名':<12} | {'列名':<25} | {'数据类型':<15} | {'长度/精度':<10} | {'可空性':<6}"
        print(header)
        print("-" * 80)

        # 打印数据行
        for row in cursor.fetchall():
            print(f"{row[0]:<12} | {row[1]:<25} | {row[2]:<15} |"
                  f"{str(row[3]):<10} | {row[4]:<6}")

        print("-" * 80)
        print(f"\n共查询到 {len(tables_to_query)} 个表，{cursor.rowcount} 列")

except pyodbc.Error as e:
    print(f"\n❌ 错误: {str(e)}\n")
except Exception as e:
    print(f"\n其他错误: {str(e)}\n")
finally:
    if 'conn' in locals():
        conn.close()