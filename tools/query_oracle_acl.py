# tools/query_oracle_acl.py
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import List, Tuple

# 讓它可在專案外層執行也能 import webapps.*
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from webapps.database.db_factory import db_connect  # noqa: E402


def env_str(k: str, d: str = "") -> str:
    return (os.getenv(k) or d).strip()


def fetch_user_groups(
    *,
    user_id: str = "",
    like: bool = False,
    limit: int = 2000,
) -> List[Tuple[str, str]]:
    """
    查 Oracle ACL: 回傳 [(USERID, GROUP_NAME), ...]
    - user_id=""：列出全部（上限 limit）
    - like=True：用 LIKE 做模糊查
    """
    table = env_str("ORA_ACL_TABLE", "VIEW_ZZ_USER_GROUP_ACL")
    user_col = env_str("ORA_ACL_USER_COL", "USERNAME")
    group_col = env_str("ORA_ACL_GROUP_COL", "GROUP_NAME")

    # ⚠️ table/col 名稱不可參數化，只能從 env 讀（請確保 env 值是可信的）
    base_sql = f"""
        SELECT TRIM({user_col}) AS USERID, TRIM({group_col}) AS GROUP_NAME
        FROM {table}
    """

    params = {}
    where = ""
    if user_id:
        if like:
            where = f" WHERE TRIM({user_col}) LIKE :u"
            params["u"] = f"%{user_id.strip()}%"
        else:
            where = f" WHERE TRIM({user_col}) = :u"
            params["u"] = user_id.strip()

    sql = base_sql + where + f" ORDER BY TRIM({user_col}), TRIM({group_col})"

    conn = None
    cur = None
    try:
        conn = db_connect("oracle")
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchmany(max(1, int(limit)))
        out: List[Tuple[str, str]] = []
        for r in rows or []:
            uid = (r[0] or "").strip()
            grp = (r[1] or "").strip()
            if uid and grp:
                out.append((uid, grp))
        return out
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Query Oracle ACL table: USERID / GROUP")
    ap.add_argument("--user", default="", help="USERID (exact match by default)")
    ap.add_argument("--like", action="store_true", help="use LIKE for fuzzy search")
    ap.add_argument("--limit", type=int, default=2000, help="max rows to print")
    args = ap.parse_args()

    rows = fetch_user_groups(user_id=args.user, like=args.like, limit=args.limit)

    if not rows:
        print("(no rows)")
        return

    # pretty print
    w = max(len(x[0]) for x in rows)
    print(f"{'USERID'.ljust(w)}  GROUP")
    print("-" * (w + 2 + 20))
    for uid, grp in rows:
        print(f"{uid.ljust(w)}  {grp}")
    print(f"\nTotal: {len(rows)} rows")


if __name__ == "__main__":
    main()

# .env 有 ORA_HOST/ORA_SERVICE_NAME/ORA_USER/ORA_PASS
# 執行方式:python tools\query_oracle_acl.py --user H121356578
# 列出全部（上限 20）：python tools\query_oracle_acl.py --limit 20

# .env
# ORA_ACL_TABLE=ZZ_USER_GROUPS
# ORA_ACL_USER_COL=USERNAME  待查
# ORA_ACL_GROUP_COL=GROUP_NAME 待查
