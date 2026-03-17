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

from webapps.database.db_factory import db_connect
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


def connect_sqlserver() -> pyodbc.Connection:
    return db_connect("sqlserver")


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
    ap.add_argument("--conn", default="", help="DEPRECATED: ignored; use db_factory settings/env instead")
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

    if args.conn:
        print("[WARN] --conn is deprecated and ignored; using db_factory settings/env instead")

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

    conn = connect_sqlserver()
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
