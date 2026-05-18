# webapps/portal/middleware.py
from __future__ import annotations

import logging
import os
import ipaddress
import socket
import time
import re
import json
from typing import Optional, Tuple, Dict, Any

from django.conf import settings
from django.utils import timezone

from webapps.portal.models import PortalUsageLog
from webapps.portal.oracle_emp import get_emp_full_info

logger = logging.getLogger(__name__)


# ============================================================
# aaa decode嚗????? debug嚗??雿?乩蜓瘚?嚗?# ============================================================
def aaadecode(aaa: Optional[str]) -> str:
    if not aaa:
        return ""
    return aaa[::2]


def _env_bool(key: str, default: bool = False) -> bool:
    v = (os.getenv(key) or ("1" if default else "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _strip_domain(user: str) -> str:
    user = (user or "").strip().strip('"').strip("'")
    if not user:
        return ""
    # DOMAIN\user
    if "\\" in user:
        user = user.split("\\", 1)[-1].strip()
    # DOMAIN/user
    if "/" in user and not user.startswith("/"):
        left, right = user.split("/", 1)
        if left and right:
            user = right.strip()
    # user@domain
    if "@" in user:
        user = user.split("@", 1)[0].strip()
    return user


def _pick_remote_user(request) -> str:
    """
    IIS/Reverse proxy fallback identity headers.
    Keep this independent from aaa so display name won't break when aaa/query is stripped.
    """
    keys = (
        "REMOTE_USER",
        "AUTH_USER",
        "LOGON_USER",
        "HTTP_X_FORWARDED_USER",
        "HTTP_X_REMOTE_USER",
        "HTTP_X_AUTH_USER",
        "HTTP_X_LOGON_USER",
        "HTTP_X_MS_CLIENT_PRINCIPAL_NAME",
        "HTTP_REMOTE_USER",
    )
    for k in keys:
        v = (request.META.get(k) or "").strip()
        if v:
            return _strip_domain(v)
    return ""


def _normalize_display_name(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return ""
    if "-" in s:
        prefix, rest = s.split("-", 1)
        prefix = (prefix or "").strip().upper()
        if prefix == "PC":
            prefix = "MPC"
        rest = (rest or "").strip()
        if prefix and rest:
            return f"{prefix}-{rest}"
    return s


def _name_from_aaa_decoded(aaa_decoded: str) -> str:
    s = _strip_domain(aaa_decoded or "")
    if not s:
        return ""
    if re.search(r"[\u4e00-\u9fff]", s):
        return _normalize_display_name(s)
    return ""


# ============================================================
# ??Emp name cache + Oracle down circuit breaker
# ============================================================
_EMP_NAME_CACHE = {
    "ttl_sec": float(getattr(settings, "EMP_NAME_CACHE_TTL_SEC", 3600.0)),
    "map": {},
}

_ORA_DOWN_UNTIL = {
    "ts": 0.0
}


def _normalize_plant_label(plant: str) -> str:
    p = (plant or "").strip().upper()
    if p == "MPC":
        return "MPC"
    return p


def _normalize_org_code(plant: str) -> str:
    p = _normalize_plant_label(plant)
    if not p:
        return ""
    if p == "PC":
        return "MPC"
    if p in {"MPC", "202", "205", "209", "401"}:
        return p
    m = re.search(r"(202|205|209|401)", p)
    if m:
        return m.group(1)
    if "MPC" in p:
        return "MPC"
    return ""


def _org_label(org_code: str) -> str:
    c = _normalize_org_code(org_code)
    if not c:
        return ""
    if c == "MPC":
        return "MPC"
    return f"{c}廠"


def _plant_from_display_name(display_name: str) -> str:
    s = (display_name or "").strip().upper()
    if not s:
        return ""
    if "-" in s:
        left = (s.split("-", 1)[0] or "").strip()
        code = _normalize_org_code(left)
        if code:
            return code
    return _normalize_org_code(s)


def _resolve_login_user_org(emp_id: str, emp_name: str) -> str:
    uid = (emp_id or "").strip()
    name = (emp_name or "").strip()
    code = _plant_from_display_name(name)
    if code:
        return code
    if uid:
        try:
            from webapps.portal.oracle_emp import get_factory_plant_by_id

            code = _normalize_org_code(get_factory_plant_by_id(uid) or "")
            if code:
                return code
        except Exception:
            pass
    return ""


def _lookup_emp_display_from_oracle(emp_id: str, *, refresh: bool = False) -> str:
    emp_id = (emp_id or "").strip()
    if not emp_id:
        return ""
    # Rule: login_user -> login_user_name is resolved by MPC employee master only
    # (webapps.portal.oracle_emp), not by per-plant DOC database routing.
    from webapps.portal.oracle_emp import get_emp_name, get_factory_plant_by_id

    name = (get_emp_name(emp_id, refresh=refresh) or "").strip()
    if not name:
        return ""
    plant = (get_factory_plant_by_id(emp_id) or "").strip()
    if plant:
        return f"{_normalize_plant_label(plant)}-{name}"
    return name


def _cache_get_emp_name(emp_id: str, *, force_refresh: bool = False) -> str:
    emp_id = (emp_id or "").strip()
    if not emp_id:
        return ""

    now = time.time()
    ttl = float(_EMP_NAME_CACHE.get("ttl_sec") or 3600.0)
    m = _EMP_NAME_CACHE.get("map") or {}
    try:
        cached = m.get(emp_id)
        if cached:
            name, ts = cached
            if name and (now - float(ts)) <= ttl:
                return str(name).strip()
    except Exception:
        pass

    down_until = float(_ORA_DOWN_UNTIL.get("ts") or 0.0)
    if (not force_refresh) and down_until and now < down_until:
        return ""

    try:
        name = _lookup_emp_display_from_oracle(emp_id, refresh=force_refresh)
        if name:
            m[emp_id] = (name, now)
            _EMP_NAME_CACHE["map"] = m
        return name
    except Exception as e:
        logger.warning("[emp_name] oracle lookup failed: emp_id=%s err=%s", emp_id, e)
        cooldown = int(getattr(settings, "EMP_NAME_ORA_FAIL_COOLDOWN_SEC", 60) or 60)
        _ORA_DOWN_UNTIL["ts"] = now + max(5, cooldown)
        return ""


# ============================================================
# AAA bridge middleware (IIS/Proxy)
# ============================================================
class IISRemoteUserBridgeMiddleware:
    AAA_CANDIDATES = ["HTTP_X_AAA", "HTTP_AAA"]

    def __init__(self, get_response):
        self.get_response = get_response

    def _pick_aaa_debug(self, request) -> Tuple[str, str]:
        aaa_raw = ""
        for k in self.AAA_CANDIDATES:
            v = (request.META.get(k) or "").strip()
            if v:
                aaa_raw = v
                break
        if not aaa_raw:
            aaa_qs = (request.GET.get("aaa") or "").strip()
            if aaa_qs: aaa_raw = aaa_qs
        if not aaa_raw:
            aaa_ck = (request.COOKIES.get("aaa") or "").strip()
            if aaa_ck: aaa_raw = aaa_ck
        aaa_decoded = aaadecode(aaa_raw) if aaa_raw else ""
        return aaa_raw, aaa_decoded

    def __call__(self, request):
        aaa_raw, aaa_decoded = self._pick_aaa_debug(request)
        request.aaa = aaa_raw
        request.aaa_decoded = aaa_decoded
        aaa_display_name = _name_from_aaa_decoded(aaa_decoded)
        from_aaa = bool(aaa_decoded)

        login_user = ""
        if aaa_decoded:
            login_user = _strip_domain(aaa_decoded)
        if not login_user:
            login_user = _pick_remote_user(request)
        if (not login_user) and _env_bool("DEBUG", default=False):
            dev = (os.getenv("DEV_LOGIN_USER") or "").strip()
            if dev: login_user = _strip_domain(dev)

        if not login_user:
            try:
                sess_login = (request.session.get("login_user") or "").strip()
                if sess_login: login_user = sess_login
            except Exception: pass

        request.login_user = login_user or ""
        if login_user:
            request.META["REMOTE_USER"] = login_user
        emp_id = (request.login_user or "").strip()
        emp_name = ""
        sess_org = ""
        try:
            sess_emp_id = (request.session.get("login_user") or "").strip()
            sess_emp_name = (request.session.get("login_user_name") or "").strip()
            sess_org = (request.session.get("login_user_org") or "").strip()
        except Exception:
            sess_emp_id, sess_emp_name, sess_org = "", "", ""

        if sess_emp_name in ("未取得姓名", "雿輻??"):
            sess_emp_name = ""

        if emp_id:
            # Intranet rule: aaa decode -> USER_ID -> CT_EMPLOY (FACTORY_PLANT + NAME)
            if from_aaa and _env_bool("EMP_NAME_LOOKUP", default=True):
                emp_name = _cache_get_emp_name(emp_id, force_refresh=True)

            if (not emp_name) and sess_emp_name and sess_emp_id == emp_id:
                emp_name = sess_emp_name

            if (not emp_name) and _env_bool("EMP_NAME_LOOKUP", default=True):
                emp_name = _cache_get_emp_name(emp_id)

            employ = get_emp_full_info(emp_id)

            try:
                request.session["login_user"] = emp_id
                if emp_name:
                    request.session["login_user_name"] = emp_name
            except Exception:
                pass

        if (not emp_name) and emp_id and getattr(settings, "DEBUG", False):
            emp_name = (os.getenv("DEV_LOGIN_NAME") or "").strip()
        if not emp_name and aaa_display_name:
            emp_name = aaa_display_name
        # Reverse proxy abnormal fallback: keep existing session display name.
        if (not emp_name) and sess_emp_name:
            emp_name = sess_emp_name

        org_code = _resolve_login_user_org(emp_id, emp_name) or _normalize_org_code(sess_org)
        org_label = _org_label(org_code)        
        request.login_user_name = emp_name or ""
        request.login_user_org = org_code or ""
        request.login_user_org_label = org_label or ""
        if org_code:
            request.login_user_factory_plant = org_code
        else:
            request.login_user_factory_plant = ""
        try:
            if org_code:
                request.session["login_user_org"] = org_code
                request.session["login_user_factory_plant"] = org_code
                request.session["dep"] = employ['DEPTNO'] 
        except Exception:
            pass
        return self.get_response(request)


# ============================================================
# Portal usage log middleware
# ============================================================
def _to_bool_setting(v: object, default: bool = True) -> bool:
    if v is None: return default
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return bool(v)
    s = str(v).strip().lower()
    if not s: return default
    return s in ("1", "true", "yes", "y", "on")


def _parse_ip_token(raw: str) -> str:
    token = (raw or "").strip()
    if not token: return ""
    token = token.split(";", 1)[0].strip()
    if token.lower().startswith("for="): token = token[4:].strip()
    token = token.strip().strip('"').strip("'").strip()
    if token.startswith("[") and "]" in token: token = token[1 : token.find("]")]
    elif token.count(":") == 1 and "." in token:
        host, port = token.rsplit(":", 1)
        if port.isdigit(): token = host
    token = token.strip().strip("[]").strip()
    if token.lower() == "unknown": return ""
    try: return str(ipaddress.ip_address(token))
    except Exception: return ""


def _collect_client_ip_candidates(request) -> list[str]:
    trust_xff = _to_bool_setting(getattr(settings, "DOC_QUERY_TRUST_X_FORWARDED_FOR", True), default=True)
    candidates: list[str] = []
    if trust_xff:
        header_keys = ("HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP", "HTTP_X_ORIGINAL_FOR", "HTTP_X_CLIENT_IP", "HTTP_CLIENT_IP", "HTTP_FORWARDED")
        for key in header_keys:
            raw_val = (request.META.get(key) or "").strip()
            if not raw_val: continue
            for part in raw_val.split(","):
                ip = _parse_ip_token(part)
                if ip: candidates.append(ip)
    remote_ip = _parse_ip_token((request.META.get("REMOTE_ADDR") or "").strip())
    if remote_ip: candidates.append(remote_ip)
    return candidates


def _pick_non_loopback_ip(candidates: list[str]) -> str:
    for ip in candidates:
        try:
            obj = ipaddress.ip_address(ip)
            if obj.is_loopback or obj.is_unspecified or obj.is_link_local: continue
            return ip
        except Exception: continue
    return ""


def _get_server_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = str(s.getsockname()[0] or "").strip()
            if ip and not ip.startswith("127."): return ip
        finally: s.close()
    except Exception: pass
    return ""


def _client_ip(request) -> str:
    candidates = _collect_client_ip_candidates(request)
    best = _pick_non_loopback_ip(candidates)
    if best: return best
    if candidates: return candidates[0]
    return _get_server_lan_ip()


def _norm_prefix(p: str) -> str:
    p = (p or "").strip()
    if not p: return ""
    if not p.startswith("/"): p = "/" + p
    if len(p) > 1 and p.endswith("/"): p = p[:-1]
    return p


class ClearRemoteUserMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        request.META.pop("REMOTE_USER", None)
        request.META.pop("AUTH_USER", None)
        return self.get_response(request)


def _strip_prefix(path: str, prefix: str) -> str:
    p = (path or "").strip()
    pre = _norm_prefix(prefix)
    if not p or not pre or pre == "/": return p
    if p == pre: return "/"
    if p.startswith(pre + "/"): return "/" + p[len(pre) + 1 :]
    return p


def _normalize_path_for_match(path: str, request=None) -> str:
    p = (path or "").strip()
    if not p: return ""
    try: sn = _norm_prefix(getattr(request, "script_name", "") or "")
    except Exception: sn = ""
    if sn: p = _strip_prefix(p, sn)
    p = _strip_prefix(p, getattr(settings, "PROXY_PREFIX", "") or "")
    p = _strip_prefix(p, getattr(settings, "FORCE_SCRIPT_NAME", "") or "")
    if p.startswith("/portal/"): p = "/" + p[len("/portal/") :]
    return p


def _match_program_code(path: str, request=None) -> Optional[str]:
    code_map = tuple(getattr(settings, "PORTAL_USAGE_CODE_MAP", ()))
    if not code_map: return None
    p0 = (path or "").strip()
    p1 = _normalize_path_for_match(p0, request=request)
    sorted_map = sorted([(prefix or "", code) for prefix, code in code_map if prefix], key=lambda x: len(x[0]), reverse=True)
    for prefix, code in sorted_map:
        if prefix == "/":
            if p0 == "/" or p1 == "/": return code
            continue
        if p0.startswith(prefix) or p1.startswith(prefix): return code
    return None


# ???啣?嚗?敺?WhoAmI ?日鞈?
def _get_whoami_debug_info(
    request,
    *,
    program_code: str = "",
    norm_path: str = "",
    raw_path: str = "",
) -> Dict[str, Any]:
    return {
        "ENV": (os.getenv("ENV") or "").strip().upper(),
        "timestamp": timezone.now().isoformat(),
        "program_code": program_code,
        "raw_path": raw_path or (request.path or ""),
        "normalized_path": norm_path or _normalize_path_for_match((request.path or ""), request=request),
        "path_info": request.path_info or "",
        "method": request.method or "",
        "query_string": request.META.get("QUERY_STRING", ""),
        "request_script_name": getattr(request, "script_name", ""),
        "META_SCRIPT_NAME": request.META.get("SCRIPT_NAME", ""),
        "ENV_PROXY_PREFIX": os.getenv("PROXY_PREFIX"),
        "SETTINGS_PROXY_PREFIX": getattr(settings, "PROXY_PREFIX", None),
        "FORCE_SCRIPT_NAME": getattr(settings, "FORCE_SCRIPT_NAME", None),
        "host": request.get_host() if hasattr(request, "get_host") else "",
        "client_ip": _client_ip(request),
        "login_user": (getattr(request, "login_user", "") or ""),
        "login_user_name": (getattr(request, "login_user_name", "") or ""),
        "login_user_org": (getattr(request, "login_user_org", "") or ""),
        "login_user_org_label": (getattr(request, "login_user_org_label", "") or ""),
        "login_user_factory_plant": (getattr(request, "login_user_factory_plant", "") or ""),
        "aaa_decoded": (getattr(request, "aaa_decoded", "") or ""),
        "REMOTE_USER": request.META.get("REMOTE_USER", ""),
        "AUTH_USER": request.META.get("AUTH_USER", ""),
        "session_login_user_org": (
            (request.session.get("login_user_org") or "").strip()
            if hasattr(request, "session")
            else ""
        ),
    }


class PortalUsageLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if response.status_code >= 400: return response
            if request.method not in ("GET", "POST"): return response

            raw_path = (request.path or "").strip()
            norm_path = _normalize_path_for_match(raw_path, request=request)
            if (not norm_path) or norm_path.startswith("/static/") or norm_path.startswith("/admin/"): return response

            program_code = _match_program_code(norm_path, request=request)
            if not program_code: return response

            user_id = (getattr(request, "login_user", "") or "").strip()
            user_name = (getattr(request, "login_user_name", "") or "").strip()
            if user_id and (not user_name) and _env_bool("EMP_NAME_LOOKUP", default=True):
                name2 = _cache_get_emp_name(user_id)
                if name2: user_name = name2

            # ??蝝??WhoAmI ?日鞈?
            whoami_data = _get_whoami_debug_info(request)

            PortalUsageLog.objects.create(
                used_date=timezone.localdate(),
                program_code=program_code,
                user_id=user_id,
                user_name=user_name,
                path=raw_path,
                method=request.method,
                ip=_client_ip(request),
                whoami_json=json.dumps(whoami_data, ensure_ascii=False) # ??撖怠 JSON
            )
        except Exception as e:
            logger.exception("PortalUsageLog write failed: %s", e)
        return response

