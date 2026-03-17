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
from webapps.database.connectionFactory import connectionFactory    

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
    """since 僅接受 YYYY-MM-DD（固定 10 碼）"""
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"--since 格式必須為 YYYY-MM-DD，例如 2025-01-03；收到：{s}") from e


def to_ymd(x: Any) -> str:
    """把 datetime/date/字串 轉成 YYYY-MM-DD；不合法回空字串"""
    if x is None:
        return ""
    if isinstance(x, datetime):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, date):
        return x.strftime("%Y-%m-%d")

    s = str(x).strip()
    if not s:
        return ""
    # 允許 'YYYY-MM-DD ...'
    if len(s) >= 10:
        s10 = s[:10]
        try:
            return validate_since_ymd(s10)
        except Exception:
            return ""
    return ""


def coalesce_dt(a: Any, b: Any) -> Any:
    """回傳 a 若存在，否則 b"""
    return a if a not in (None, "") else b


def parse_debug_one(s: str) -> Tuple[str, str]:
    """
    cmqna_{CaseID}_{ItemNo} -> (CaseID, ItemNo)
    解析失敗就回 ("","")
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
    欄位名容錯：依序嘗試 keys，找到第一個存在且非 None 的值
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
            raise RuntimeError(f"Ollama embeddings 回傳格式異常：{data}")
        vectors.append(emb)

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

    def upsert(self, ids: List[str], texts: List[str], metas: List[Dict[str, Any]]) -> None:
        if not ids:
            return
        if not (len(ids) == len(texts) == len(metas)):
            raise ValueError("ids/texts/metas 長度不一致")

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
def get_sqlserver_conn() -> pyodbc.Connection:
    # host = env("SQL_SERVER_HOST")
    # port = env("SQL_SERVER_PORT", "1433")
    # db = env("SQL_SERVER_DB", "CaseManager")
    # user = env("SQL_SERVER_USER")
    # pwd = env("SQL_SERVER_PASS")
    # driver = env("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server")

    # missing = [k for k, v in {
    #     "SQL_SERVER_HOST": host,
    #     "SQL_SERVER_USER": user,
    #     "SQL_SERVER_PASS": pwd,
    # }.items() if not v]
    # if missing:
    #     raise RuntimeError("缺少 SQL Server 連線環境變數：" + ", ".join(missing))

    # server = f"{host},{port}" if port else host

    # conn_str = (
    #     f"DRIVER={{{driver}}};"
    #     f"SERVER={server}\\mpcsqlserver;"
    #     f"DATABASE={db};"
    #     f"UID={user};"
    #     f"PWD={pwd};"
    #     "TrustServerCertificate=yes;"
    # )
    
    # 建立连接
    connFactory = connectionFactory()
    conn = connFactory.CreateMSSqlConnection()
    # print("✅ 连接 SQL Server 成功！")
    # print(pyodbc.drivers())

    return conn


# ============================================================
# Main Sync
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Sync SQLServer view -> Chroma (1 row = 1 chunk)")

    ap.add_argument("--view", default=env("SQL_SERVER_RAG_VIEW", "dbo.view_rag_cm_qna"), help="抽取視圖名稱")
    ap.add_argument("--limit", type=int, default=0, help="最多同步幾筆（0=不限）")
    ap.add_argument("--fetch-size", type=int, default=int(env("SQL_SERVER_FETCH_SIZE", "200")), help="cursor.fetchmany size")
    ap.add_argument("--upsert-batch", type=int, default=int(env("SQL_SERVER_UPSERT_BATCH", "200")), help="每批 upsert 幾筆")

    ap.add_argument("--since", default="", help="只同步 COALESCE(Dte_Verify,Dte_Finish) > since（YYYY-MM-DD）")
    ap.add_argument("--use-last-sync", action="store_true", help="使用 CHROMA_DIR/last_sync.txt 當 since（YYYY-MM-DD）")
    ap.add_argument("--no-save-last-sync", action="store_true", help="不同步寫回 last_sync.txt（除錯用）")
    ap.add_argument("--debug-one", default="", help="只同步指定 doc_id（cmqna_{CaseID}_{ItemNo}）")

    args = ap.parse_args()

    chroma_dir = env("RAG_CHROMA_DIR", r"D:\AI\Django\chroma\rag")
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

    # debug_one：用 CaseID/ItemNo 過濾（view 有這兩欄）
    if dbg_caseid and dbg_itemno:
        where_clauses.append("CaseID = ? AND ItemNo = ?")
        params.extend([dbg_caseid, dbg_itemno])
    elif since:
        # ✅ 日粒度比較（最穩）：避免時間造成漏抓/誤抓
        where_clauses.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) > CONVERT(date, ?)")
        params.append(since)  # 直接丟 'YYYY-MM-DD'

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

                # ✅ VIEW 無別名時，欄位名可能被 driver 調整：做容錯
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

# 使用方式
# python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py  --view dbo.View_rag_cm_qna
# python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py  --view dbo.View_rag_cm_qna --since 2025-01-01
# python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py  --view dbo.View_rag_cm_qna --use-last-sync
# python D:\AI\Django\webapps\database\sync_sqlserver_to_chroma.py  --view dbo.View_rag_cm_qna --debug-one cmqna_123_456
