# webapps/portal/acl.py
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Set, Tuple

from django.conf import settings

from webapps.database.db_factory import db_query_all


# ============================================================
# Backend resolution
# ============================================================
def _model_type() -> str:
    return (getattr(settings, "MODEL_TYPE", "") or "OLLAMA").strip().upper()


def _backend() -> str:
    """
    settings.PORTAL_ACL_BACKEND:
      - AUTO   : MODEL_TYPE=OLLAMA -> ORACLE ; MODEL_TYPE=OPENAI -> DJANGO
      - ORACLE : force oracle tables
      - DJANGO : force django auth_group/auth_user_groups
    """
    v = (getattr(settings, "PORTAL_ACL_BACKEND", "") or "AUTO").strip().upper()
    if v in ("AUTO", "ORACLE", "DJANGO"):
        return v
    return "AUTO"


def _effective_backend() -> str:
    # ✅ 若 settings.py 已算好 ACL_BACKEND_EFFECTIVE，就優先用（避免兩邊算的不一致）
    v = (getattr(settings, "ACL_BACKEND_EFFECTIVE", "") or "").strip().upper()
    if v in ("ORACLE", "DJANGO"):
        return v

    b = _backend()
    if b != "AUTO":
        return b
    return "ORACLE" if _model_type() == "OLLAMA" else "DJANGO"


# ============================================================
# TTL cache（避免 Oracle 掛掉時每個 request 都卡住）
# ============================================================
# cache_key = (backend, username)
# value:
#   {
#     "ts": float,
#     "ttl": float,
#     "groups": Set[str],
#     "note": str,   # optional debug label
#   }
_ACL_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _is_ext_env() -> bool:
    env_name = str(
        getattr(settings, "ENV_NAME", "") or os.getenv("ENV", "")
    ).strip().upper()
    return env_name == "EXT"


def _oracle_acl_db_profile() -> str:
    return str(
        getattr(settings, "ORACLE_ACL_DB_PROFILE", "") or os.getenv("ORACLE_ACL_DB_PROFILE", "") or "ERP_MPC"
    ).strip()


def _mock_db_json_path() -> str:
    p = str(getattr(settings, "MOCK_DB_JSON", "") or "").strip()
    if p:
        return p
    p = (os.getenv("MOCK_DB_JSON") or "").strip()
    if p:
        return p
    return "SQLTEST_output.json"


def _load_oracle_acl_groups_from_mock() -> Set[str]:
    candidate = Path(_mock_db_json_path())
    paths = [candidate]
    if not candidate.is_absolute():
        paths.append(Path.cwd() / candidate)
    else:
        # When configured absolute path does not exist on current host,
        # fallback to local repo mock file.
        paths.append(Path.cwd() / "SQLTEST_output.json")

    data: Dict[str, Any] | None = None
    for p in paths:
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                break
        except Exception:
            continue
    if not isinstance(data, dict):
        return set()

    sections: list[Any] = []
    if isinstance(data, dict):
        if "oracle_acl" in data:
            sections.append(data.get("oracle_acl"))
        recs = data.get("records")
        if isinstance(recs, list):
            for r in recs:
                if isinstance(r, dict) and ("oracle_acl" in r):
                    sections.append(r.get("oracle_acl"))

    for sec in reversed(sections):
        if not isinstance(sec, dict):
            continue
        groups = sec.get("groups")
        if isinstance(groups, list):
            out = {str(x or "").strip() for x in groups if str(x or "").strip()}
            if out:
                return out
    return set()


def _acl_cache_ttl() -> float:
    # 正常 TTL：預設 10 分鐘
    try:
        return float(getattr(settings, "PORTAL_ACL_CACHE_TTL_SEC", 600) or 600)
    except Exception:
        return 600.0


def _acl_cache_negative_ttl() -> float:
    # Oracle 失敗/超時時的負快取：預設 60 秒（避免瞬間打爆/卡死）
    try:
        return float(getattr(settings, "PORTAL_ACL_NEGATIVE_TTL_SEC", 60) or 60)
    except Exception:
        return 60.0


# ============================================================
# Group resolvers
# ============================================================
def _is_authenticated(user) -> bool:
    try:
        return bool(user and user.is_authenticated)
    except Exception:
        return False


def _get_user_groups_from_django(user) -> Set[str]:
    """
    讀 Django 內建 auth tables 的群組名稱 (auth_group.name)
    """
    if not _is_authenticated(user):
        return set()
    try:
        return set(user.groups.values_list("name", flat=True))
    except Exception:
        return set()


# 僅允許 table/col 簡單識別子（避免被注入）
_SAFE_IDENT = re.compile(r"^[A-Za-z0-9_\.]+$")


def _oracle_acl_query_timeout_sec() -> float:
    """
    ✅ Oracle 查 ACL 的「慢查視為失敗」上限秒數（soft timeout）
    - 真正硬 timeout 需靠 driver/socket timeout（db_factory Oracle connect 已設 timeout）
    """
    try:
        # INT 環境下 Oracle ACL 查詢常超過 0.8s，調高預設避免誤判為 timeout
        return float(getattr(settings, "PORTAL_ACL_ORACLE_QUERY_TIMEOUT_SEC", 3.0) or 3.0)
    except Exception:
        return 3.0


def _oracle_acl_sql(table: str, user_col: str, group_col: str) -> str:
    """
    ✅ oracledb / DBFactory：請用 named bind (:username)
    """
    return f"""
        SELECT {group_col}
        FROM {table}
        WHERE {user_col} = :login_user
    """


def _rows_to_group_set(rows: Any) -> Set[str]:
    out: Set[str] = set()
    for r in rows or []:
        if not r:
            continue
        try:
            v = r[0]
        except Exception:
            continue
        s = str(v or "").strip()
        if s:
            out.add(s)
    return out


def _get_user_groups_from_oracle_uncached(user) -> Set[str]:
    """
    ✅ 改走 DBFactory（統一 DB 連線）
    settings keys:
      ORA_ACL_TABLE / ORA_ACL_USER_COL / ORA_ACL_GROUP_COL

    注意：
    - Oracle db_factory 使用 oracledb thin
    - placeholder 必須用 :name 或 :1，不可用 '?'
    - table/col 僅允許 A-Z a-z 0-9 _ .（避免注入）
    """
    if not _is_authenticated(user):
        return set()

    username = (getattr(user, "username", None) or "").strip()
    if not username:
        return set()

    # Strip MPC- prefix if present for Oracle ACL query safety
    if username.upper().startswith("MPC-"):
        username = username[4:].strip()

    table = (getattr(settings, "ORA_ACL_TABLE", None) or "VIEW_ZZ_USER_GROUP_ACL").strip()
    user_col = (getattr(settings, "ORA_ACL_USER_COL", None) or "USER_ID").strip()
    group_col = (getattr(settings, "ORA_ACL_GROUP_COL", None) or "GROUP_NAME").strip()

    if not (_SAFE_IDENT.match(table) and _SAFE_IDENT.match(user_col) and _SAFE_IDENT.match(group_col)):
        # 不符合白名單：直接拒絕（安全）
        return set()

    # EXT policy: do not query Oracle ACL; use mock groups only.
    if _is_ext_env():
        return _load_oracle_acl_groups_from_mock()

    def _query_groups(col: str) -> Set[str]:
        sql = _oracle_acl_sql(table, col, group_col)
        rows = db_query_all("oracle", sql, {"login_user": username}, profile=_oracle_acl_db_profile()) or []
        return _rows_to_group_set(rows)

    # ✅ soft timeout + negative cache：避免 Oracle 慢/掛導致 request 卡死
    t0 = time.monotonic()
    groups = _query_groups(user_col)
    if not groups and user_col.upper() != "USERNAME":
        try:
            groups = _query_groups("USERNAME")
        except Exception:
            pass
    dt = time.monotonic() - t0

    if dt > _oracle_acl_query_timeout_sec():
        raise TimeoutError(f"oracle acl query slow dt={dt:.3f}s > limit")

    return groups


def _get_user_groups_from_oracle(user) -> Set[str]:
    """
    ✅ 有 TTL cache + negative cache 的版本
    - Oracle 掛掉/很慢：短時間內直接回空，避免每個 request 都卡住
    """
    if not _is_authenticated(user):
        return set()

    username = (getattr(user, "username", None) or "").strip()
    if not username:
        return set()

    b = "ORACLE"
    now = time.time()
    key = (b, username)

    ent = _ACL_CACHE.get(key)
    if ent:
        ts = float(ent.get("ts") or 0.0)
        ttl = float(ent.get("ttl") or 0.0)
        if (now - ts) <= ttl:
            g = ent.get("groups")
            if isinstance(g, set):
                return g
            try:
                return set(g or [])
            except Exception:
                return set()

    # cache miss / expired -> refresh
    try:
        groups = _get_user_groups_from_oracle_uncached(user)
        _ACL_CACHE[key] = {
            "ts": now,
            "ttl": _acl_cache_ttl(),
            "groups": set(groups),
            "note": "ok",
        }
        return groups
    except Exception:
        # ✅ 負快取：避免 Oracle 不通時每次都打/都卡
        _ACL_CACHE[key] = {
            "ts": now,
            "ttl": _acl_cache_negative_ttl(),
            "groups": set(),  # fail -> empty
            "note": "fail",
        }
        return set()


def get_user_groups(user) -> Set[str]:
    """
    統一入口：依 effective backend 決定從哪裡讀 groups
    """
    b = _effective_backend()
    if b == "ORACLE":
        return _get_user_groups_from_oracle(user)
    return _get_user_groups_from_django(user)


# ============================================================
# ACL evaluation
# ============================================================
def _to_bool(v: Any) -> bool:
    """
    ✅ 兼容 .env 常見：FALSE/TRUE、0/1、off/on、yes/no
    """
    if isinstance(v, bool):
        return v

    s = str(v or "").strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off", ""):
        return False

    # fallback：不要亂放行
    return bool(v)


def _acl_enabled() -> bool:
    """
    ✅ 專案規範：
      0/False -> 全部開放
      1/True  -> 控管權限

    ⚠️ 安全預設：若沒設定，應視為「啟用控管」
    - 避免上線忘記設 env 造成全開放
    """
    return _to_bool(getattr(settings, "PORTAL_ACL_ENABLED", True))


def _acl_map() -> Dict[str, Any]:
    return getattr(settings, "PORTAL_ACL", {}) or {}


def _normalize_groups(groups: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for g in groups or []:
        s = (g or "").strip()
        if s:
            out.add(s)
    return out


def can_access(user, node: str) -> bool:
    """
    ✅ 入口/功能是否可用：由 settings.PORTAL_ACL 控
    特殊群組：
      - PUBLIC             : 不需登入
      - ALL_AUTHENTICATED  : 只要登入即可
    """
    # ✅ ACL 關閉：全部放行（含未登入），符合你 .env 註解
    if not _acl_enabled():
        return True

    node = (node or "").strip()
    if not node:
        return False

    rule = _acl_map().get(node)
    if rule is None:
        # 沒寫規則：預設拒絕（安全）
        return False

    allow_groups = _normalize_groups(rule)

    # PUBLIC：直接放行
    if "PUBLIC" in allow_groups:
        return True

    # 其餘都要登入
    if not _is_authenticated(user):
        return False

    # ALL_AUTHENTICATED：登入即放行
    if "ALL_AUTHENTICATED" in allow_groups:
        return True

    # 否則比對羣組
    user_groups = get_user_groups(user)
    return bool(user_groups.intersection(allow_groups))


# ============================================================
# Optional: debug helper
# ============================================================
def acl_debug(user) -> Dict[str, Any]:
    """
    方便你在 shell / debug 看目前 ACL 狀態
    """
    username = (getattr(user, "username", None) or "").strip()
    ent = _ACL_CACHE.get(("ORACLE", username)) if username else None
    return {
        "enabled": _acl_enabled(),
        "backend": _effective_backend(),
        "model_type": _model_type(),
        "login_user": getattr(user, "username", None),
        "is_authenticated": _is_authenticated(user),
        "groups": sorted(get_user_groups(user)),
        "cache_ttl_sec": _acl_cache_ttl(),
        "negative_ttl_sec": _acl_cache_negative_ttl(),
        "oracle_query_limit_sec": _oracle_acl_query_timeout_sec(),
        "cache_note": (ent or {}).get("note"),
    }
