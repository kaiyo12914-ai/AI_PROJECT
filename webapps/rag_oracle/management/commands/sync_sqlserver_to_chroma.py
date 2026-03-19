# sync_sqlserver_to_chroma.py
from __future__ import annotations

import os
import argparse
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import pyodbc
import requests
import chromadb
from chromadb.config import Settings

from webapps.database.db_factory import db_connect
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
    """since ???YYYY-MM-DD嚗摰?10 蝣潘?"""
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"--since ?澆?敹???YYYY-MM-DD嚗?憒?2025-01-03嚗?堆?{s}") from e


def to_ymd(x: Any) -> str:
    """??datetime/date/摮葡 頧? YYYY-MM-DD嚗????征摮葡"""
    if x is None:
        return ""
    if isinstance(x, datetime):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, date):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip()
    if not s:
        return ""
    # ?迂 'YYYY-MM-DD ...'
    if len(s) >= 10:
        s10 = s[:10]
        try:
            return validate_since_ymd(s10)
        except Exception:
            return ""
    return ""


def coalesce_dt(a: Any, b: Any) -> Any:
    """? a ?亙??剁??血? b"""
    return a if a not in (None, "") else b


def parse_debug_one(s: str) -> Tuple[str, str]:
    """
    cmqna_{CaseID}_{ItemNo} -> (CaseID, ItemNo)
    閫??憭望?撠勗? ("","")
    """
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
    """
    甈??捆?荔?靘??岫 keys嚗?啁洵銝???其???None ??
    """
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


# ============================================================
# Embeddings: Ollama
# ============================================================
def ollama_embed(texts: List[str]) -> List[List[float]]:
    base_url = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    url = f"{base_url}/api/embeddings"

    sess = requests.Session()
    vectors: List[List[float]] = []

    for t in texts:
        payload = {"model": model, "prompt": t}
        r = sess.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        emb = data.get("embedding")
        if not emb or not isinstance(emb, list):
            raise RuntimeError(f"Ollama embeddings ??澆??啣虜嚗data}")
        vectors.append(emb)

    return vectors


# ============================================================
# Chroma Index
# ============================================================
class ChromaIndex:
    def __init__(self) -> None:
        self.chroma_dir = env("RAG_CHROMA_DIR", r"F:\AI\AI_TOOLS\chroma\rag")
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

    def upsert(self, ids: List[str], texts: List[str], metas: List[Dict[str, Any]]) -> None:
        if not ids:
            return
        if not (len(ids) == len(texts) == len(metas)):
            raise ValueError("ids/texts/metas ?瑕漲銝???)

        embs = ollama_embed(texts)

        self.col.upsert(
            ids=ids,
            embeddings=embs,
            documents=texts,
            metadatas=metas,
        )


# ============================================================
# SQL Server
# ============================================================
def get_sqlserver_conn() -> pyodbc.Connection:\r\n    return db_connect("sqlserver")


# ============================================================
# Main Sync
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Sync SQLServer view -> Chroma (1 row = 1 chunk)")

    ap.add_argument("--view", default=env("SQL_SERVER_RAG_VIEW", "dbo.vieww_rag_cm_qn"), help="?賢?閬??迂")
    ap.add_argument("--limit", type=int, default=0, help="?憭?甇亙嗾蝑?0=銝?嚗?)
    ap.add_argument("--fetch-size", type=int, default=int(env("SQL_SERVER_FETCH_SIZE", "200")), help="cursor.fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=int(env("SQL_SERVER_UPSERT_BATCH", "200")), help="瘥 upsert 撟曄?")

    ap.add_argument("--since", default="", help="?芸?甇?COALESCE(Dte_Verify,Dte_Finish) > since嚗YYY-MM-DD嚗?)
    ap.add_argument("--use-last-sync", action="store_true", help="雿輻 CHROMA_DIR/last_sync.txt ??since嚗YYY-MM-DD嚗?)
    ap.add_argument("--no-save-last-sync", action="store_true", help="銝?甇亙神??last_sync.txt嚗?舐嚗?)
    ap.add_argument("--debug-one", default="", help="?芸?甇交?摰?doc_id嚗mqna_{CaseID}_{ItemNo}嚗?)

    args = ap.parse_args()

    chroma_dir = env("RAG_CHROMA_DIR", r"F:\AI\AI_TOOLS\chroma\rag")
    last_sync_file = os.path.join(chroma_dir, "last_sync.txt")

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

    # debug_one嚗 CaseID/ItemNo ?蕪嚗iew ?甈?
    if dbg_caseid and dbg_itemno:
        where_clauses.append("CaseID = ? AND ItemNo = ?")
        params.extend([dbg_caseid, dbg_itemno])
    elif since:
        # ???亦?摨行?頛??蝛抬?嚗????瞍?/隤斗?
        where_clauses.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) > CONVERT(date, ?)")
        params.append(since)  # ?湔銝?'YYYY-MM-DD'

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    sql += " ORDER BY COALESCE(Dte_Verify, Dte_Finish) ASC"

    print(f"[sync] sql={sql}")
    if since:
        print(f"[sync] since={since}")
    if dbg_caseid and dbg_itemno:
        print(f"[sync] debug_one={args.debug_one} -> CaseID={dbg_caseid}, ItemNo={dbg_itemno}")
    print(f"[sync] fetch_size={args.fetch_size}, upsert_batch={args.upsert_batch}")
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
        idx.upsert(batch_ids, batch_texts, batch_metas)
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

                # ??VIEW ?∪??嚗?雿??航鋡?driver 隤踵嚗?摰寥
                directive_val = pick_field(d, ["CONTENTS", "Case_ITEMS.CONTENTS", "CONTENTS1"])
                status_val = pick_field(d, ["DeptContents", "ITEMS_ASSIGN.DeptContents", "DeptContents1"])

                directive = str(directive_val or "").strip()
                status = str(status_val or "").strip()

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
                    f"獢辣?迂嚗case_name}",
                    f"CaseID嚗case_id}",
                    f"ItemNo嚗item_no}",
                    f"??蝷綽?{directive}",
                    f"颲行?嚗status}",
                    f"撱嚗dept_factory}",
                    f"?輯齒?桐?嚗dept_code}",
                    f"摰??伐?{dte_finish if dte_finish else ''}",
                    f"?詨??伐?{dte_verify if dte_verify else ''}",
                ]).strip()

                meta: Dict[str, Any] = {
                    "doc_id": doc_id,
                    "doc_type": "cm_qna",
                    "title": title,
                    "updated_at": updated_at,
                    "dept": dept_factory,
                    "sec": "",
                    "case_id": case_id,
                    "item_no": item_no,
                    "dept_code": dept_code,
                    "assign_status": "",
                    "is_finished": "",
                    "lock_edit": "",
                    "remove_status": "",
                    "manager_verify": "",
                }

                text_for_embed = body[:4000]

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

# 雿輻?孵?
# python sync_sqlserver_to_chroma.py --view dbo.vieww_rag_cm_qn
# python sync_sqlserver_to_chroma.py --view dbo.vieww_rag_cm_qn --since 2025-01-01
# python sync_sqlserver_to_chroma.py --view dbo.vieww_rag_cm_qn --use-last-sync
# python sync_sqlserver_to_chroma.py --view dbo.vieww_rag_cm_qn --debug-one cmqna_123_456

