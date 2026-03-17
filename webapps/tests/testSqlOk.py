# import pyodbc
# from langchain_ollama import OllamaEmbeddings

# try:
#     conn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=mssql1.mpc.mil.tw\mpcsqlserver;DATABASE=CaseManager;UID=sa;PWD=Aa123456")
#     print("Connection successful!")
# except Exception as e:
#     print(f"Connection failed: {e}")

# webapps/tests/test_db_connection.py

# In your_app/tests/test_db_connection.py
from django.test import TestCase
from webapps.database.db_factoryold import db_connect

class DBConnectionTest(TestCase):
    def test_sqlserver_connection(self):
        try:
            conn = db_connect()
            # Test simple query
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
            conn.close()
            print("\n✅ SQL Server connection test passed successfully!")
        except Exception as e:
            self.fail(f"SQL Server connection failed: {str(e)}")