import sqlite3
import os

db_path = "db.sqlite3"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, title, file_path FROM videolearning_asset WHERE id=18")
    row = cur.fetchone()
    if row:
        print(f"ID: {row[0]}")
        print(f"Title: {row[1]}")
        print(f"File Path: {row[2]}")
    else:
        print("Video ID 18 not found.")
    conn.close()
else:
    print("db.sqlite3 not found.")
