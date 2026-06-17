import sqlite3
from pathlib import Path

path = Path("chroma 1.sqlite3")
if not path.exists():
    print("chroma 1.sqlite3 not found!")
    exit(1)

conn = sqlite3.connect(str(path))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

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

print("=== Checking CP950 decoding for Chroma Documentation ===")
for row_id, meta in grouped.items():
    doc_text = meta.get("chroma:document", "")
    topic = meta.get("Topic", "")
    
    # 嘗試用 cp950 或 raw-unicode-escape / latin1 還原
    # 由於 sqlite3 text 欄位在讀取時，Python 會預設用 utf-8 解碼。
    # 如果寫入時是 Big5/CP950 的 byte，但以 text 存入，
    # sqlite3 或 python 讀出來會是 unicode 替換字元或亂碼。
    # 我們需要把 python string 先用 encode('latin1' 或 'raw_unicode_escape') 轉回 bytes，
    # 再用 cp950 decode。
    try:
        # 很多時候 python 讀取 sqlite text 時如果編碼錯了，會用 utf-8 解碼，
        # 如果有錯會變成帶有 \ufffd 的字串。
        # 我們直接把字串編碼回 bytes，如果是 CP950 以 UTF-8 解碼，
        # 常見手法是 string.encode('utf-8')，但如果 utf-8 出錯，可能某些字節丟失了。
        # 讓我們試試幾種不同的還原方式。
        raw_bytes = doc_text.encode('utf-8')
        # 如果原本是 cp950 bytes 被 sqlite/python 錯誤當成 utf-8 text 讀取，
        # 我們可以用 'raw_unicode_escape' 或是將 text 轉為 bytes 再用 cp950 decode。
        # 不過在 sqlite3 中，若是 text 類型，我們可以嘗試在 select 時使用 CAST(string_value AS BLOB)！
        pass
    except Exception:
        pass

# 我們使用 CAST(string_value AS BLOB) 讀取原始 binary bytes！
cur.execute(
    """
    SELECT
      e.id AS row_id,
      CAST(m.string_value AS BLOB) AS raw_val,
      m.key
    FROM embeddings e
    JOIN segments s ON s.id = e.segment_id
    JOIN collections c ON c.id = s.collection
    LEFT JOIN embedding_metadata m ON m.id = e.id
    WHERE c.name = 'documentation' AND s.scope = 'METADATA' AND m.key = 'chroma:document'
    ORDER BY e.id
    """
)

for r in cur.fetchall():
    row_id = r["row_id"]
    raw_val = r["raw_val"]
    if not raw_val:
        continue
    
    # 嘗試以 cp950 / big5 / utf-8 解碼
    decoded = None
    for enc in ('cp950', 'big5', 'utf-8', 'gbk'):
        try:
            decoded = raw_val.decode(enc)
            print(f"Row ID: {row_id} (Encoding: {enc})")
            print(f"Content: {decoded[:150]}")
            print("-" * 30)
            break
        except Exception:
            pass
    if not decoded:
        print(f"Row ID: {row_id} failed to decode with any encoding. Raw: {raw_val[:50]}")

conn.close()
