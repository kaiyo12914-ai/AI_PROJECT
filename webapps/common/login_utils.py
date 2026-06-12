from __future__ import annotations

import os
import re
from typing import Any, Optional

from django.http import HttpRequest


def _env_bool(key: str, default: bool = False) -> bool:
    v = (os.getenv(key) or ("1" if default else "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _env_str(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


def normalize_org_code(raw: str, default: str = "") -> str:
    s = str(raw or "").strip().upper()
    if not s:
        return default
    if s == "PC":
        return "MPC"
    if s in {"MPC", "202", "205", "209", "401"}:
        return s
    if s in {"MNDQ", "MNDV", "MNDI"}:
        return {"MNDQ": "205", "MNDV": "209", "MNDI": "401"}[s]
    compact = re.sub(r"[^A-Z0-9]+", "", s)
    if compact == "PC":
        return "MPC"
    if compact in {"MPC", "202", "205", "209", "401"}:
        return compact
    if compact in {"MNDQ", "MNDV", "MNDI"}:
        return {"MNDQ": "205", "MNDV": "209", "MNDI": "401"}[compact]
    m = re.search(r"(202|205|209|401)", compact)
    if m:
        return m.group(1)
    if "MPC" in compact:
        return "MPC"
    return default


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
    1) request.login_user
    2) RemoteUser username (request.user.username)
    3) AAA header/query/cookie decode fallback
    4) DEV fallback (local dev only)
    5) empty string
    """
    try:
        v = getattr(request, "login_user", None)
        if v is not None:
            s = str(v).strip()
            if s:
                if s.upper().startswith("MPC-"):
                    s = s[4:].strip()
                return s
    except Exception:
        pass

    try:
        u = get_effective_user(request)
        if u is not None:
            name = getattr(u, "username", None)
            if name is not None:
                s = str(name).strip()
                if s:
                    if s.upper().startswith("MPC-"):
                        s = s[4:].strip()
                    return s
    except Exception:
        pass

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
                from webapps.portal.middleware import _strip_domain
                s = _strip_domain(decoded)
                if s.upper().startswith("MPC-"):
                    s = s[4:].strip()
                return s
    except Exception:
        pass

    dev = _dev_login_user()
    if dev:
        if dev.upper().startswith("MPC-"):
            dev = dev[4:].strip()
        return dev

    return ""


def get_login_user_name(request: HttpRequest) -> str:
    try:
        n = getattr(request, "login_user_name", None)
        if n is not None:
            s = str(n).strip()
            if s:
                return s
    except Exception:
        pass

    emp_id = get_login_user_idno(request)
    if not emp_id:
        return ""

    try:
        from webapps.portal.oracle_emp import get_emp_name, get_factory_plant_by_id

        name = (get_emp_name(emp_id) or "").strip()
        if name:
            plant = normalize_org_code(get_factory_plant_by_id(emp_id) or "", default="")
            if plant:
                return f"{plant}-{name}"
            return name
    except Exception:
        pass

    return emp_id


def get_login_user_org(request: HttpRequest) -> str:
    env_val = (os.getenv("ENV") or os.getenv("ENX") or "").strip().upper()
    if env_val == "EXT" and get_login_user_idno(request):
        return "MPC"

    try:
        v = getattr(request, "login_user_org", None)
        if v is not None:
            s = normalize_org_code(str(v).strip(), default="")
            if s:
                return s
    except Exception:
        pass

    try:
        s = normalize_org_code(str(request.session.get("login_user_org") or "").strip(), default="")
        if s:
            return s
    except Exception:
        pass

    try:
        name = str(getattr(request, "login_user_name", "") or "").strip().upper()
        s = normalize_org_code(name, default="")
        if s:
            return s
    except Exception:
        pass

    emp_id = get_login_user_idno(request)
    if not emp_id:
        return ""

    try:
        from webapps.portal.oracle_emp import get_factory_plant_by_id

        return normalize_org_code((get_factory_plant_by_id(emp_id) or "").strip(), default="")
    except Exception:
        return ""
