# webapps/portal/templatetags/proxy_urls.py
from __future__ import annotations

from django import template
from django.templatetags.static import static as dj_static
from django.urls import NoReverseMatch, reverse

register = template.Library()


def _norm_prefix(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def _get_prefix(context) -> str:
    req = context.get("request")
    if not req:
        return ""
    return _norm_prefix(getattr(req, "proxy_prefix", "") or "")


@register.simple_tag(takes_context=True)
def proxy_url(context, viewname: str, *args, **kwargs) -> str:
    """
    用法：{% proxy_url 'doc:incoming_lookup' %}
    會回傳：<prefix> + reverse(viewname)
    """
    path = reverse(viewname, args=args, kwargs=kwargs)
    prefix = _get_prefix(context)
    return f"{prefix}{path}"


@register.simple_tag(takes_context=True)
def proxy_url_or(context, fallback_path: str, viewname: str, *args, **kwargs) -> str:
    """
    用法：{% proxy_url_or '/doc/' 'doc_page' %}
    - reverse 成功：回 prefix + reverse
    - reverse 失敗：回 prefix + fallback_path（確保 fallback 也吃 prefix）
    """
    prefix = _get_prefix(context)
    try:
        path = reverse(viewname, args=args, kwargs=kwargs)
        return f"{prefix}{path}"
    except NoReverseMatch:
        fb = (fallback_path or "").strip() or "/"
        if not fb.startswith("/"):
            fb = "/" + fb
        return f"{prefix}{fb}"


@register.simple_tag(takes_context=True)
def proxy_static(context, static_path: str) -> str:
    """
    用法：{% proxy_static 'doc/incoming_sybase.js' %}
    會回傳：<prefix> + STATIC_URL + path
    """
    url = dj_static(static_path)
    prefix = _get_prefix(context)
    # dj_static 回傳通常是 /static/xxx；我們把 prefix 接上
    return f"{prefix}{url}"
