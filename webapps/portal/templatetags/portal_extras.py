# webapps/portal/templatetags/portal_extras.py
from __future__ import annotations

from django import template
from django.urls import NoReverseMatch, reverse

from webapps.portal.acl import can_access

register = template.Library()


def _strip_slashes(s: str) -> str:
    return (s or "").strip().strip("/")


def _ensure_leading_slash(s: str) -> str:
    s = (s or "").strip()
    if not s.startswith("/"):
        s = "/" + s
    return s


def _norm_path(p: str) -> str:
    """
    正規化「內部路徑」（不是 prefix）
    - 確保以 / 開頭
    - 不在這裡加 proxy prefix（prefix 由 script_name 統一處理）
    """
    p = (p or "").strip()
    if not p:
        return "/"
    return _ensure_leading_slash(p)


def _get_script_name(context) -> str:
    """
    ✅ 專案規範：外部 prefix 唯一真相 = request.script_name
    - middleware 會在反代情境寫回 request.script_name / META['SCRIPT_NAME']
    """
    req = context.get("request")
    if not req:
        return ""

    sn = (getattr(req, "script_name", "") or "").strip()
    if sn:
        return _ensure_leading_slash(_strip_slashes(sn))

    sn2 = (req.META.get("SCRIPT_NAME", "") or "").strip()
    if sn2:
        return _ensure_leading_slash(_strip_slashes(sn2))

    return ""


def _prefix_with_script_name(script_name: str, path: str) -> str:
    """
    把「內部路徑」轉成「外部可用路徑」
    - script_name: "" or ""
    - path: "/translator/" or "/doc/"
    return:
      - "" + "/translator/" => "/translator/"
      - "" + "/translator/" => "/translator/"
    規則：
      - 避免雙層：若 path 已含 script_name 則直接回傳
    """
    sn = _ensure_leading_slash(_strip_slashes(script_name)) if script_name else ""
    p = _norm_path(path)

    if not sn:
        return p

    if p == sn or p.startswith(sn + "/"):
        return p

    return sn.rstrip("/") + p


@register.simple_tag(takes_context=True)
def url_or(context, fallback_path: str, url_name: str, *args, **kwargs) -> str:
    """
    ✅ Portal 入口頁規範：fail-open（Proxy-aware / ScriptName-aware）

    1) 優先 reverse(url_name)
       - 若 FORCE_SCRIPT_NAME 有值，reverse 結果通常已帶 prefix（例如 /xxx/）
       - 若 FORCE_SCRIPT_NAME 為空，reverse 只會回 /xxx/

    2) reverse 失敗才用 fallback_path（必須是「Django 內部路徑」例如 "/doc/"）
       - fallback 也不允許硬寫 

    3) 最後一律用 request.script_name 補上外部 prefix（唯一真相）
       - 避免出現 portal 點出去少  的問題
    """
    script_name = _get_script_name(context)

    try:
        u = reverse(url_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        u = _norm_path(fallback_path)

    return _prefix_with_script_name(script_name, u)


@register.simple_tag(takes_context=True)
def allow(context, node: str) -> bool:
    """
    ACL helper
    用法：
      {% allow "pdf" as can_pdf %}
      {% if can_pdf %} ... {% endif %}
    """
    request = context.get("request")
    user = getattr(request, "user", None) if request else None
    return can_access(user, node)
