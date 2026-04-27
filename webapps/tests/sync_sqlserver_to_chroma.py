# sync_sqlserver_to_chroma.py (MOST STABLE + QUEUE THROTTLE VERSION) - DBFactory Edition
from __future__ import annotations

import os
import json
import time
import argparse
from collections import deque
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from langchain_ollama import OllamaEmbeddings

import pyodbc
import chromadb
from chromadb.config import Settings


from dotenv import load_dotenv  # type: ignore
import sys
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent  # 從 tests 文件夾向上移動兩級到項目根
sys.path.append(str(project_root))

from webapps.database.db_factoryold import DatabaseFactory, get_db, db_connect

try:    
    load_dotenv(override=False)    
    conn = DatabaseFactory.create("sqlserver")
    
except ImportError as e:
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
    while "\n\n\n" in s:
        s = s.replace("\n\n\n", "\n\n")
    return s.strip()


def looks_like_gateway_timeout(err: Exception) -> bool:
    """
    粗略判斷是否是 504 / gateway / timeout 相關
    """
    msg = (str(err) or "").lower()
    keywords = [
        "504",
        "gateway timeout",
        "timed out",
        "timeout",
        "read timeout",
        "bad gateway",
        "502",
        "503",
    ]
    return any(k in msg for k in keywords)


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
    _ = timeout_sec  # LangChain wrapper 不一定能直接套 timeout；先保留參數

    emb = OllamaEmbeddings(model=model, base_url=base_url)

    vectors: List[List[float]] = []
    i = 0

    while i < len(texts):
        cur = texts[i: i + batch_size]

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

                # adaptive batch shrinking
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
        # from env (shared with your Django settings habit)
        self.chroma_dir = env("RAG_CHROMA_DIR", r"d:\AI\AI_TOOLS\chroma\rag")
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
        self.ollama_url = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
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

        safe_texts = [(t if (t and t.strip()) else " ") for t in texts]

        try:
            embs = langchain_ollama_embed(
                safe_texts,
                base_url=self.ollama_url,
                model=self.embed_model,
                timeout_sec=self.embed_timeout,
                batch_size=self.embed_batch,
                max_retries=self.embed_retry,
            )
            self.col.upsert(
                ids=ids,
                embeddings=embs,
                documents=safe_texts,
                metadatas=metas,
            )
        except Exception as e:
            print(f"[ERROR] batch embedding/upsert failed size={len(ids)} err={e}")
            if not skip_bad:
                raise

            os.makedirs(os.path.dirname(bad_log_path), exist_ok=True)
            with open(bad_log_path, "a", encoding="utf-8") as f:
                for _id, _txt, _meta in zip(ids, safe_texts, metas):
                    f.write(json.dumps({
                        "id": _id,
                        "meta": _meta,
                        "text_preview": (_txt or "")[:240],
                        "ts": now_str(),
                        "err": str(e),
                    }, ensure_ascii=False) + "\n")
            print(f"[WARN] batch skipped; logged to {bad_log_path}")


# ============================================================
# SQL Server (DBFactory)
# ============================================================
def get_sqlserver_conn() -> pyodbc.Connection:
    # ✅ Auto reads .env from db_factory
    return db_connect("sqlserver")


# ============================================================
# Main Sync
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Sync SQLServer view -> Chroma (1 row = 1 chunk) [MOST STABLE + QUEUE THROTTLE + DBFactory]")

    ap.add_argument("--view", default=env("SQL_SERVER_RAG_VIEW", "dbo.view_rag_cm_qna"), help="抽取視圖名稱")
    ap.add_argument("--limit", type=int, default=0, help="最多同步幾筆（0=不限）")

    ap.add_argument("--fetch-size", type=int, default=int(env("SQL_SERVER_FETCH_SIZE", "200")), help="cursor.fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=int(env("SQL_SERVER_UPSERT_BATCH", "50")), help="每批 upsert 幾筆（建議 2~50；遠端 Ollama 建議 2）")

    ap.add_argument("--since", default="", help="只同步 COALESCE(Dte_Verify,Dte_Finish) > since（YYYY-MM-DD）")
    ap.add_argument("--use-last-sync", action="store_true", help="使用 CHROMA_DIR/last_sync.txt 當 since（YYYY-MM-DD）")
    ap.add_argument("--no-save-last-sync", action="store_true", help="不同步寫回 last_sync.txt（除錯用）")
    ap.add_argument("--debug-one", default="", help="只同步指定 doc_id（cmqna_{CaseID}_{ItemNo}）")

    ap.add_argument("--text-max-chars", type=int, default=int(env("TEXT_MAX_CHARS", "1500")), help="embedding text 最長字元（建議 800~1500）")

    ap.add_argument("--skip-bad", action="store_true", help="遇到批次仍失敗：跳過並記錄到 bad_rows.jsonl（不中斷）")

    ap.add_argument("--rate-limit-ms", type=int, default=int(env("EMBED_RATE_LIMIT_MS", "350")),
                    help="每次 embedding/upsert 批次後 sleep 幾毫秒（節流用，建議 200~800）")
    ap.add_argument("--burst-sleep-ms", type=int, default=int(env("EMBED_BURST_SLEEP_MS", "1200")),
                    help="遇到 504/timeout 類錯誤時額外 sleep 幾毫秒（建議 1000~5000）")
    ap.add_argument("--queue-max", type=int, default=int(env("EMBED_QUEUE_MAX", "500")),
                    help="embedding queue 最大累積筆數，避免吃太多 RAM（建議 200~2000）")

    # 若遇到 504/timeout 時的額外重試次數（避免一遇到就停）
    ap.add_argument("--timeout-retry", type=int, default=int(env("EMBED_TIMEOUT_RETRY", "15")),
                    help="遇到 504/timeout 類錯誤時，consume_queue 額外重試幾次（預設 15；0=不重試）")

    args = ap.parse_args()

    chroma_dir = env("RAG_CHROMA_DIR", r"d:\AI\AI_TOOLS\chroma\rag")
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
    print(f"[sync] rate_limit_ms={args.rate_limit_ms}, burst_sleep_ms={args.burst_sleep_ms}, queue_max={args.queue_max}, timeout_retry={args.timeout_retry}")
    print(f"[sync] chroma_dir={chroma_dir}, time={now_str()}")

    idx = ChromaIndex()

    total_rows_seen = 0
    total_queued = 0
    total_upserted = 0
    max_updated_seen: Optional[str] = None

    q = deque()

    def consume_queue(force: bool = False) -> None:
        nonlocal q, total_upserted

        while q and (force or len(q) >= args.upsert_batch):
            ids: List[str] = []
            texts: List[str] = []
            metas: List[Dict[str, Any]] = []

            n = min(max(1, args.upsert_batch), len(q))
            for _ in range(n):
                _id, _txt, _meta = q.popleft()
                ids.append(_id)
                texts.append(_txt)
                metas.append(_meta)

            retry_left = max(0, int(args.timeout_retry))

            while True:
                try:
                    idx.upsert(
                        ids,
                        texts,
                        metas,
                        skip_bad=args.skip_bad,
                        bad_log_path=bad_log_file,
                    )
                    total_upserted += len(ids)
                    print(f"[sync] upserted: +{len(ids)} (rows_seen={total_rows_seen}, upserted={total_upserted}, queue={len(q)})")

                    if args.rate_limit_ms > 0:
                        time.sleep(args.rate_limit_ms / 1000.0)
                    break

                except Exception as e:
                    print(f"[ERROR] consume_queue failed size={len(ids)} err={e}")

                    # 先把這批塞回 queue 前面（保持順序）
                    for _id, _txt, _meta in reversed(list(zip(ids, texts, metas))):
                        q.appendleft((_id, _txt, _meta))

                    if looks_like_gateway_timeout(e) and retry_left > 0:
                        retry_left -= 1
                        if args.burst_sleep_ms > 0:
                            time.sleep(args.burst_sleep_ms / 1000.0)
                        else:
                            time.sleep(2.0)

                        # 重新取回同一批再試
                        ids.clear(); texts.clear(); metas.clear()
                        n2 = min(max(1, args.upsert_batch), len(q))
                        for _ in range(n2):
                            _id, _txt, _meta = q.popleft()
                            ids.append(_id); texts.append(_txt); metas.append(_meta)
                        continue

                    # 如果 skip_bad：就把這批記錄後丟掉（不中斷）
                    if args.skip_bad:
                        drop_ids: List[str] = []
                        drop_texts: List[str] = []
                        drop_metas: List[Dict[str, Any]] = []

                        n3 = min(max(1, args.upsert_batch), len(q))
                        for _ in range(n3):
                            _id, _txt, _meta = q.popleft()
                            drop_ids.append(_id); drop_texts.append(_txt); drop_metas.append(_meta)

                        os.makedirs(os.path.dirname(bad_log_file), exist_ok=True)
                        with open(bad_log_file, "a", encoding="utf-8") as f:
                            for _id, _txt, _meta in zip(drop_ids, drop_texts, drop_metas):
                                f.write(json.dumps({
                                    "id": _id,
                                    "meta": _meta,
                                    "text_preview": (_txt or "")[:240],
                                    "ts": now_str(),
                                    "consume_queue_err": str(e),
                                }, ensure_ascii=False) + "\n")
                        print(f"[WARN] batch dropped due to error; logged to {bad_log_file}")

                        if args.rate_limit_ms > 0:
                            time.sleep(args.rate_limit_ms / 1000.0)
                        break

                    # 不跳過：中止
                    raise

    conn: Optional[pyodbc.Connection] = None
    try:
        conn = get_sqlserver_conn()
        cur = conn.cursor()
        cur.execute(sql, params)

        while True:
            rows = cur.fetchmany(args.fetch_size)
            if not rows:
                break

            dicts = rows_to_dicts(cur, rows)

            for d in dicts:
                total_rows_seen += 1
                if args.limit and total_rows_seen > args.limit:
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
                    "chunk_no": item_no,  # ✅ align with retrieve.py
                }

                q.append((doc_id, text_for_embed, meta))
                total_queued += 1

                if args.queue_max > 0 and len(q) >= args.queue_max:
                    consume_queue(force=False)

                if len(q) >= max(1, args.upsert_batch):
                    consume_queue(force=False)

            if args.limit and total_rows_seen >= args.limit:
                break

        consume_queue(force=True)
        cur.close()

    finally:
        if conn is not None:
            conn.close()

    print(f"[sync] done. rows_seen={total_rows_seen}, queued={total_queued}, upserted={total_upserted}, max_updated_seen={max_updated_seen}")

    if (not args.debug_one) and args.use_last_sync and (not args.no_save_last_sync) and max_updated_seen:
        os.makedirs(chroma_dir, exist_ok=True)
        with open(last_sync_file, "w", encoding="utf-8") as f:
            f.write(max_updated_seen)
        print(f"[sync] wrote last_sync: {last_sync_file} = {max_updated_seen}")


if __name__ == "__main__":
    main()

# 建議：
# python sync_sqlserver_to_chroma.py --upsert-batch 2 --text-max-chars 800 --rate-limit-ms 500 --burst-sleep-ms 3000 --queue-max 300 --skip-bad
