# webapps/doc/views_templates.py
from __future__ import annotations

import json
import os
import re
from typing import Any

from django.db import connection as dj_connection
from django.db.utils import OperationalError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.models import DocumentTemplate

from webapps.doc.views_helpers import (
    _safe_str,
    _clean_tags,
    _valid_doc_types_set,
    _templates_visibility_filter,
    _apply_tag_filter,
    _draft_to_sections,
    _normalize_sections,
    _normalize_doc_fields,
    _normalize_meta,
    _save_template_with_conflict_policy_v2,
)

def _can_delete_template(tpl: DocumentTemplate, *, user, is_auth: bool) -> bool:
    if tpl.scope == "personal":
        return bool(is_auth and tpl.owner_id and user and tpl.owner_id == user.id)
    # public templates require staff/admin
    return bool(is_auth and user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)))

def _strip_ascii_qmarks(text: str) -> str:
    if not text:
        return ""
    # Remove repeated ASCII question marks (mojibake remnants), keep normal text.
    cleaned = re.sub(r"\?{2,}", "", str(text))
    return cleaned.strip()

def _clean_tags_ascii_qmarks(tags: Any) -> list[str]:
    out: list[str] = []
    for t in _clean_tags(tags):
        base = re.sub(r"\?{1,}", "", str(t)).strip()
        if not base:
            continue
        out.append(base)
    return out


@csrf_exempt
@require_node("doc", api=True)
def api_templates(request: HttpRequest):
    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))
    valid_doc_types = _valid_doc_types_set()

    if request.method == "GET":
        doc_type = (request.GET.get("doc_type") or "").strip()
        tag = (request.GET.get("tag") or "").strip()
        scope = (request.GET.get("scope") or "").strip().lower()

        qs = DocumentTemplate.objects.all()

        # scope 明確指定時優先處理
        if scope == "public":
            qs = qs.filter(scope="public")

        elif scope == "personal":
            if not is_auth:
                return JsonResponse({"ok": False, "error": "login required for personal templates"}, status=401)
            qs = qs.filter(scope="personal", owner=user)

        else:
            qs = _templates_visibility_filter(qs, user=user, is_auth=is_auth)

        # doc_type filter
        if doc_type:
            if doc_type not in valid_doc_types:
                return JsonResponse({"ok": False, "error": f"invalid doc_type: {doc_type}"}, status=400)
            qs = qs.filter(doc_type=doc_type)

        # order
        try:
            qs = qs.order_by("-created_at")
        except (OperationalError, Exception):
            qs = qs.order_by("-id")

        # tag filter
        if tag:
            qs = _apply_tag_filter(qs, tag)
            if isinstance(qs, list):
                qs.sort(
                    key=lambda t: (getattr(t, "created_at", None) or getattr(t, "id", 0)),
                    reverse=True,
                )

        data = []
        for t in qs:
            data.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "doc_type": t.doc_type,
                    "description": _strip_ascii_qmarks(getattr(t, "description", "") or ""),
                    "tags": _clean_tags_ascii_qmarks(getattr(t, "tags", None) or []),
                    "scope": getattr(t, "scope", "public"),
                    "owner": getattr(getattr(t, "owner", None), "username", None),
                    "schema_ver": getattr(t, "schema_ver", 2),
                    "sections": getattr(t, "sections", None) or {},
                    "doc_fields": getattr(t, "doc_fields", None) or {},
                    "meta": getattr(t, "meta", None) or {},
                    "content_text": _strip_ascii_qmarks(getattr(t, "content_text", "") or ""),
                    "created_at": getattr(t, "created_at", None).isoformat()
                    if getattr(t, "created_at", None)
                    else None,
                    "updated_at": getattr(t, "updated_at", None).isoformat()
                    if getattr(t, "updated_at", None)
                    else None,
                    "can_delete": _can_delete_template(t, user=user, is_auth=is_auth),
                }
            )

        return JsonResponse({"ok": True, "templates": data}, status=200)

    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

        title = _safe_str(body.get("title")).strip()
        doc_type = _safe_str(body.get("doc_type")).strip()
        description = _safe_str(body.get("description")).strip()

        scope = (_safe_str(body.get("scope") or "public").strip().lower() or "public")
        if scope not in ("public", "personal"):
            return JsonResponse({"ok": False, "error": "invalid scope (public/personal)"}, status=400)

        if scope == "personal" and (not is_auth):
            return JsonResponse({"ok": False, "error": "login required for personal templates"}, status=401)

        on_conflict = (_safe_str(body.get("on_conflict") or "suffix").strip().lower() or "suffix")
        if on_conflict not in ("overwrite", "suffix"):
            on_conflict = "suffix"

        tags = _clean_tags(body.get("tags", []))

        if not title:
            return JsonResponse({"ok": False, "error": "missing field: title"}, status=400)
        if not doc_type:
            return JsonResponse({"ok": False, "error": "missing field: doc_type"}, status=400)
        if doc_type not in valid_doc_types:
            return JsonResponse({"ok": False, "error": f"invalid doc_type: {doc_type}"}, status=400)

        schema_ver = int(body.get("schema_ver") or 2)

        sections = _normalize_sections(body.get("sections"))
        doc_fields = _normalize_doc_fields(body.get("doc_fields"))
        meta = _normalize_meta(body.get("meta"))

        content_text = _safe_str(body.get("content_text")).strip()
        if not sections and not content_text:
            return JsonResponse({"ok": False, "error": "missing field: sections or content_text"}, status=400)

        if not sections and content_text:
            sections = _draft_to_sections(doc_type, content_text)

        try:
            obj, created, final_title, policy, status_msg = _save_template_with_conflict_policy_v2(
                title=title,
                doc_type=doc_type,
                description=description,
                sections=sections,
                doc_fields=doc_fields,
                meta=meta,
                tags=tags,
                scope=scope,
                user=user,
                on_conflict=on_conflict,
                schema_ver=schema_ver,
                max_suffix_try=int(os.getenv("DOC_TPL_SUFFIX_MAX_TRY", "50")),
            )
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

        return JsonResponse(
            {
                "ok": True,
                "id": obj.id,
                "created": created,
                "title": final_title,
                "scope": getattr(obj, "scope", scope),
                "on_conflict": policy,
                "status": status_msg,
            },
            status=201 if created else 200,
        )

    return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)


@csrf_exempt
@require_node("doc", api=True)
def api_template_item(request: HttpRequest, tpl_id: int):
    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))

    if request.method != "DELETE":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        tpl = DocumentTemplate.objects.get(id=tpl_id)
    except DocumentTemplate.DoesNotExist:
        return JsonResponse({"ok": False, "error": "not found"}, status=404)

    if not _can_delete_template(tpl, user=user, is_auth=is_auth):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    tpl.delete()
    return JsonResponse({"ok": True, "id": tpl_id}, status=200)
