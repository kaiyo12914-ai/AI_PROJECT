import os
import pyodbc
from dotenv import load_dotenv

class connectionFactory():

    def __init__(self) -> None:
        # 加载 .env 文件
        load_dotenv()

    def CreateMSSqlConnection(self):
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
            return conn
        except pyodbc.Error as e:
            print(f"\n❌ 错误: {str(e)}\n")
        except Exception as e:
            print(f"\n其他错误: {str(e)}\n")