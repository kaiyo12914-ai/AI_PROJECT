import os
import django
from django.conf import settings
from pathlib import Path
import sqlite3

def check_sqlite_raw(db_path):
    print(f"\n--- Checking SQLite Raw: {db_path} ---")
    if not os.path.exists(db_path):
        print("File does not exist.")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables: {[t[0] for t in tables]}")
        
        # 嘗試讀取 collections
        if ('collections',) in tables:
            cursor.execute("SELECT name FROM collections;")
            cols = cursor.fetchall()
            print(f"Collections: {[c[0] for c in cols]}")
            
        conn.close()
    except Exception as e:
        print(f"SQLite Error: {e}")

if __name__ == "__main__":
    check_sqlite_raw("H:\\AI\\Django\\chroma\\chroma.sqlite3")
    check_sqlite_raw("H:\\AI\\Django\\chroma\\rag\\chroma.sqlite3")
