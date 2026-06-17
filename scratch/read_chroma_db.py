import sqlite3
from pathlib import Path

path = Path("chroma 1.sqlite3")
if not path.exists():
    print("chroma 1.sqlite3 not found!")
    exit(1)

conn = sqlite3.connect(str(path))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 查詢 collections 列表
cur.execute("SELECT id, name FROM collections")
for c in cur.fetchall():
    print(f"Collection ID: {c['id']}, Name: {c['name']}")

# 讀取 documentation 相關的 metadata
cur.execute(
    """
    SELECT
      e.id AS row_id,
      e.embedding_id,
      m.key,
      m.string_value
    FROM embeddings e
    JOIN segments s ON s.id = e.segment_id
    JOIN collections c ON c.id = s.collection
    LEFT JOIN embedding_metadata m ON m.id = e.id
    WHERE c.name = 'documentation' AND s.scope = 'METADATA'
    ORDER BY e.id, m.key
    """
)

rows = cur.fetchall()
grouped = {}
for r in rows:
    grouped.setdefault(r["row_id"], {})[r["key"]] = r["string_value"]

print(f"\nTotal documentation records in Chroma: {len(grouped)}")

# 列出前 10 筆
for row_id, meta in list(grouped.items())[:15]:
    doc_text = meta.get("chroma:document", "")
    topic = meta.get("Topic", "")
    print(f"Row ID: {row_id}")
    print(f"  Topic: {topic}")
    print(f"  Text (first 100 chars): {doc_text[:100]}")
    # 嘗試以 utf-8 或 cp950 解碼看是否有亂碼
    try:
        raw_bytes = doc_text.encode('utf-8')
        print(f"  UTF-8 decoded ok: {raw_bytes[:30].decode('utf-8')}")
    except Exception as e:
        print(f"  UTF-8 decode failed: {e}")
    print()

conn.close()
