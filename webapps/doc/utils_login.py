# webapps/doc/utils_login.py
from __future__ import annotations

import os
from typing import Optional, Any

from django.http import HttpRequest


def _env_bool(key: str, default: bool = False) -> bool:
    v = (os.getenv(key) or ("1" if default else "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def _dev_login_user() -> str:
    """
    Development-only fallback IDNO.
    - Enabled when DEBUG=1 or DEV_LOGIN_ENABLED=1
    - Reads DEV_LOGIN_USER as fallback login IDNO
    """
    if not (_env_bool("DEBUG", False) or _env_bool("DEV_LOGIN_ENABLED", False)):
        return ""
    return _env_str("DEV_LOGIN_USER", "")


def get_effective_user(request: HttpRequest) -> Optional[Any]:
    """
    Return authenticated Django user from RemoteUser auth flow.
    - Usually populated by RemoteUserMiddleware + RemoteUserBackend
    - Returns None when unauthenticated or unavailable
    """
    try:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return user
    except Exception:
        pass
    return None


def get_login_user_idno(request: HttpRequest) -> str:
    """
    Resolve current login user IDNO by priority:
    1) request.login_user (project convention)
    2) RemoteUser username (request.user.username)
    3) AAA header/query/cookie decode fallback
    4) DEV fallback (local dev only)
    5) empty string
    """
    # 1) project convention
    try:
        v = getattr(request, "login_user", None)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    except Exception:
        pass

    # 2) RemoteUser / Django auth
    try:
        u = get_effective_user(request)
        if u is not None:
            name = getattr(u, "username", None)
            if name is not None:
                s = str(name).strip()
                if s:
                    return s
    except Exception:
        pass

    # 3) aaa fallback (if middleware did not set login_user)
    try:
        aaa = (
            request.META.get("HTTP_X_AAA")
            or request.META.get("HTTP_AAA")
            or request.GET.get("aaa")
            or request.COOKIES.get("aaa")
            or ""
        ).strip()
        if aaa:
            from webapps.portal.utils import aaadecode

            decoded = (aaadecode(aaa) or "").strip()
            if decoded:
                return decoded
    except Exception:
        pass

    # 4) DEV fallback (local dev only)
    dev = _dev_login_user()
    if dev:
        return dev

    return ""


def get_login_user_name(request: HttpRequest) -> str:
    """
    Resolve display name for UI by priority:
    1) request.login_user_name if middleware already filled it
    2) Oracle lookup via oracle_emp
    3) fallback to IDNO
    """
    # 1) middleware already set
    try:
        n = getattr(request, "login_user_name", None)
        if n is not None:
            s = str(n).strip()
            if s:
                return s
    except Exception:
        pass

    # 2) oracle lookup (optional)
    emp_id = get_login_user_idno(request)
    if not emp_id:
        return ""

    try:
        from webapps.portal.oracle_emp import get_emp_name, get_factory_plant_by_id  # lazy import
        name = (get_emp_name(emp_id) or "").strip()
        if name:
            plant = (get_factory_plant_by_id(emp_id) or "").strip()
            if plant:
                return f"{plant}-{name}"
            return name
    except Exception:
        pass

    # 3) fallback
    return emp_id if emp_id else ""


def get_login_user_org(request: HttpRequest) -> str:
    """
    Resolve current login user's org/plant code for cross-module use.
    Returns normalized code: MPC / 202 / 205 / 209 / 401 (or "").
    Priority:
    1) request.login_user_org (middleware standard field)
    2) session.login_user_org
    3) parse from login_user_name prefix (e.g. "MPC-王小明", "209-王小明")
    4) Oracle lookup by IDNO
    """
    try:
        v = getattr(request, "login_user_org", None)
        if v is not None:
            s = str(v).strip().upper()
            if s:
                return s
    except Exception:
        pass

    try:
        s = str((request.session.get("login_user_org") or "")).strip().upper()
        if s:
            return s
    except Exception:
        pass

    try:
        name = str(getattr(request, "login_user_name", "") or "").strip().upper()
        if name:
            if "MPC" in name:
                return "MPC"
            import re

            m = re.search(r"(202|205|209|401)", name)
            if m:
                return m.group(1)
    except Exception:
        pass

    emp_id = get_login_user_idno(request)
    if not emp_id:
        return ""
    try:
        from webapps.portal.oracle_emp import get_factory_plant_by_id
        from webapps.doc.services.doc_db_router import normalize_doc_plant

        return normalize_doc_plant((get_factory_plant_by_id(emp_id) or "").strip(), default="")
    except Exception:
        return ""


def get_plant_arg(request: HttpRequest) -> str:
    """
    Read plant from request (GET, POST, or JSON body).
    """
    import json
    p = (request.GET.get("plant") or request.POST.get("plant") or "").strip()
    if not p:
        try:
            body = json.loads((request.body or b"").decode("utf-8") or "{}")
            p = (body.get("plant") or "").strip()
        except Exception:
            pass
    return p
