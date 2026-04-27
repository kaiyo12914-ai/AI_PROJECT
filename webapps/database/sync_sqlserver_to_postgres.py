# webapps/database/sync_sqlserver_to_postgres.py
from __future__ import annotations

import os
import argparse
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2 # type: ignore
    from psycopg2.extras import execute_batch # type: ignore
except ImportError:
    psycopg2 = None

import pyodbc

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
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        raise ValueError(f"--since 參數必須為 YYYY-MM-DD，收到的值為: {s}") from e

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

# ============================================================
# Database Initializers
# ============================================================
def init_postgres_table(conn: Any, table_name: str) -> None:
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        doc_id VARCHAR(100) PRIMARY KEY,
        case_id VARCHAR(100),
        item_no VARCHAR(50),
        case_name VARCHAR(500),
        title VARCHAR(1000),
        directive TEXT,
        status TEXT,
        dept_name VARCHAR(200),
        dept_code VARCHAR(100),
        updated_at DATE
    );
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print(f"[sync] PostgreSQL table `{table_name}` verified/created.")

# ============================================================
# Main Sync
# ============================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Sync SQLServer view -> PostgreSQL DB")

    ap.add_argument("--view", default=env("SQL_SERVER_RAG_VIEW", "dbo.vieww_rag_cm_qn"), help="來源 SQL Server View")
    ap.add_argument("--target-table", default="public.meeting_records", help="目標 PostgreSQL Table")
    ap.add_argument("--limit", type=int, default=0, help="最多同步筆數，0=不限")
    ap.add_argument("--fetch-size", type=int, default=int(env("SQL_SERVER_FETCH_SIZE", "500")), help="SQL Server cursor 取回批次")
    ap.add_argument("--upsert-batch", type=int, default=int(env("PG_UPSERT_BATCH", "200")), help="寫入 PostgreSQL 批次大小")
    ap.add_argument("--since", default="", help="同步起始日期 (大於等於)，YYYY-MM-DD")
    ap.add_argument("--until", default="", help="同步截止日期 (小於等於)，YYYY-MM-DD")
    ap.add_argument("--debug-one", default="", help="單筆除錯 doc_id，如 cmqna_123_456")

    args = ap.parse_args()

    since = validate_since_ymd(args.since)
    until = validate_since_ymd(args.until)
    dbg_caseid, dbg_itemno = parse_debug_one(args.debug_one)

    sql = f"SELECT * FROM {args.view}"
    params: List[Any] = []
    where_clauses: List[str] = []

    if dbg_caseid and dbg_itemno:
        where_clauses.append("CaseID = ? AND ItemNo = ?")
        params.extend([dbg_caseid, dbg_itemno])
    else:
        if since:
            where_clauses.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) >= CONVERT(date, ?)")
            params.append(since) 
        if until:
            where_clauses.append("CONVERT(date, COALESCE(Dte_Verify, Dte_Finish)) <= CONVERT(date, ?)")
            params.append(until)

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY COALESCE(Dte_Verify, Dte_Finish) ASC"

    print(f"[sync] source_sql={sql}")
    if since or until:
        print(f"[sync] time_range: since={since}, until={until}")
    if dbg_caseid and dbg_itemno:
        print(f"[sync] debug_one={args.debug_one} -> CaseID={dbg_caseid}, ItemNo={dbg_itemno}")

    # Initialize Connections
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is missing! Please pip install psycopg2-binary")
        
    conn_pg = db_connect("postgresql")
    conn_sql = db_connect("sqlserver")

    init_postgres_table(conn_pg, args.target_table)

    target_upsert_sql = f"""
    INSERT INTO {args.target_table} 
    (doc_id, case_id, item_no, case_name, title, directive, status, dept_name, dept_code, updated_at) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (doc_id) DO UPDATE SET 
        case_id = EXCLUDED.case_id,
        item_no = EXCLUDED.item_no,
        case_name = EXCLUDED.case_name,
        title = EXCLUDED.title,
        directive = EXCLUDED.directive,
        status = EXCLUDED.status,
        dept_name = EXCLUDED.dept_name,
        dept_code = EXCLUDED.dept_code,
        updated_at = EXCLUDED.updated_at;
    """

    total = 0
    max_updated_seen: Optional[str] = None
    batch_records: List[Tuple] = []

    def flush_pg() -> None:
        nonlocal batch_records
        if not batch_records:
            return
        with conn_pg.cursor() as cur:
            execute_batch(cur, target_upsert_sql, batch_records, page_size=args.upsert_batch)
        conn_pg.commit()
        print(f"[sync] upserted: +{len(batch_records)} (total={total})")
        batch_records.clear()

    try:
        cur_sql = conn_sql.cursor()
        cur_sql.execute(sql, params)

        while True:
            rows = cur_sql.fetchmany(args.fetch_size)
            if not rows:
                break

            dicts = rows_to_dicts(cur_sql, rows)

            for d in dicts:
                total += 1
                if args.limit and total > args.limit:
                    break

                case_id = str(d.get("CaseID") or "").strip()
                item_no = str(d.get("ItemNo") or "").strip()
                if not case_id or not item_no:
                    continue

                doc_id = f"meeting_{case_id}_{item_no}"
                case_name = str(d.get("CaseName") or "").strip()

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
                
                # Append row as tuple aligned with target_upsert_sql columns
                parsed_updated_at = datetime.strptime(updated_at, "%Y-%m-%d").date() if updated_at else None
                
                batch_records.append((
                    doc_id, case_id, item_no, case_name, title, 
                    directive, status, dept_factory, dept_code, parsed_updated_at
                ))

                if len(batch_records) >= args.upsert_batch:
                    flush_pg()

            if args.limit and total >= args.limit:
                break

        flush_pg()
        cur_sql.close()
    finally:
        conn_sql.close()
        conn_pg.close()

    print(f"[sync] done. total={total}, max_updated_seen={max_updated_seen}")

if __name__ == "__main__":
    main()

# ============================================================
# 程式使用說明 (Usage Notes)
# ============================================================
# 本腳本直接將 SQL Server 上的會議指裁示與辦理情形，同步寫入 PostgreSQL 的 meeting_records 資料表中，
# 作為「會議彙辦事項擬答 (meetingreply)」子系統之 RAG 檢索基礎庫 (Base DB)。
#
# 常見執行方式：
# 1. 預設完整執行 (同步所有或依排程提取)： 
#    python webapps/database/sync_sqlserver_to_postgres.py
#
# 2. 指定區間更新 (僅同步特定日期「起 / 迄」的最新編輯或完成紀錄)：
#    python webapps/database/sync_sqlserver_to_postgres.py --since 2025-01-01
#    python webapps/database/sync_sqlserver_to_postgres.py --since 2025-01-01 --until 2025-01-31
#
# 3. 指定同步筆數上限 (適合首次啟動測試效能或防呆)：
#    python webapps/database/sync_sqlserver_to_postgres.py --limit 1000
#
# 4. 單筆指定除錯同步 (只針對某個 CaseID 與 ItemNo 覆寫)：
#    python webapps/database/sync_sqlserver_to_postgres.py --debug-one cmqna_{CaseID}_{ItemNo}
