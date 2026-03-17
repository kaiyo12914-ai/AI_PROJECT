# webapps/doc/views_draft_reply.py
from __future__ import annotations

import json
from typing import Any, Dict

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.views_helpers import _safe_str
from webapps.doc.services.draft_reply_service import draft_reply


@csrf_exempt
@require_node("doc", api=True)
def api_draft_reply(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    doc_id = _safe_str(body.get("doc_id")).strip()
    from_level = _safe_str(body.get("from_level")).strip()
    instruction = _safe_str(body.get("instruction")).strip()
    doc_text = _safe_str(body.get("doc_text")).strip()
    context = _safe_str(body.get("context")).strip()

    doc_meta_raw = body.get("doc_meta", {})
    doc_meta: Dict[str, Any] = doc_meta_raw if isinstance(doc_meta_raw, dict) else {}

    from_org = ""
    if isinstance(doc_meta, dict):
        from_org = _safe_str(doc_meta.get("from_org")).strip()
    if not from_level and not from_org:
        return JsonResponse({"ok": False, "error": "from_level or doc_meta.from_org is required"}, status=400)

    try:
        result = draft_reply(
            doc_id=doc_id,
            from_level=from_level,
            instruction=instruction,
            doc_meta=doc_meta,
            doc_text=doc_text,
            context=context,
        )
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": "draft_reply_failed", "detail": str(e)}, status=500)

    return JsonResponse(result, status=200)
