# webapps/portal/oracle_emp.py
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, TypedDict

from django.conf import settings

# ✅ DB 連線必須走 DB_FACTORY（專案規範）
from webapps.database.db_factory import OracleDB

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
SELECT TRIM(NAM) AS EMP_NAME
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


def _oracle_emp_profile() -> str:
    """
    Employee lookup must always use MPC employee DB and must not follow per-plant DOC DB routing.
    Can be overridden by ORACLE_EMP_DB_PROFILE, default is MPC.
    """
    return (os.getenv("ORACLE_EMP_DB_PROFILE") or "MPC").strip()


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

    if not _is_oracle_emp_enabled():
        return ""

    if not refresh:
        hit = _cache_get_if_valid(emp_id)
        if hit is not None:
            return hit

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
    if not emp_id or not _is_oracle_emp_enabled():
        return {}

    if not refresh:
        hit = _cache_get_full_if_valid(emp_id)
        if hit: return hit

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
    if not _is_oracle_emp_enabled():
        return []

    now = time.time()
    if _ORA_DOWN_UNTIL_TS and now < _ORA_DOWN_UNTIL_TS:
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
        return ""

    now = time.time()
    if _ORA_DOWN_UNTIL_TS and now < _ORA_DOWN_UNTIL_TS:
        return ""

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
        return ""

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
