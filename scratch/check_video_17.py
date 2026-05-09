import sqlite3
import json

db_path = "db.sqlite3"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT * FROM videolearning_asset WHERE id=17")
row = cur.fetchone()
if row:
    # Get column names
    cols = [d[0] for d in cur.description]
    data = dict(zip(cols, row))
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print("Video 17 not found.")
conn.close()
