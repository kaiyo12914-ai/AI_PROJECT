# webapps/doc/views_pages.py
from __future__ import annotations

from pathlib import Path

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


@require_node("doc")
def index(request: HttpRequest):
    """
    規範重點（Mandatory）
    1) 前端 baseUrl 只能讀 body[data-base-url]（template 注入）
    2) baseUrl 必須是「proxy prefix + app mount」，不得只給 request.script_name
       - 例：/doc 或 /djangoai/doc 或 /comment/doc
    3) views 不做任何前端路由推導；只負責注入正確 baseUrl 字串
    """
    # request.script_name：反代 prefix（可能為 /djangoai 或 /comment 或空）
    script = _norm_base(getattr(request, "script_name", "") or request.META.get("SCRIPT_NAME", ""))

    # request.path_info：Django 內部路徑（此頁通常是 /）
    path_info = (request.path_info or "/").strip()
    if not path_info.startswith("/"):
        path_info = "/" + path_info
    # 入口頁 / → 代表「doc 的 mount root」
    mount = "/doc" if path_info == "/" else path_info.rstrip("/")

    app_base_url = _norm_base((script + mount).replace("//", "/"))

    context = {
        # index.html 用：<body data-base-url="{{ app_base_url }}">
        "app_base_url": app_base_url,
    }

    try:
        return render(request, "doc/index.html", context)
    except TemplateDoesNotExist:
        # 兜底：直接讀取本 app 內模板檔，避免環境 template loader 找不到
        tpl_path = Path(__file__).resolve().parent / "templates" / "doc" / "index.html"
        if tpl_path.exists():
            engine = Engine.get_default()
            template = engine.from_string(tpl_path.read_text(encoding="utf-8"))
            return HttpResponse(template.render(context, request))
        raise
