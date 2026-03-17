# sync_sqlserver_to_chroma.py
from __future__ import annotations

import os
import sys
import json
import time
import argparse
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Iterable, Tuple

import pyodbc
import chromadb
from chromadb.config import Settings

# LangChain Ollama Embeddings (recommended package)
# pip install -U langchain langchain-ollama
from langchain_ollama import OllamaEmbeddings


def env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return v if v is not None and v != "" else default


def as_iso(v: Any) -> Any:
    """Convert datetime/date to isoformat for metadata JSON serializability."""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return v


def safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return as_iso(v)
    return str(v)


def rows_to_dicts(cursor: pyodbc.Cursor, rows: List[pyodbc.Row]) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = {}
        for i, c in enumerate(cols):
            d[c] = r[i]
        out.append(d)
    return out


def build_doc_id(row: Dict[str, Any], id_cols: List[str], fallback_prefix: str, fallback_seq: int) -> str:
    if id_cols:
        parts = []
        for c in id_cols:
            parts.append(safe_str(row.get(c)))
        joined = "|".join(parts).strip("|")
        if joined:
            return joined
    return f"{fallback_prefix}:{fallback_seq}"


def build_text(row: Dict[str, Any], text_cols: List[str], max_chars: int) -> str:
    """
    Build embedding text from selected columns; truncate to max_chars to reduce Ollama failure risk.
    """
    if text_cols:
        parts = []
        for c in text_cols:
            parts.append(f"{c}: {safe_str(row.get(c))}")
        text = "\n".join(parts)
    else:
        # fallback: include all columns
        text = json.dumps({k: as_iso(v) for k, v in row.items()}, ensure_ascii=False)

    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
    return text


def build_meta(row: Dict[str, Any], meta_cols: List[str], extra_meta: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if meta_cols:
        for c in meta_cols:
            meta[c] = as_iso(row.get(c))
    else:
        # fallback: light meta (avoid huge strings in metadata)
        for k, v in row.items():
            if isinstance(v, (int, float, bool, datetime, date)) or v is None:
                meta[k] = as_iso(v)

    # add extra meta (e.g. table name)
    for k, v in extra_meta.items():
        meta[k] = as_iso(v)

    # Ensure all metadata values are JSON-serializable primitives/strings
    for k, v in list(meta.items()):
        if isinstance(v, (dict, list, tuple)):
            meta[k] = json.dumps(v, ensure_ascii=False)
        elif v is None:
            # Chroma allows None in meta? safer to convert to empty string
            meta[k] = ""
        else:
            meta[k] = as_iso(v)
    return meta


def langchain_embed(
    texts: List[str],
    base_url: str,
    model: str,
    timeout_sec: int = 180,
    batch_size: int = 32,
    max_retries: int = 4,
) -> List[List[float]]:
    """
    Embed texts via LangChain OllamaEmbeddings with:
      - retry + exponential backoff
      - adaptive batch splitting when server errors happen (often OOM / overload)
    """
    emb = OllamaEmbeddings(
        model=model,
        base_url=base_url.rstrip("/"),
        timeout=timeout_sec,
    )

    vectors: List[List[float]] = []
    i = 0

    while i < len(texts):
        cur_batch = texts[i : i + batch_size]

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                vecs = emb.embed_documents(cur_batch)
                if len(vecs) != len(cur_batch):
                    raise RuntimeError(f"Embedding count mismatch: got {len(vecs)} expected {len(cur_batch)}")
                vectors.extend(vecs)
                last_err = None
                break
            except Exception as e:
                last_err = e
                sleep_s = min(2 ** attempt, 12)
                print(
                    f"[WARN] embed failed attempt={attempt+1}/{max_retries+1} "
                    f"batch={len(cur_batch)} err={e} -> sleep {sleep_s}s"
                )
                time.sleep(sleep_s)

                # If last attempt and batch > 1, shrink batch size and retry same index
                if attempt == max_retries and batch_size > 1:
                    new_bs = max(1, batch_size // 2)
                    if new_bs == batch_size:
                        new_bs = max(1, batch_size - 1)
                    batch_size = new_bs
                    print(f"[WARN] reduce embed batch_size -> {batch_size} (retry same index)")
                    break

        if last_err is not None and batch_size == 1:
            preview = (cur_batch[0] or "")[:160].replace("\n", " ")
            raise RuntimeError(f"Ollama embedding failed even for single item. preview='{preview}'") from last_err

        if last_err is None:
            i += len(cur_batch)

    return vectors


class ChromaIndex:
    def __init__(self, persist_dir: str, collection: str):
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(name=collection)

    def upsert(self, ids: List[str], texts: List[str], metas: List[Dict[str, Any]], embeddings: List[List[float]]) -> None:
        self.col.upsert(
            ids=ids,
            documents=texts,
            metadatas=metas,
            embeddings=embeddings,
        )


def connect_sqlserver(conn_str: str) -> pyodbc.Connection:
    # You can include: "TrustServerCertificate=yes;" if needed for TLS
    return pyodbc.connect(conn_str, autocommit=False)


def iter_rows(cursor: pyodbc.Cursor, fetch_size: int) -> Iterable[List[pyodbc.Row]]:
    while True:
        rows = cursor.fetchmany(fetch_size)
        if not rows:
            break
        yield rows


def parse_csv_list(v: str) -> List[str]:
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync SQL Server rows to ChromaDB with LangChain Ollama embeddings")

    # SQL source
    ap.add_argument("--conn", default=env("SQLSERVER_CONN_STR", ""), help="pyodbc connection string (or env SQLSERVER_CONN_STR)")
    ap.add_argument("--query", default="", help="SQL query to fetch rows. If not set, use --table and cols.")
    ap.add_argument("--table", default="", help="Table name if --query not provided")
    ap.add_argument("--where", default="", help="Optional WHERE clause (without the word WHERE)")
    ap.add_argument("--order-by", default="", help="Optional ORDER BY clause (without the words ORDER BY)")

    ap.add_argument("--id-cols", default=env("ID_COLS", ""), help="Comma-separated columns to build document id")
    ap.add_argument("--text-cols", default=env("TEXT_COLS", ""), help="Comma-separated columns to build embedding text (default: all)")
    ap.add_argument("--meta-cols", default=env("META_COLS", ""), help="Comma-separated columns to store in metadata (default: numeric/datetime only)")

    # Chroma
    ap.add_argument("--persist-dir", default=env("CHROMA_DIR", "./chroma_db"), help="Chroma persist directory")
    ap.add_argument("--collection", default=env("CHROMA_COLLECTION", "sqlserver_docs"), help="Chroma collection name")

    # Embeddings (Ollama)
    ap.add_argument("--ollama-url", default=env("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434"), help="Ollama base URL")
    ap.add_argument("--embed-model", default=env("OLLAMA_EMBED_MODEL", "nomic-embed-text"), help="Ollama embedding model name")
    ap.add_argument("--embed-timeout", type=int, default=int(env("OLLAMA_TIMEOUT_SEC", "180")), help="Embedding request timeout seconds")
    ap.add_argument("--embed-batch", type=int, default=int(env("OLLAMA_EMBED_BATCH", "32")), help="Embedding batch size (adaptive shrink on failures)")
    ap.add_argument("--embed-retry", type=int, default=int(env("OLLAMA_RETRY", "4")), help="Retries per embedding batch")

    # Pipeline
    ap.add_argument("--fetch-size", type=int, default=500, help="DB fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=200, help="Chroma upsert batch (also drives embedding calls)")
    ap.add_argument("--limit", type=int, default=0, help="Limit total rows (0 = no limit)")
    ap.add_argument("--text-max-chars", type=int, default=int(env("TEXT_MAX_CHARS", "2000")), help="Truncate embedding text to this length (0=disable)")
    ap.add_argument("--skip-bad", action="store_true", help="Skip rows that still fail after retries; log to bad_rows.jsonl")

    args = ap.parse_args()

    if not args.conn:
        print("[ERROR] Missing --conn or env SQLSERVER_CONN_STR")
        return 2

    id_cols = parse_csv_list(args.id_cols)
    text_cols = parse_csv_list(args.text_cols)
    meta_cols = parse_csv_list(args.meta_cols)

    if not args.query:
        if not args.table:
            print("[ERROR] Provide --query or --table")
            return 2
        cols = "*"
        # If user specified text/meta/id cols, we should at least include them (avoid missing fields)
        wanted = sorted(set(id_cols + text_cols + meta_cols))
        if wanted:
            cols = ", ".join(f"[{c}]" for c in wanted)
        sql = f"SELECT {cols} FROM {args.table}"
        if args.where:
            sql += f" WHERE {args.where}"
        if args.order_by:
            sql += f" ORDER BY {args.order_by}"
        args.query = sql

    print("[INFO] SQL query:")
    print(args.query)

    idx = ChromaIndex(args.persist_dir, args.collection)
    bad_path = os.path.join(args.persist_dir, "bad_rows.jsonl")

    conn = connect_sqlserver(args.conn)
    try:
        cur = conn.cursor()
        cur.execute(args.query)

        total = 0
        seq = 0

        batch_ids: List[str] = []
        batch_texts: List[str] = []
        batch_metas: List[Dict[str, Any]] = []

        def flush() -> None:
            nonlocal batch_ids, batch_texts, batch_metas

            if not batch_ids:
                return

            # Embeddings via LangChain Ollama
            try:
                embs = langchain_embed(
                    texts=batch_texts,
                    base_url=args.ollama_url,
                    model=args.embed_model,
                    timeout_sec=args.embed_timeout,
                    batch_size=args.embed_batch,
                    max_retries=args.embed_retry,
                )
                idx.upsert(batch_ids, batch_texts, batch_metas, embs)
                print(f"[INFO] upserted {len(batch_ids)} docs")
            except Exception as e:
                print(f"[ERROR] embedding/upsert failed for batch size={len(batch_ids)} err={e}")
                if not args.skip_bad:
                    raise
                # Skip bad: write each row to bad_rows.jsonl for later replay
                with open(bad_path, "a", encoding="utf-8") as f:
                    for _id, _txt, _meta in zip(batch_ids, batch_texts, batch_metas):
                        f.write(json.dumps({"id": _id, "meta": _meta, "text_preview": _txt[:240]}, ensure_ascii=False) + "\n")
                print(f"[WARN] batch skipped; logged to {bad_path}")

            batch_ids = []
            batch_texts = []
            batch_metas = []

        for rows in iter_rows(cur, args.fetch_size):
            dicts = rows_to_dicts(cur, rows)
            for row in dicts:
                seq += 1
                doc_id = build_doc_id(
                    row=row,
                    id_cols=id_cols,
                    fallback_prefix=args.table or "query",
                    fallback_seq=seq,
                )
                text = build_text(row=row, text_cols=text_cols, max_chars=args.text_max_chars)
                meta = build_meta(
                    row=row,
                    meta_cols=meta_cols,
                    extra_meta={"source": "sqlserver", "table": args.table or ""},
                )

                batch_ids.append(doc_id)
                batch_texts.append(text)
                batch_metas.append(meta)

                total += 1
                if args.limit and total >= args.limit:
                    flush()
                    print(f"[INFO] reached limit={args.limit}")
                    conn.commit()
                    return 0

                if len(batch_ids) >= args.upsert_batch:
                    flush()

        flush()
        conn.commit()
        print(f"[INFO] done. total={total}")
        return 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
下面是一份**完整可直接貼上**、可運作的 `sync_sqlserver_to_chroma.py` 範本：

* **SQL Server → ChromaDB**
* **Embedding 改用 LangChain (`langchain-ollama` 的 `OllamaEmbeddings`)**
* 內建 **retry / backoff / 動態縮小 batch / 單筆失敗可略過並記錄**
* 支援用 `--query` 或 `--table + --text-cols` 方式抓資料
* 你可以直接把它當成「新版本整支檔案」替換掉原本的腳本使用（因為你上傳的檔案內容中間是 `...` 省略，無法 1:1 patch，但下面這支會把你要的功能完整補齊並更穩）

---

## ✅ 完整檔案：sync_sqlserver_to_chroma.py（可直接貼上）

```python
# sync_sqlserver_to_chroma.py
from __future__ import annotations

import os
import sys
import json
import time
import argparse
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Iterable, Tuple

import pyodbc
import chromadb
from chromadb.config import Settings

# LangChain Ollama Embeddings (recommended package)
# pip install -U langchain langchain-ollama
from langchain_ollama import OllamaEmbeddings


def env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return v if v is not None and v != "" else default


def as_iso(v: Any) -> Any:
    """Convert datetime/date to isoformat for metadata JSON serializability."""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return v


def safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return as_iso(v)
    return str(v)


def rows_to_dicts(cursor: pyodbc.Cursor, rows: List[pyodbc.Row]) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = {}
        for i, c in enumerate(cols):
            d[c] = r[i]
        out.append(d)
    return out


def build_doc_id(row: Dict[str, Any], id_cols: List[str], fallback_prefix: str, fallback_seq: int) -> str:
    if id_cols:
        parts = []
        for c in id_cols:
            parts.append(safe_str(row.get(c)))
        joined = "|".join(parts).strip("|")
        if joined:
            return joined
    return f"{fallback_prefix}:{fallback_seq}"


def build_text(row: Dict[str, Any], text_cols: List[str], max_chars: int) -> str:
    """
    Build embedding text from selected columns; truncate to max_chars to reduce Ollama failure risk.
    """
    if text_cols:
        parts = []
        for c in text_cols:
            parts.append(f"{c}: {safe_str(row.get(c))}")
        text = "\n".join(parts)
    else:
        # fallback: include all columns
        text = json.dumps({k: as_iso(v) for k, v in row.items()}, ensure_ascii=False)

    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
    return text


def build_meta(row: Dict[str, Any], meta_cols: List[str], extra_meta: Dict[str, Any]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if meta_cols:
        for c in meta_cols:
            meta[c] = as_iso(row.get(c))
    else:
        # fallback: light meta (avoid huge strings in metadata)
        for k, v in row.items():
            if isinstance(v, (int, float, bool, datetime, date)) or v is None:
                meta[k] = as_iso(v)

    # add extra meta (e.g. table name)
    for k, v in extra_meta.items():
        meta[k] = as_iso(v)

    # Ensure all metadata values are JSON-serializable primitives/strings
    for k, v in list(meta.items()):
        if isinstance(v, (dict, list, tuple)):
            meta[k] = json.dumps(v, ensure_ascii=False)
        elif v is None:
            # Chroma allows None in meta? safer to convert to empty string
            meta[k] = ""
        else:
            meta[k] = as_iso(v)
    return meta


def langchain_embed(
    texts: List[str],
    base_url: str,
    model: str,
    timeout_sec: int = 180,
    batch_size: int = 32,
    max_retries: int = 4,
) -> List[List[float]]:
    """
    Embed texts via LangChain OllamaEmbeddings with:
      - retry + exponential backoff
      - adaptive batch splitting when server errors happen (often OOM / overload)
    """
    emb = OllamaEmbeddings(
        model=model,
        base_url=base_url.rstrip("/"),
        timeout=timeout_sec,
    )

    vectors: List[List[float]] = []
    i = 0

    while i < len(texts):
        cur_batch = texts[i : i + batch_size]

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                vecs = emb.embed_documents(cur_batch)
                if len(vecs) != len(cur_batch):
                    raise RuntimeError(f"Embedding count mismatch: got {len(vecs)} expected {len(cur_batch)}")
                vectors.extend(vecs)
                last_err = None
                break
            except Exception as e:
                last_err = e
                sleep_s = min(2 ** attempt, 12)
                print(
                    f"[WARN] embed failed attempt={attempt+1}/{max_retries+1} "
                    f"batch={len(cur_batch)} err={e} -> sleep {sleep_s}s"
                )
                time.sleep(sleep_s)

                # If last attempt and batch > 1, shrink batch size and retry same index
                if attempt == max_retries and batch_size > 1:
                    new_bs = max(1, batch_size // 2)
                    if new_bs == batch_size:
                        new_bs = max(1, batch_size - 1)
                    batch_size = new_bs
                    print(f"[WARN] reduce embed batch_size -> {batch_size} (retry same index)")
                    break

        if last_err is not None and batch_size == 1:
            preview = (cur_batch[0] or "")[:160].replace("\n", " ")
            raise RuntimeError(f"Ollama embedding failed even for single item. preview='{preview}'") from last_err

        if last_err is None:
            i += len(cur_batch)

    return vectors


class ChromaIndex:
    def __init__(self, persist_dir: str, collection: str):
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(name=collection)

    def upsert(self, ids: List[str], texts: List[str], metas: List[Dict[str, Any]], embeddings: List[List[float]]) -> None:
        self.col.upsert(
            ids=ids,
            documents=texts,
            metadatas=metas,
            embeddings=embeddings,
        )


def connect_sqlserver(conn_str: str) -> pyodbc.Connection:
    # You can include: "TrustServerCertificate=yes;" if needed for TLS
    return pyodbc.connect(conn_str, autocommit=False)


def iter_rows(cursor: pyodbc.Cursor, fetch_size: int) -> Iterable[List[pyodbc.Row]]:
    while True:
        rows = cursor.fetchmany(fetch_size)
        if not rows:
            break
        yield rows


def parse_csv_list(v: str) -> List[str]:
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync SQL Server rows to ChromaDB with LangChain Ollama embeddings")

    # SQL source
    ap.add_argument("--conn", default=env("SQLSERVER_CONN_STR", ""), help="pyodbc connection string (or env SQLSERVER_CONN_STR)")
    ap.add_argument("--query", default="", help="SQL query to fetch rows. If not set, use --table and cols.")
    ap.add_argument("--table", default="", help="Table name if --query not provided")
    ap.add_argument("--where", default="", help="Optional WHERE clause (without the word WHERE)")
    ap.add_argument("--order-by", default="", help="Optional ORDER BY clause (without the words ORDER BY)")

    ap.add_argument("--id-cols", default=env("ID_COLS", ""), help="Comma-separated columns to build document id")
    ap.add_argument("--text-cols", default=env("TEXT_COLS", ""), help="Comma-separated columns to build embedding text (default: all)")
    ap.add_argument("--meta-cols", default=env("META_COLS", ""), help="Comma-separated columns to store in metadata (default: numeric/datetime only)")

    # Chroma
    ap.add_argument("--persist-dir", default=env("CHROMA_DIR", "./chroma_db"), help="Chroma persist directory")
    ap.add_argument("--collection", default=env("CHROMA_COLLECTION", "sqlserver_docs"), help="Chroma collection name")

    # Embeddings (Ollama)
    ap.add_argument("--ollama-url", default=env("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434"), help="Ollama base URL")
    ap.add_argument("--embed-model", default=env("OLLAMA_EMBED_MODEL", "nomic-embed-text"), help="Ollama embedding model name")
    ap.add_argument("--embed-timeout", type=int, default=int(env("OLLAMA_TIMEOUT_SEC", "180")), help="Embedding request timeout seconds")
    ap.add_argument("--embed-batch", type=int, default=int(env("OLLAMA_EMBED_BATCH", "32")), help="Embedding batch size (adaptive shrink on failures)")
    ap.add_argument("--embed-retry", type=int, default=int(env("OLLAMA_RETRY", "4")), help="Retries per embedding batch")

    # Pipeline
    ap.add_argument("--fetch-size", type=int, default=500, help="DB fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=200, help="Chroma upsert batch (also drives embedding calls)")
    ap.add_argument("--limit", type=int, default=0, help="Limit total rows (0 = no limit)")
    ap.add_argument("--text-max-chars", type=int, default=int(env("TEXT_MAX_CHARS", "2000")), help="Truncate embedding text to this length (0=disable)")
    ap.add_argument("--skip-bad", action="store_true", help="Skip rows that still fail after retries; log to bad_rows.jsonl")

    args = ap.parse_args()

    if not args.conn:
        print("[ERROR] Missing --conn or env SQLSERVER_CONN_STR")
        return 2

    id_cols = parse_csv_list(args.id_cols)
    text_cols = parse_csv_list(args.text_cols)
    meta_cols = parse_csv_list(args.meta_cols)

    if not args.query:
        if not args.table:
            print("[ERROR] Provide --query or --table")
            return 2
        cols = "*"
        # If user specified text/meta/id cols, we should at least include them (avoid missing fields)
        wanted = sorted(set(id_cols + text_cols + meta_cols))
        if wanted:
            cols = ", ".join(f"[{c}]" for c in wanted)
        sql = f"SELECT {cols} FROM {args.table}"
        if args.where:
            sql += f" WHERE {args.where}"
        if args.order_by:
            sql += f" ORDER BY {args.order_by}"
        args.query = sql

    print("[INFO] SQL query:")
    print(args.query)

    idx = ChromaIndex(args.persist_dir, args.collection)
    bad_path = os.path.join(args.persist_dir, "bad_rows.jsonl")

    conn = connect_sqlserver(args.conn)
    try:
        cur = conn.cursor()
        cur.execute(args.query)

        total = 0
        seq = 0

        batch_ids: List[str] = []
        batch_texts: List[str] = []
        batch_metas: List[Dict[str, Any]] = []

        def flush() -> None:
            nonlocal batch_ids, batch_texts, batch_metas

            if not batch_ids:
                return

            # Embeddings via LangChain Ollama
            try:
                embs = langchain_embed(
                    texts=batch_texts,
                    base_url=args.ollama_url,
                    model=args.embed_model,
                    timeout_sec=args.embed_timeout,
                    batch_size=args.embed_batch,
                    max_retries=args.embed_retry,
                )
                idx.upsert(batch_ids, batch_texts, batch_metas, embs)
                print(f"[INFO] upserted {len(batch_ids)} docs")
            except Exception as e:
                print(f"[ERROR] embedding/upsert failed for batch size={len(batch_ids)} err={e}")
                if not args.skip_bad:
                    raise
                # Skip bad: write each row to bad_rows.jsonl for later replay
                with open(bad_path, "a", encoding="utf-8") as f:
                    for _id, _txt, _meta in zip(batch_ids, batch_texts, batch_metas):
                        f.write(json.dumps({"id": _id, "meta": _meta, "text_preview": _txt[:240]}, ensure_ascii=False) + "\n")
                print(f"[WARN] batch skipped; logged to {bad_path}")

            batch_ids = []
            batch_texts = []
            batch_metas = []

        for rows in iter_rows(cur, args.fetch_size):
            dicts = rows_to_dicts(cur, rows)
            for row in dicts:
                seq += 1
                doc_id = build_doc_id(
                    row=row,
                    id_cols=id_cols,
                    fallback_prefix=args.table or "query",
                    fallback_seq=seq,
                )
                text = build_text(row=row, text_cols=text_cols, max_chars=args.text_max_chars)
                meta = build_meta(
                    row=row,
                    meta_cols=meta_cols,
                    extra_meta={"source": "sqlserver", "table": args.table or ""},
                )

                batch_ids.append(doc_id)
                batch_texts.append(text)
                batch_metas.append(meta)

                total += 1
                if args.limit and total >= args.limit:
                    flush()
                    print(f"[INFO] reached limit={args.limit}")
                    conn.commit()
                    return 0

                if len(batch_ids) >= args.upsert_batch:
                    flush()

        flush()
        conn.commit()
        print(f"[INFO] done. total={total}")
        return 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## ✅ 安裝與前置

```bash
pip install -U pyodbc chromadb langchain langchain-ollama
```

---

## ✅ 使用範例（PowerShell / Windows）

### A) 用 `--query`（最彈性）

```powershell
$env:SQLSERVER_CONN_STR="DRIVER={ODBC Driver 17 for SQL Server};SERVER=YOURSERVER;DATABASE=YOURDB;UID=USER;PWD=PASS;TrustServerCertificate=yes;"
$env:OLLAMA_BASE_URL="http://mpcai.mpc.mil.tw:11434"
$env:OLLAMA_EMBED_MODEL="nomic-embed-text"

python .\sync_sqlserver_to_chroma.py `
  --query "SELECT Id, Title, Body, UpdatedAt FROM dbo.KnowledgeBase WHERE Body IS NOT NULL ORDER BY UpdatedAt DESC" `
  --id-cols "Id" `
  --text-cols "Title,Body" `
  --meta-cols "Id,UpdatedAt" `
  --persist-dir "D:\chroma_db" `
  --collection "kb_docs" `
  --upsert-batch 200 `
  --embed-batch 16 `
  --embed-timeout 180 `
  --embed-retry 4
```

### B) 用 `--table`（快速）

```powershell
python .\sync_sqlserver_to_chroma.py `
  --table "dbo.KnowledgeBase" `
  --where "Body IS NOT NULL" `
  --order-by "UpdatedAt DESC" `
  --id-cols "Id" `
  --text-cols "Title,Body" `
  --meta-cols "Id,UpdatedAt" `
  --persist-dir "D:\chroma_db" `
  --collection "kb_docs"
```

---

## ✅ 針對你遇到的 500：我建議你先這樣跑（更穩）

通常 500 多半是 Ollama 端壓力/記憶體或文本太長導致，先保守一點：

```powershell
python .\sync_sqlserver_to_chroma.py `
  --table "dbo.KnowledgeBase" `
  --where "Body IS NOT NULL" `
  --id-cols "Id" `
  --text-cols "Title,Body" `
  --meta-cols "Id,UpdatedAt" `
  --persist-dir "D:\chroma_db" `
  --collection "kb_docs" `
  --upsert-batch 50 `
  --embed-batch 8 `
  --text-max-chars 1500 `
  --skip-bad
```

* `--skip-bad` 會把仍失敗的資料寫到 `D:\chroma_db\bad_rows.jsonl`，讓你後續針對失敗的資料再補跑/檢查內容。

---

如果你把你實際的 SQL 表格欄位（或你原本 query）貼一下（不用機敏資料，欄位名就好），我也可以幫你把 `--text-cols` / `--meta-cols` 的最佳組合與 `--where` 條件（例如排除超長欄位、HTML 清理）一起調到最穩。
好，我直接把你目前的 `webapps/database/sync_sqlserver_to_chroma.py`（你現有那支：用 `requests` 打 `/api/embeddings`、`text_for_embed = body[:4000]`、`upsert_batch` 預設 200）調到「**最穩**」：改成 **LangChain `OllamaEmbeddings`** + **保守批次** + **自動縮批** + **重試退避** + **單筆失敗可跳過並記錄** + **更保守的 text 長度**。你目前程式碼內容我已參照你提供的檔案片段（含 Chroma 路徑、view 欄位、doc_id 規則等）。

---

## 我幫你調成「最穩」的策略（你不用再猜參數）

針對你之前遇到的 Ollama `500 Internal Server Error`，實務上最有效的穩定組合是：

* **embedding text 限長：1500 字元**（你原本 4000 太容易觸發 OOM/ctx 壓力）
* **embed batch：8**（必要時自動降到 4/2/1）
* **upsert batch：50**（不要一次堆 200 筆去 embed）
* **timeout：240 秒**
* **retry：5 次，指數退避**
* **skip-bad：開啟**（失敗那幾筆寫到檔案，整批不中斷）

---

## ✅ 直接貼上版（完整檔案）：sync_sqlserver_to_chroma.py（最穩版）

> 你可以整支覆蓋原本的 `D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py`
> 仍沿用你原本的 `connectionFactory()`、view 欄位、doc_id、last_sync 機制。

```python
# sync_sqlserver_to_chroma.py (MOST STABLE VERSION)
from __future__ import annotations

import os
import json
import time
import argparse
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import pyodbc
import chromadb
from chromadb.config import Settings

from webapps.database.connectionFactory import connectionFactory

# ✅ LangChain embeddings for Ollama
# pip install -U langchain langchain-ollama
from langchain_ollama import OllamaEmbeddings

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


# ============================================================
# Helpers
# ============================================================
def env(k: str, d: str = "") -> str:
    return (os.getenv(k) or d).strip()


def env_int(k: str, d: int) -> int:
    try:
        return int(env(k, str(d)))
    except Exception:
        return d


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rows_to_dicts(cursor: pyodbc.Cursor, rows: list) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    out: List[Dict[str, Any]] = []
    for r in rows:
        d: Dict[str, Any] = {}
        for i, k in enumerate(cols):
            d[k] = r[i]
        out.append(d)
    return out


def validate_since_ymd(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"--since 格式必須為 YYYY-MM-DD，例如 2025-01-03；收到：{s}") from e


def to_ymd(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, datetime):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, date):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip()
    if not s:
        return ""
    if len(s) >= 10:
        s10 = s[:10]
        try:
            return validate_since_ymd(s10)
        except Exception:
            return ""
    return ""


def coalesce_dt(a: Any, b: Any) -> Any:
    return a if a not in (None, "") else b


def parse_debug_one(s: str) -> Tuple[str, str]:
    s = (s or "").strip()
    if not s:
        return "", ""
    if not s.startswith("cmqna_"):
        return "", ""
    parts = s.split("_", 2)
    if len(parts) != 3:
        return "", ""
    return parts[1].strip(), parts[2].strip()


def pick_field(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def normalize_text(s: str) -> str:
    """
    最保守的清理：去掉多餘空白、NUL
    （不做 HTML strip，避免誤傷內容；需要再加）
    """
    if not s:
        return ""
    s = s.replace("\x00", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # 壓縮過多空行
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    return s.strip()


# ============================================================
# Embeddings: LangChain OllamaEmbeddings (MOST STABLE)
# ============================================================
def langchain_ollama_embed(
    texts: List[str],
    *,
    base_url: str,
    model: str,
    timeout_sec: int,
    batch_size: int,
    max_retries: int,
) -> List[List[float]]:
    """
    embed_documents with:
      - retry + exponential backoff
      - adaptive batch shrinking: 8 -> 4 -> 2 -> 1
    """
    emb = OllamaEmbeddings(
        model=model,
        base_url=base_url.rstrip("/"),
        timeout=timeout_sec,
    )

    vectors: List[List[float]] = []
    i = 0

    while i < len(texts):
        cur = texts[i : i + batch_size]

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                vecs = emb.embed_documents(cur)
                if len(vecs) != len(cur):
                    raise RuntimeError(f"Embedding count mismatch: got {len(vecs)} expected {len(cur)}")
                vectors.extend(vecs)
                last_err = None
                break
            except Exception as e:
                last_err = e
                sleep_s = min(2 ** attempt, 12)
                print(f"[WARN] embed failed attempt={attempt+1}/{max_retries+1} batch={len(cur)} err={e} -> sleep {sleep_s}s")
                time.sleep(sleep_s)

                if attempt == max_retries and batch_size > 1:
                    new_bs = max(1, batch_size // 2)
                    if new_bs == batch_size:
                        new_bs = max(1, batch_size - 1)
                    batch_size = new_bs
                    print(f"[WARN] reduce embed batch_size -> {batch_size} (retry same index)")
                    break

        if last_err is not None and batch_size == 1:
            preview = (cur[0] or "")[:160].replace("\n", " ")
            raise RuntimeError(f"Ollama embedding failed even for single item. preview='{preview}'") from last_err

        if last_err is None:
            i += len(cur)

    return vectors


# ============================================================
# Chroma Index
# ============================================================
class ChromaIndex:
    def __init__(self) -> None:
        self.chroma_dir = env("RAG_CHROMA_DIR", r"D:\AI\Django\chroma\rag")
        self.collection_name = env("RAG_CHROMA_COLLECTION", "cm_qna")

        os.makedirs(self.chroma_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=self.chroma_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # embedding config (MOST STABLE DEFAULTS)
        self.ollama_url = env("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434")
        self.embed_model = env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.embed_timeout = env_int("OLLAMA_TIMEOUT_SEC", 240)
        self.embed_batch = env_int("OLLAMA_EMBED_BATCH", 8)
        self.embed_retry = env_int("OLLAMA_RETRY", 5)

    def upsert(
        self,
        ids: List[str],
        texts: List[str],
        metas: List[Dict[str, Any]],
        *,
        skip_bad: bool,
        bad_log_path: str,
    ) -> None:
        if not ids:
            return
        if not (len(ids) == len(texts) == len(metas)):
            raise ValueError("ids/texts/metas 長度不一致")

        try:
            embs = langchain_ollama_embed(
                texts,
                base_url=self.ollama_url,
                model=self.embed_model,
                timeout_sec=self.embed_timeout,
                batch_size=self.embed_batch,
                max_retries=self.embed_retry,
            )
            self.col.upsert(
                ids=ids,
                embeddings=embs,
                documents=texts,
                metadatas=metas,
            )
        except Exception as e:
            print(f"[ERROR] batch embedding/upsert failed size={len(ids)} err={e}")
            if not skip_bad:
                raise

            # ✅ skip bad: log each doc id + preview
            os.makedirs(os.path.dirname(bad_log_path), exist_ok=True)
            with open(bad_log_path, "a", encoding="utf-8") as f:
                for _id, _txt, _meta in zip(ids, texts, metas):
                    f.write(json.dumps({
                        "id": _id,
                        "meta": _meta,
                        "text_preview": (_txt or "")[:240],
                        "ts": now_str(),
                    }, ensure_ascii=False) + "\n")
            print(f"[WARN] batch skipped; logged to {bad_log_path}")


# ============================================================
# SQL Server
# ============================================================
def get_sqlserver_conn() -> pyodbc.Connection:
    connFactory = connectionFactory()
    conn = connFactory.CreateMSSqlConnection()
    return conn


# ============================================================
# Main Sync
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Sync SQLServer view -> Chroma (1 row = 1 chunk) [MOST STABLE]")

    ap.add_argument("--view", default=env("SQL_SERVER_RAG_VIEW", "dbo.view_rag_cm_qna"), help="抽取視圖名稱")
    ap.add_argument("--limit", type=int, default=0, help="最多同步幾筆（0=不限）")

    # ✅ DB fetch and upsert tuned for stability
    ap.add_argument("--fetch-size", type=int, default=int(env("SQL_SERVER_FETCH_SIZE", "200")), help="cursor.fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=int(env("SQL_SERVER_UPSERT_BATCH", "50")), help="每批 upsert 幾筆（建議 50）")

    ap.add_argument("--since", default="", help="只同步 COALESCE(Dte_Verify,Dte_Finish) > since（YYYY-MM-DD）")
    ap.add_argument("--use-last-sync", action="store_true", help="使用 CHROMA_DIR/last_sync.txt 當 since（YYYY-MM-DD）")
    ap.add_argument("--no-save-last-sync", action="store_true", help="不同步寫回 last_sync.txt（除錯用）")
    ap.add_argument("--debug-one", default="", help="只同步指定 doc_id（cmqna_{CaseID}_{ItemNo}）")

    # ✅ MOST STABLE: shorter embedding text
    ap.add_argument("--text-max-chars", type=int, default=int(env("TEXT_MAX_CHARS", "1500")), help="embedding text 最長字元（建議 1500）")

    # ✅ failure handling
    ap.add_argument("--skip-bad", action="store_true", help="遇到批次仍失敗：跳過並記錄到 bad_rows.jsonl（不中斷）")

    args = ap.parse_args()

    chroma_dir = env("RAG_CHROMA_DIR", r"D:\AI\Django\chroma\rag")
    last_sync_file = os.path.join(chroma_dir, "last_sync.txt")
    bad_log_file = os.path.join(chroma_dir, "bad_rows.jsonl")

    since = validate_since_ymd(args.since)

    if args.use_last_sync and not since and not args.debug_one:
        try:
            raw = (open(last_sync_file, "r", encoding="utf-8").read() or "").strip()
            since = validate_since_ymd(raw)
        except Exception:
            since = ""

    dbg_caseid, dbg_itemno = parse_debug_one(args.debug_one)

    sql = f"SELECT * FROM {args.view}"
    params: List[Any] = []
    where_clauses: List[str] = []

    if dbg_caseid and dbg_itemno:
        where_clauses.append("CaseID = ? AND ItemNo = ?")
        params.extend([dbg_caseid, dbg_itemno])
    elif since:
        # ✅ 日粒度比較（最穩）
        where_clauses.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) > CONVERT(date, ?)")
        params.append(since)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY COALESCE(Dte_Verify, Dte_Finish) ASC"

    print(f"[sync] sql={sql}")
    if since:
        print(f"[sync] since={since}")
    if dbg_caseid and dbg_itemno:
        print(f"[sync] debug_one={args.debug_one} -> CaseID={dbg_caseid}, ItemNo={dbg_itemno}")
    print(f"[sync] fetch_size={args.fetch_size}, upsert_batch={args.upsert_batch}")
    print(f"[sync] text_max_chars={args.text_max_chars}")
    print(f"[sync] chroma_dir={chroma_dir}, time={now_str()}")

    idx = ChromaIndex()

    total = 0
    max_updated_seen: Optional[str] = None

    batch_ids: List[str] = []
    batch_texts: List[str] = []
    batch_metas: List[Dict[str, Any]] = []

    def flush() -> None:
        nonlocal batch_ids, batch_texts, batch_metas
        if not batch_ids:
            return

        idx.upsert(
            batch_ids,
            batch_texts,
            batch_metas,
            skip_bad=args.skip_bad,
            bad_log_path=bad_log_file,
        )

        print(f"[sync] upserted: +{len(batch_ids)} (total={total})")
        batch_ids, batch_texts, batch_metas = [], [], []

    conn = get_sqlserver_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)

        while True:
            rows = cur.fetchmany(args.fetch_size)
            if not rows:
                break

            dicts = rows_to_dicts(cur, rows)

            for d in dicts:
                total += 1
                if args.limit and total > args.limit:
                    break

                case_id = str(d.get("CaseID") or "").strip()
                item_no = str(d.get("ItemNo") or "").strip()
                if not case_id or not item_no:
                    continue

                doc_id = f"cmqna_{case_id}_{item_no}"

                case_name = str(d.get("CaseName") or "").strip()

                directive_val = pick_field(d, ["CONTENTS", "Case_ITEMS.CONTENTS", "CONTENTS1"])
                status_val = pick_field(d, ["DeptContents", "ITEMS_ASSIGN.DeptContents", "DeptContents1"])

                directive = normalize_text(str(directive_val or ""))
                status = normalize_text(str(status_val or ""))

                dept_factory = str(d.get("DeptCode_Factory") or "").strip()
                dept_code = str(d.get("DeptCode") or "").strip()

                if not directive or not status:
                    continue

                dte_finish = d.get("Dte_Finish")
                dte_verify = d.get("Dte_Verify")

                updated_dt = coalesce_dt(dte_verify, dte_finish)
                updated_at = to_ymd(updated_dt)
                if updated_at:
                    max_updated_seen = updated_at

                title = f"{case_name} | CaseID={case_id} ItemNo={item_no}"

                body = "\n".join([
                    f"案件名稱：{case_name}",
                    f"CaseID：{case_id}",
                    f"ItemNo：{item_no}",
                    f"指裁示：{directive}",
                    f"辦況：{status}",
                    f"廠別：{dept_factory}",
                    f"承辦單位：{dept_code}",
                    f"完成日：{dte_finish if dte_finish else ''}",
                    f"核定日：{dte_verify if dte_verify else ''}",
                ]).strip()

                body = normalize_text(body)

                # ✅ MOST STABLE: shorter text
                text_for_embed = body
                if args.text_max_chars > 0 and len(text_for_embed) > args.text_max_chars:
                    text_for_embed = text_for_embed[: args.text_max_chars]

                meta: Dict[str, Any] = {
                    "doc_id": doc_id,
                    "doc_type": "cm_qna",
                    "title": title,
                    "updated_at": updated_at,
                    "dept": dept_factory,
                    "case_id": case_id,
                    "item_no": item_no,
                    "dept_code": dept_code,
                }

                batch_ids.append(doc_id)
                batch_texts.append(text_for_embed)
                batch_metas.append(meta)

                if len(batch_ids) >= args.upsert_batch:
                    flush()

            if args.limit and total >= args.limit:
                break

        flush()
        cur.close()
    finally:
        conn.close()

    print(f"[sync] done. total={total}, max_updated_seen={max_updated_seen}")

    if (not args.debug_one) and args.use_last_sync and (not args.no_save_last_sync) and max_updated_seen:
        os.makedirs(chroma_dir, exist_ok=True)
        with open(last_sync_file, "w", encoding="utf-8") as f:
            f.write(max_updated_seen)
        print(f"[sync] wrote last_sync: {last_sync_file} = {max_updated_seen}")


if __name__ == "__main__":
    main()
```

---

## ✅ 建議你的 .env（穩定版預設）

你可以先照這組放（更穩）：

```ini
OLLAMA_BASE_URL=http://mpcai.mpc.mil.tw:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_TIMEOUT_SEC=240
OLLAMA_EMBED_BATCH=8
OLLAMA_RETRY=5

SQL_SERVER_FETCH_SIZE=200
SQL_SERVER_UPSERT_BATCH=50
TEXT_MAX_CHARS=1500

RAG_CHROMA_DIR=D:\AI\Django\chroma\rag
RAG_CHROMA_COLLECTION=cm_qna
SQL_SERVER_RAG_VIEW=dbo.view_rag_cm_qna
```

---

## ✅ 使用範例（直接照跑）

### 1) 先用少量驗證（最重要）

```powershell
python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py `
  --view dbo.view_rag_cm_qna `
  --limit 30 `
  --skip-bad
```

### 2) 用 last_sync 增量同步（正式跑）

```powershell
python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py `
  --view dbo.view_rag_cm_qna `
  --use-last-sync `
  --skip-bad
```

### 3) 指定某一筆 debug（你原本就有）

```powershell
python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py `
  --view dbo.view_rag_cm_qna `
  --debug-one cmqna_123_456 `
  --skip-bad
```

---

## ✅ 如果還是偶發 500，我建議你再「更保守」一格（幾乎不會爆）

把以下改更小：

* `OLLAMA_EMBED_BATCH=4`
* `SQL_SERVER_UPSERT_BATCH=30`
* `TEXT_MAX_CHARS=1000`

（你不用改程式，只要改 env 或 CLI 參數）

---

## ✅ 你要的「失敗清單」在哪裡、怎麼用

* 失敗會寫到：`D:\AI\Django\chroma\rag\bad_rows.jsonl`
* 內容包含 `id`、`meta`、`text_preview`、時間戳
  你可以用它定位哪些資料一直讓 embeddings 失敗，通常是：
* 單筆內容超長 / 重複符號很多
* 某些欄位帶奇怪控制字元（我已加 NUL 清理了）

---

如果你願意再更「極限穩定」（幾乎 0 失敗），下一步我會把 **embed 時遇到單筆失敗** 改成「自動再截短 1500→1000→700→500」逐級嘗試，成功就 upsert；只有最後仍不行才記 bad_rows。這一招通常可以把 bad_rows 壓到幾乎沒有。
