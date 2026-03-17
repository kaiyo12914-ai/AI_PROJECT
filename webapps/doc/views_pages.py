# webapps/doc/views_pages.py
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template import Engine, TemplateDoesNotExist

from webapps.portal.decorators import require_node


def _norm_base(p: str) -> str:
    s = (p or "").strip()
    if not s:
        return ""
    if not s.startswith("/"):
        s = "/" + s
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return "" if s == "/" else s


def _calc_app_base_url(request: HttpRequest) -> str:
    """
    Compute app mount root for frontend API URL generation.
    Example: /doc/templates/ -> /doc
    """
    path = (getattr(request, "path", "") or "/")
    script = _norm_base(getattr(request, "script_name", "") or request.META.get("SCRIPT_NAME", ""))

    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/") or "/"

    base = path
    if base.startswith(script):
        rest = base[len(script):]
    else:
        rest = base

    if rest in ("", "/"):
        mount = "/doc"
    else:
        first = rest.split("/", 2)[1] if rest.startswith("/") else rest.split("/", 1)[0]
        mount = "/" + first if first else "/doc"

    return _norm_base((script + mount).replace("//", "/"))
    if not path.startswith("/"):
        path = "/" + path
    if not path_info.startswith("/"):
        path_info = "/" + path_info

    path = path.rstrip("/") or "/"
    path_info = path_info.rstrip("/") or "/"

    if path_info != "/" and path.endswith(path_info):
        base = path[: -len(path_info)]
        if not base:
            base = path
    elif path_info == "/":
        base = path
    else:
        base = path

    return _norm_base(base)


def _to_bool_setting(v: object, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if not s:
        return default
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _parse_ip_token(raw: str) -> str:
    token = (raw or "").strip()
    if not token:
        return ""
    token = token.split(";", 1)[0].strip()
    if token.lower().startswith("for="):
        token = token[4:].strip()
    token = token.strip().strip('"').strip("'").strip()
    if token.startswith("[") and "]" in token:
        token = token[1 : token.find("]")]
    elif token.count(":") == 1 and "." in token:
        host, port = token.rsplit(":", 1)
        if port.isdigit():
            token = host
    token = token.strip().strip("[]").strip()
    if token.lower() == "unknown":
        return ""
    try:
        return str(ipaddress.ip_address(token))
    except Exception:
        return ""


def _collect_client_ip_candidates(request: HttpRequest) -> list[str]:
    trust_xff = _to_bool_setting(getattr(settings, "DOC_QUERY_TRUST_X_FORWARDED_FOR", True), default=True)
    candidates: list[str] = []

    if trust_xff:
        header_keys = (
            "HTTP_X_FORWARDED_FOR",
            "HTTP_X_REAL_IP",
            "HTTP_X_ORIGINAL_FOR",
            "HTTP_X_CLIENT_IP",
            "HTTP_CLIENT_IP",
            "HTTP_FORWARDED",
        )
        for key in header_keys:
            raw_val = (request.META.get(key) or "").strip()
            if not raw_val:
                continue
            for part in raw_val.split(","):
                ip = _parse_ip_token(part)
                if ip:
                    candidates.append(ip)

    remote_ip = _parse_ip_token((request.META.get("REMOTE_ADDR") or "").strip())
    if remote_ip:
        candidates.append(remote_ip)
    return candidates


def _ip_in_allow_list(ip: str, allow_list: list[str]) -> bool:
    cur = (ip or "").strip()
    if not cur:
        return False
    if "*" in [x.strip() for x in (allow_list or [])]:
        return True

    try:
        ip_obj = ipaddress.ip_address(cur)
    except Exception:
        return False

    for raw in (allow_list or []):
        item = (raw or "").strip()
        if not item:
            continue
        if item == cur:
            return True
        try:
            net = ipaddress.ip_network(item, strict=False)
        except Exception:
            continue
        if ip_obj in net:
            return True
    return False


def _pick_non_loopback_ip(candidates: list[str]) -> str:
    for ip in candidates:
        try:
            obj = ipaddress.ip_address(ip)
        except Exception:
            continue
        if obj.is_loopback or obj.is_unspecified or obj.is_link_local:
            continue
        return ip
    return ""


def _get_server_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = str(s.getsockname()[0] or "").strip()
            if ip and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except Exception:
        pass

    try:
        host = socket.gethostname()
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except Exception:
        infos = []
    for info in infos:
        try:
            ip = str(info[4][0] or "").strip()
            obj = ipaddress.ip_address(ip)
        except Exception:
            continue
        if obj.is_loopback or obj.is_unspecified or obj.is_link_local:
            continue
        return ip
    return ""


def _is_authorized_query_ip(request: HttpRequest) -> bool:
    allow_list = list(getattr(settings, "DOC_QUERY_ALLOWED_IPS", []) or [])
    candidates = _collect_client_ip_candidates(request)

    # Match any candidate IP (forwarded headers + remote addr).
    for ip in candidates:
        if _ip_in_allow_list(ip, allow_list):
            return True

    # Fallback: best non-loopback candidate, then server LAN IP.
    best = _pick_non_loopback_ip(candidates)
    if best and _ip_in_allow_list(best, allow_list):
        return True
    if candidates:
        lan = _get_server_lan_ip()
        if lan and _ip_in_allow_list(lan, allow_list):
            return True
    return False


@require_node("doc")
def index(request: HttpRequest):
    """
    Render doc index with derived app base URL.
    1) Inject base URL into body[data-base-url] for JS.
    2) Base URL is derived from script/prefix + app mount.
    3) Keep this computation in view so templates stay simple.
    """
    app_base_url = _calc_app_base_url(request)

    context = {
        # index.html expects: <body data-base-url="{{ app_base_url }}">
        "app_base_url": app_base_url,
        "show_doc_query_button": _is_authorized_query_ip(request),
    }

    try:
        return render(request, "doc/index.html", context)
    except TemplateDoesNotExist:
        # Fallback when template loader cannot resolve app templates.
        tpl_path = Path(__file__).resolve().parent / "templates" / "doc" / "index.html"
        if tpl_path.exists():
            engine = Engine.get_default()
            template = engine.from_string(tpl_path.read_text(encoding="utf-8"))
            return HttpResponse(template.render(context, request))
        raise

@require_node("doc")
def templates_manage(request: HttpRequest):
    """
    Render template management page.
    """
    app_base_url = _calc_app_base_url(request)

    context = {
        "app_base_url": app_base_url,
        "show_doc_query_button": _is_authorized_query_ip(request),
    }

    try:
        return render(request, "doc/templates_manage.html", context)
    except TemplateDoesNotExist:
        tpl_path = Path(__file__).resolve().parent / "templates" / "doc" / "templates_manage.html"
        if tpl_path.exists():
            engine = Engine.get_default()
            template = engine.from_string(tpl_path.read_text(encoding="utf-8"))
            return HttpResponse(template.render(context, request))
        raise
