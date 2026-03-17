# webapps/doc/views_todo.py
from __future__ import annotations

import json
from typing import Any, Dict

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.utils_login import get_login_user_idno, get_login_user_name
from webapps.doc.services.todo_service import todoService


def _get_q(request: HttpRequest) -> str:
    q = (request.GET.get("q") or "").strip()
    if q:
        return q

    if request.method != "POST":
        return ""

    try:
        payload: Dict[str, Any] = json.loads((request.body or b"").decode("utf-8") or "{}")
    except Exception:
        payload = {}

    return (payload.get("q") or "").strip()


@csrf_exempt
@require_node("doc", api=True)
def api_todo_lookup(request: HttpRequest):
    """
    個人待辦公文查詢（MOCK JSON）
    GET:
      /doc/api/todo/lookup/?q=1150000712
    POST JSON:
      { "q": "1150000712" }

    Response:
      { ok, items: [...], meta: {login_user, q, sql_example, ...} }
    """
    if request.method not in ("GET", "POST"):
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    login_user = (get_login_user_idno(request) or "").strip()
    login_user_name = (get_login_user_name(request) or "").strip()
    if not login_user:
        return JsonResponse({"ok": False, "error": "missing login_user"}, status=401)

    q = _get_q(request)
    from webapps.doc.utils_login import get_plant_arg
    plant = get_plant_arg(request)
    svc = todoService()
    data = svc.list_items(login_user=login_user, login_user_name=login_user_name, q=q, plant=plant)

    meta = data.get("meta") or {}
    return JsonResponse(
        {
            "ok": True,
            "items": data.get("items") or [],
            "meta": {
                "login_user": login_user,
                "q": q,
                "version": meta.get("version"),
                "source": meta.get("source"),
                "owner_org": meta.get("owner_org"),
                "sql_example": meta.get("sql_example"),
                "warning": meta.get("warning"),
                "error": meta.get("error"),
            },
        },
        status=200,
    )

# trigger reload
