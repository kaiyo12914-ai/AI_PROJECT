# webapps/portal/oracle_emp.py
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, TypedDict

from django.conf import settings

# ✅ DB 連線必須走 DB_FACTORY（專案規範）
from webapps.database.db_factory import OracleDB, db_connect

logger = logging.getLogger(__name__)

# ============================================================
# 固定 SQL
# ============================================================
# ✅ oracledb 參數風格：:emp_id（dict 綁定）
EMP_NAME_SQLS = (
    """
SELECT TRIM(NAME) AS EMP_NAME
FROM CT_EMPLOY
WHERE TRIM(IDNO) = :emp_id
""",
    """
SELECT TRIM(NAME) AS EMP_NAME
FROM CT_EMPLOY
WHERE TRIM(IDNO) = :emp_id
""",
)

EMP_IDS_BY_NAME_SQLS = (
    """
SELECT TRIM(IDNO) AS IDNO
FROM CT_EMPLOY
WHERE TRIM(NAME) = :emp_name
""",
    """
SELECT TRIM(IDNO) AS IDNO
FROM CT_EMPLOY
WHERE TRIM(NAM) = :emp_name
""",
)

EMP_IDS_BY_NAME_LIKE_SQLS = (
    """
SELECT TRIM(IDNO) AS IDNO
FROM CT_EMPLOY
WHERE TRIM(NAME) LIKE :emp_name_like
""",
    """
SELECT TRIM(IDNO) AS IDNO
FROM CT_EMPLOY
WHERE TRIM(NAM) LIKE :emp_name_like
""",
)

FACTORY_BY_NAME_SQLS = (
    """
SELECT TRIM(FACTORY_PLANT) AS FACTORY_PLANT
FROM CT_EMPLOY
WHERE TRIM(NAME) = :emp_name
""",
    """
SELECT TRIM(FACTORY_PLANT) AS FACTORY_PLANT
FROM CT_EMPLOY
WHERE TRIM(NAM) = :emp_name
""",
)

FACTORY_BY_NAME_ID_SQLS = (
    """
SELECT TRIM(FACTORY_PLANT) AS FACTORY_PLANT
FROM CT_EMPLOY
WHERE TRIM(NAME) = :emp_name
  AND TRIM(IDNO) = :emp_id
""",
    """
SELECT TRIM(FACTORY_PLANT) AS FACTORY_PLANT
FROM CT_EMPLOY
WHERE TRIM(NAM) = :emp_name
  AND TRIM(IDNO) = :emp_id
""",
)

FACTORY_BY_ID_SQLS = (
    """
SELECT TRIM(FACTORY_PLANT) AS FACTORY_PLANT
FROM CT_EMPLOY
WHERE TRIM(IDNO) = :emp_id
""",
)

# ✅ 修正：根據使用者提供之關聯性 (CT_EMPLOY E JOIN CT_DEPARTMENT D) 提取資訊
# 欄位說明：E.IDNO=身分證, E.DEPNO=單位代碼(CIN2000), D.DEPT_NAME=單位名稱, E.EMP_TITLE=職稱
EMP_FULL_INFO_SQL = """
SELECT 
    TRIM(E.NAME) AS EMP_NAME,
    TRIM(E.FACTORY_PLANT) AS PLANT,
    TRIM(D.DEPT_NAME) AS DEPT,
    TRIM(E.EMP_TITLE) AS TITLE
FROM CT_EMPLOY E
LEFT JOIN CT_DEPARTMENT D ON E.DEPNO = D.CIN2000_CODE AND E.FACTORY_PLANT = D.FACTORY_PLANT
WHERE TRIM(E.IDNO) = :emp_id
"""


# ============================================================
# TTL cache（per-emp_id + negative cache + circuit breaker）
# ============================================================
class _EmpCacheEntry(TypedDict):
    ts: float
    ttl: float
    name: str
    full_info: Dict[str, str] | None


_EMP_CACHE: Dict[str, _EmpCacheEntry] = {}
_ORA_DOWN_UNTIL_TS: float = 0.0
_LAST_ERR: str = ""
_MOCK_EMP_CACHE: Dict[str, Any] = {"path": "", "mtime": 0.0, "data": {}}


def _oracle_emp_profile() -> str:
    """
    Employee lookup must always use MPC employee DB and must not follow per-plant DOC DB routing.
    Can be overridden by ORACLE_EMP_DB_PROFILE, default is MPC.
    """
    return (os.getenv("ORACLE_EMP_DB_PROFILE") or "MPC").strip()


def _mock_db_json_path() -> str:
    p = str(getattr(settings, "MOCK_DB_JSON", "") or "").strip()
    if p:
        return p
    p = (os.getenv("MOCK_DB_JSON") or "").strip()
    if p:
        return p
    return "SQLTEST_output.json"


def _load_mock_db_json() -> Dict[str, Any]:
    candidate = Path(_mock_db_json_path())
    paths = [candidate]
    if not candidate.is_absolute():
        paths.append(Path.cwd() / candidate)
    else:
        # cross-host fallback: when configured absolute path does not exist,
        # fallback to current repo mock file.
        paths.append(Path.cwd() / "SQLTEST_output.json")

    p = None
    mtime = None
    for c in paths:
        try:
            if c.exists():
                p = c
                mtime = c.stat().st_mtime
                break
        except Exception:
            continue
    if p is None or mtime is None:
        return {}

    if _MOCK_EMP_CACHE.get("path") == str(p) and _MOCK_EMP_CACHE.get("mtime") == mtime:
        return _MOCK_EMP_CACHE.get("data") or {}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    _MOCK_EMP_CACHE.update({"path": str(p), "mtime": mtime, "data": data})
    return data or {}


def _iter_oracle_emp_sections(data: Dict[str, Any]):
    if not isinstance(data, dict):
        return
    sec = data.get("oracle_emp")
    if sec is not None:
        yield sec

    records = data.get("records")
    if isinstance(records, list):
        for r in records:
            if isinstance(r, dict) and ("oracle_emp" in r):
                yield r.get("oracle_emp")


def _match_mock_emp_from_section(section: Any, emp_id: str) -> Dict[str, str]:
    uid = (emp_id or "").strip().upper()
    if not uid:
        return {}

    def _norm(v: Any) -> str:
        return str(v or "").strip()

    # Case A: {"login_user":"F...","login_user_name":"姚承佑","login_user_org":"401"}
    if isinstance(section, dict):
        lu = _norm(section.get("login_user")).upper()
        if lu and lu == uid:
            return {
                "name": _norm(section.get("login_user_name") or section.get("name")),
                "plant": _norm(section.get("login_user_org") or section.get("factory_plant") or section.get("plant")),
            }

        # Case B: {"F129...":"姚承佑"} or {"F129...":{"login_user_name":"姚承佑","plant":"401"}}
        direct = section.get(emp_id) or section.get(uid) or section.get(uid.lower())
        if isinstance(direct, str):
            return {"name": _norm(direct), "plant": ""}
        if isinstance(direct, dict):
            return {
                "name": _norm(direct.get("login_user_name") or direct.get("name")),
                "plant": _norm(direct.get("login_user_org") or direct.get("factory_plant") or direct.get("plant")),
            }

        # Case C: {"users":[{"login_user":"F...","login_user_name":"姚承佑"}]}
        users = section.get("users")
        if isinstance(users, list):
            for item in users:
                if not isinstance(item, dict):
                    continue
                if _norm(item.get("login_user")).upper() == uid:
                    return {
                        "name": _norm(item.get("login_user_name") or item.get("name")),
                        "plant": _norm(item.get("login_user_org") or item.get("factory_plant") or item.get("plant")),
                    }

    # Case D: [{"login_user":"F...","login_user_name":"姚承佑"}, ...]
    if isinstance(section, list):
        for item in section:
            if not isinstance(item, dict):
                continue
            if _norm(item.get("login_user")).upper() == uid:
                return {
                    "name": _norm(item.get("login_user_name") or item.get("name")),
                    "plant": _norm(item.get("login_user_org") or item.get("factory_plant") or item.get("plant")),
                }
    return {}


def _mock_emp_info(emp_id: str) -> Dict[str, str]:
    data = _load_mock_db_json()
    if not data:
        return {}

    hit: Dict[str, str] = {}
    for sec in _iter_oracle_emp_sections(data):
        matched = _match_mock_emp_from_section(sec, emp_id)
        if matched and (matched.get("name") or matched.get("plant")):
            hit = matched
    return hit


def _pg_query_one(sqls: tuple[str, ...] | str, params: Dict[str, Any]) -> Any:
    if isinstance(sqls, str):
        sqls = (sqls,)
    
    last_err = None
    for sql in sqls:
        pg_sql = re.sub(r':([a-zA-Z_]\w*)', r'%(\1)s', sql)
        conn = None
        cur = None
        db_url = os.environ.get("DATABASE_URL")
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        try:
            conn = db_connect("postgresql", profile="mpcdb")
            cur = conn.cursor()
            cur.execute(pg_sql, params)
            if cur.description:
                columns = [col[0] for col in cur.description]
                row = cur.fetchone()
                if row:
                    return {col.upper(): row[idx] for idx, col in enumerate(columns)}
            else:
                row = cur.fetchone()
                return row
        except Exception as e:
            last_err = e
            continue
        finally:
            if db_url is not None:
                os.environ["DATABASE_URL"] = db_url
            try:
                if cur is not None:
                    cur.close()
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
    if last_err is not None:
        raise last_err
    return None


def _pg_query_all(sqls: tuple[str, ...] | str, params: Dict[str, Any], limit: int = 0) -> list[Any]:
    if isinstance(sqls, str):
        sqls = (sqls,)
    
    last_err = None
    for sql in sqls:
        pg_sql = re.sub(r':([a-zA-Z_]\w*)', r'%(\1)s', sql)
        conn = None
        cur = None
        db_url = os.environ.get("DATABASE_URL")
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        try:
            conn = db_connect("postgresql", profile="mpcdb")
            cur = conn.cursor()
            cur.execute(pg_sql, params)
            
            if limit and limit > 0:
                rows = cur.fetchmany(int(limit))
            else:
                rows = cur.fetchall()
                
            if cur.description:
                columns = [col[0] for col in cur.description]
                out = []
                for r in rows:
                    out.append({col.upper(): r[idx] for idx, col in enumerate(columns)})
                return out
            else:
                return list(rows)
        except Exception as e:
            last_err = e
            continue
        finally:
            if db_url is not None:
                os.environ["DATABASE_URL"] = db_url
            try:
                if cur is not None:
                    cur.close()
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
    if last_err is not None:
        raise last_err
    return []


# ============================================================
# ✅ Settings accessors（專案規範：環境開關集中在 settings.py）
# - 外網/DMZ 必須 0 次 Oracle 連線（fail-fast）
# ============================================================
def _is_oracle_emp_enabled() -> bool:
    """
    依 settings 控制是否允許 Oracle 員工查詢：
    - ORACLE_ENABLED=0 或 ORACLE_EMP_ENABLED=0 => 一律停用（外網/DMZ）
    """
    env_name = (os.getenv("ENV") or "").strip().upper()
    env_name = {
        "DEV": "DEV_EXT",
        "EXT": "DEV_EXT",
        "INT": "DEV_INT",
        "PROD": "PROD_EXT",
    }.get(env_name, env_name)
    if env_name in ("DEV_EXT", "PROD_EXT"):
        return False
    if env_name in ("DEV_INT", "PROD_INT"):
        return True
    return bool(getattr(settings, "ORACLE_ENABLED", False) and getattr(settings, "ORACLE_EMP_ENABLED", False))


def _oracle_query_one_direct(sql: str, params: Dict[str, str]) -> Any:
    db = OracleDB(profile=_oracle_emp_profile())
    conn = db.connect()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        # 轉為 dict 以利存取
        if cur.description:
            columns = [col[0] for col in cur.description]
            row = cur.fetchone()
            if row:
                return dict(zip(columns, row))
        return None
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _oracle_query_all_direct(sql: str, params: Dict[str, str], limit: int = 0) -> list[Any]:
    db = OracleDB(profile=_oracle_emp_profile())
    conn = db.connect()
    cur = None
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        if limit and limit > 0:
            return list(cur.fetchmany(int(limit)))
        return list(cur.fetchall())
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _oracle_query_one_with_fallback(sqls: tuple[str, ...] | str, params: Dict[str, str]) -> Any:
    last_err: Exception | None = None
    if isinstance(sqls, str):
        sqls = (sqls,)
    for sql in sqls:
        try:
            return _oracle_query_one_direct(sql, params)
        except Exception as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    return None


def _oracle_query_all_with_fallback(sqls: tuple[str, ...], params: Dict[str, str], limit: int = 0) -> list[Any]:
    last_err: Exception | None = None
    for sql in sqls:
        try:
            return _oracle_query_all_direct(sql, params, limit=limit)
        except Exception as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    return []


def _emp_cache_ttl_sec() -> float:
    # 正常快取 TTL（預設 1 小時）
    return float(getattr(settings, "ORA_EMP_CACHE_TTL_SEC", 3600))


def _emp_negative_ttl_sec() -> float:
    # Oracle 失敗/查不到時的負快取 TTL（預設 60 秒）
    return float(getattr(settings, "ORA_EMP_NEGATIVE_TTL_SEC", 60.0))


def _fail_cooldown_sec() -> int:
    """
    熔斷 cooldown（優先沿用你 settings 既有的 ORACLE_FAIL_COOLDOWN）
    - 若未定義 ORACLE_FAIL_COOLDOWN，才用 ORA_EMP_FAIL_COOLDOWN_SEC
    """
    v = getattr(settings, "ORACLE_FAIL_COOLDOWN", None)
    if v is None:
        v = getattr(settings, "ORA_EMP_FAIL_COOLDOWN_SEC", 60)
    try:
        return max(5, int(v))
    except Exception:
        return 60


def _cache_get_if_valid(emp_id: str) -> str | None:
    ent = _EMP_CACHE.get(emp_id)
    if not ent:
        return None
    now = time.time()
    ts = float(ent.get("ts") or 0.0)
    ttl = float(ent.get("ttl") or 0.0)
    if (now - ts) <= ttl:
        return str(ent.get("name") or "").strip()
    return None


def _cache_get_full_if_valid(emp_id: str) -> Dict[str, str] | None:
    ent = _EMP_CACHE.get(emp_id)
    if not ent:
        return None
    now = time.time()
    ts = float(ent.get("ts") or 0.0)
    ttl = float(ent.get("ttl") or 0.0)
    if (now - ts) <= ttl:
        return ent.get("full_info")
    return None


def _cache_put(emp_id: str, name: str, ttl: float, full_info: Dict[str, str] | None = None) -> None:
    _EMP_CACHE[emp_id] = {
        "ts": time.time(),
        "ttl": float(ttl),
        "name": (name or "").strip(),
        "full_info": full_info
    }


def get_emp_name(emp_id: str, *, refresh: bool = False) -> str:
    """
    依 IDNO 取得人員姓名
    """
    global _LAST_ERR, _ORA_DOWN_UNTIL_TS

    emp_id = (emp_id or "").strip()
    if not emp_id:
        return ""

    if not refresh:
        hit = _cache_get_if_valid(emp_id)
        if hit is not None:
            return hit

    if not _is_oracle_emp_enabled():
        try:
            res = _pg_query_one(EMP_NAME_SQLS, {"emp_id": emp_id})
            name = ""
            if isinstance(res, dict):
                name = str(res.get("EMP_NAME") or "").strip()
            elif res:
                name = str(res[0] or "").strip()
            
            if not name:
                name = str(_mock_emp_info(emp_id).get("name") or "").strip()
            _cache_put(emp_id, name, _emp_cache_ttl_sec())
            return name
        except Exception as e:
            logger.warning(f"PostgreSQL get_emp_name failed: {e}")
            name = str(_mock_emp_info(emp_id).get("name") or "").strip()
            _cache_put(emp_id, name, _emp_cache_ttl_sec())
            return name

    now = time.time()
    if _ORA_DOWN_UNTIL_TS and now < _ORA_DOWN_UNTIL_TS:
        cached = _cache_get_if_valid(emp_id)
        return cached if cached is not None else ""

    try:
        res = _oracle_query_one_with_fallback(EMP_NAME_SQLS, {"emp_id": emp_id})
        name = ""
        if isinstance(res, dict):
            name = str(res.get("EMP_NAME") or "").strip()
        elif res:
            name = str(res[0] or "").strip()

        _cache_put(emp_id, name, _emp_cache_ttl_sec())
        _LAST_ERR = ""
        return name

    except Exception as e:
        _LAST_ERR = str(e)
        cooldown = _fail_cooldown_sec()
        _ORA_DOWN_UNTIL_TS = now + cooldown
        old = _EMP_CACHE.get(emp_id, {}).get("name", "")
        _cache_put(emp_id, str(old or "").strip(), _emp_negative_ttl_sec())
        return str(old or "").strip()


def get_emp_full_info(emp_id: str, *, refresh: bool = False) -> Dict[str, str]:
    """
    取得人員完整資訊（姓名、中心/廠、單位名稱、職稱）
    """
    global _LAST_ERR, _ORA_DOWN_UNTIL_TS
    emp_id = (emp_id or "").strip()
    if not emp_id:
        return {}
    if not refresh:
        hit = _cache_get_full_if_valid(emp_id)
        if hit: return hit

    if not _is_oracle_emp_enabled():
        try:
            info = _pg_query_one(EMP_FULL_INFO_SQL, {"emp_id": emp_id})
            if info and isinstance(info, dict):
                res_dict = {
                    "EMP_NAME": str(info.get("EMP_NAME") or "").strip(),
                    "PLANT": str(info.get("PLANT") or "").strip(),
                    "DEPT": str(info.get("DEPT") or "").strip(),
                    "TITLE": str(info.get("TITLE") or "").strip(),
                }
                _cache_put(emp_id, res_dict["EMP_NAME"], _emp_cache_ttl_sec(), full_info=res_dict)
                return res_dict
            
            hit = _mock_emp_info(emp_id)
            if hit:
                res_dict = {
                    "EMP_NAME": str(hit.get("name") or "").strip(),
                    "PLANT": str(hit.get("plant") or "").strip(),
                    "DEPT": "",
                    "TITLE": "",
                }
                _cache_put(emp_id, res_dict["EMP_NAME"], _emp_cache_ttl_sec(), full_info=res_dict)
                return res_dict
            return {}
        except Exception as e:
            logger.warning(f"PostgreSQL get_emp_full_info failed: {e}")
            hit = _mock_emp_info(emp_id)
            if not hit:
                return {}
            res_dict = {
                "EMP_NAME": str(hit.get("name") or "").strip(),
                "PLANT": str(hit.get("plant") or "").strip(),
                "DEPT": "",
                "TITLE": "",
            }
            _cache_put(emp_id, res_dict["EMP_NAME"], _emp_cache_ttl_sec(), full_info=res_dict)
            return res_dict

    now = time.time()
    if _ORA_DOWN_UNTIL_TS and now < _ORA_DOWN_UNTIL_TS:
        return _cache_get_full_if_valid(emp_id) or {}

    try:
        info = _oracle_query_one_with_fallback(EMP_FULL_INFO_SQL, {"emp_id": emp_id})
        if info and isinstance(info, dict):
            _cache_put(emp_id, info.get("EMP_NAME", ""), _emp_cache_ttl_sec(), full_info=info)
            return info
        return {}
    except Exception as e:
        _LAST_ERR = str(e)
        _ORA_DOWN_UNTIL_TS = now + _fail_cooldown_sec()
        return {}


def find_emp_ids_by_name(emp_name: str, *, limit: int = 20) -> list[str]:
    """
    Lookup employee IDNO by Chinese name (CT_EMPLOY.NAME).
    """
    global _LAST_ERR, _ORA_DOWN_UNTIL_TS

    name = (emp_name or "").strip()
    if not name:
        return []
    n = max(1, min(int(limit or 20), 200))

    def _row_id(v: Any) -> str:
        if isinstance(v, dict):
            return str(v.get("IDNO") or v.get("idno") or "").strip()
        try:
            if hasattr(v, "_mapping"):
                m = v._mapping
                for k in ("IDNO", "idno"):
                    if k in m and m.get(k) is not None:
                        return str(m.get(k)).strip()
        except Exception:
            pass
        try:
            return str(v[0] or "").strip()
        except Exception:
            return ""

    if not _is_oracle_emp_enabled():
        try:
            rows = _pg_query_all(EMP_IDS_BY_NAME_SQLS, {"emp_name": name}, limit=n)
            if not rows:
                rows = _pg_query_all(
                    EMP_IDS_BY_NAME_LIKE_SQLS,
                    {"emp_name_like": f"%{name}%"},
                    limit=n,
                )
            seen = set()
            out: list[str] = []
            for r in rows or []:
                emp_id = _row_id(r)
                if not emp_id or emp_id in seen:
                    continue
                seen.add(emp_id)
                out.append(emp_id)
                if len(out) >= n:
                    break
            return out
        except Exception as e:
            logger.warning(f"PostgreSQL find_emp_ids_by_name failed: {e}")
            return []

    now = time.time()

    try:
        rows = _oracle_query_all_with_fallback(EMP_IDS_BY_NAME_SQLS, {"emp_name": name}, limit=n)
        if not rows:
            rows = _oracle_query_all_with_fallback(
                EMP_IDS_BY_NAME_LIKE_SQLS,
                {"emp_name_like": f"%{name}%"},
                limit=n,
            )

        seen = set()
        out: list[str] = []
        for r in rows or []:
            emp_id = _row_id(r)
            if not emp_id or emp_id in seen:
                continue
            seen.add(emp_id)
            out.append(emp_id)
            if len(out) >= n:
                break
        _LAST_ERR = ""
        return out

    except Exception as e:
        _LAST_ERR = str(e)
        cooldown = _fail_cooldown_sec()
        _ORA_DOWN_UNTIL_TS = now + cooldown
        return []


def _row_factory_plant(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("FACTORY_PLANT") or v.get("factory_plant") or "").strip()
    try:
        if hasattr(v, "_mapping"):
            m = v._mapping
            for k in ("FACTORY_PLANT", "factory_plant"):
                if k in m and m.get(k) is not None:
                    return str(m.get(k)).strip()
    except Exception:
        pass
    try:
        return str(v[0] or "").strip()
    except Exception:
        return ""


def get_factory_plant_by_name(emp_name: str, *, emp_id: str = "") -> str:
    """
    Lookup FACTORY_PLANT from CT_EMPLOY using Chinese name.
    """
    global _LAST_ERR, _ORA_DOWN_UNTIL_TS

    name = (emp_name or "").strip()
    emp_id = (emp_id or "").strip()
    if not name:
        return ""
    if not _is_oracle_emp_enabled():
        try:
            row = None
            if emp_id:
                row = _pg_query_one(
                    FACTORY_BY_NAME_ID_SQLS,
                    {"emp_name": name, "emp_id": emp_id},
                )
            if not row:
                row = _pg_query_one(
                    FACTORY_BY_NAME_SQLS,
                    {"emp_name": name},
                )
            plant = _row_factory_plant(row) if row else ""
            return plant
        except Exception as e:
            logger.warning(f"PostgreSQL get_factory_plant_by_name failed: {e}")
            return ""

    now = time.time()

    try:
        row = None
        if emp_id:
            row = _oracle_query_one_with_fallback(
                FACTORY_BY_NAME_ID_SQLS,
                {"emp_name": name, "emp_id": emp_id},
            )
        if not row:
            row = _oracle_query_one_with_fallback(
                FACTORY_BY_NAME_SQLS,
                {"emp_name": name},
            )

        plant = _row_factory_plant(row) if row else ""
        _LAST_ERR = ""
        return plant
    except Exception as e:
        _LAST_ERR = str(e)
        _ORA_DOWN_UNTIL_TS = now + _fail_cooldown_sec()
        return ""


def get_factory_plant_by_id(emp_id: str) -> str:
    """
    Fallback lookup FACTORY_PLANT by IDNO.
    """
    global _LAST_ERR, _ORA_DOWN_UNTIL_TS

    uid = (emp_id or "").strip()
    if not uid:
        return ""
    if not _is_oracle_emp_enabled():
        try:
            row = _pg_query_one(FACTORY_BY_ID_SQLS, {"emp_id": uid})
            plant = _row_factory_plant(row) if row else ""
            if not plant:
                plant = str(_mock_emp_info(uid).get("plant") or "").strip()
            return plant
        except Exception as e:
            logger.warning(f"PostgreSQL get_factory_plant_by_id failed: {e}")
            return str(_mock_emp_info(uid).get("plant") or "").strip()

    now = time.time()
    if _ORA_DOWN_UNTIL_TS and now < _ORA_DOWN_UNTIL_TS:
        return ""

    try:
        row = _oracle_query_one_with_fallback(FACTORY_BY_ID_SQLS, {"emp_id": uid})
        plant = _row_factory_plant(row) if row else ""
        _LAST_ERR = ""
        return plant
    except Exception as e:
        _LAST_ERR = str(e)
        _ORA_DOWN_UNTIL_TS = now + _fail_cooldown_sec()
        return ""


def get_last_error() -> str:
    """除錯用：最近一次 Oracle 存取錯誤訊息（如果有）"""
    return (_LAST_ERR or "").strip()


def clear_cache() -> None:
    """除錯/測試用：清空快取 + 熔斷狀態"""
    global _LAST_ERR, _ORA_DOWN_UNTIL_TS
    _EMP_CACHE.clear()
    _LAST_ERR = ""
    _ORA_DOWN_UNTIL_TS = 0.0
