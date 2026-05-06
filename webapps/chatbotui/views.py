from __future__ import annotations

import json
import logging
from typing import Any, Dict

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node

from .service import ChatbotUIService, resolve_user_id, safe_text

logger = logging.getLogger(__name__)

service = ChatbotUIService()


def _read_json_body(request) -> Dict[str, Any] | None:
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else {}


@require_node("chatbotui")
def index(request):
    return render(
        request,
        "chatbotui/index.html",
        {
            "debug_mode": bool(getattr(settings, "DEBUG", False)),
            "default_model_type": safe_text(getattr(settings, "MODEL_TYPE", "OPENAI")) or "OPENAI",
        },
    )


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversations(request):
    user_id = resolve_user_id(request)

    if request.method == "GET":
        try:
            rows = service.list_conversations(user_id)
            return JsonResponse({"ok": True, "conversations": rows})
        except Exception as exc:
            logger.exception("chatbotui api_conversations list failed")
            return JsonResponse({"ok": False, "error": "conversation list failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)

    if request.method == "POST":
        body = _read_json_body(request)
        if body is None:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        try:
            conversation = service.create_conversation(
                user_id=user_id,
                title=safe_text(body.get("title")) or "New Chat",
                model_type=safe_text(body.get("model_type")) or safe_text(getattr(settings, "MODEL_TYPE", "OPENAI")) or "OPENAI",
            )
            return JsonResponse({"ok": True, "conversation": conversation}, status=201)
        except Exception as exc:
            logger.exception("chatbotui api_conversations create failed")
            return JsonResponse({"ok": False, "error": "conversation create failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)

    return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_detail(request, conversation_id: str):
    user_id = resolve_user_id(request)
    conversation_id = safe_text(conversation_id)
    if not conversation_id:
        return JsonResponse({"ok": False, "error": "conversation_id is required"}, status=400)

    if request.method == "GET":
        try:
            conversation = service.get_conversation_detail(user_id, conversation_id)
            if not conversation:
                return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
            return JsonResponse({"ok": True, "conversation": conversation})
        except Exception as exc:
            logger.exception("chatbotui api_conversation_detail get failed")
            return JsonResponse({"ok": False, "error": "conversation detail failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)

    if request.method == "DELETE":
        try:
            ok = service.archive_conversation(user_id, conversation_id)
            if not ok:
                return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
            return JsonResponse({"ok": True})
        except Exception as exc:
            logger.exception("chatbotui api_conversation_detail delete failed")
            return JsonResponse({"ok": False, "error": "conversation delete failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)

    return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_clear(request, conversation_id: str):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    user_id = resolve_user_id(request)
    try:
        ok = service.clear_conversation(user_id, safe_text(conversation_id))
        if not ok:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse({"ok": True})
    except Exception as exc:
        logger.exception("chatbotui api_conversation_clear failed")
        return JsonResponse({"ok": False, "error": "conversation clear failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)


@csrf_exempt
@require_node("chatbotui", api=True)
def api_chat(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    conversation_id = safe_text(body.get("conversation_id"))
    user_text = safe_text(body.get("message"))
    if not conversation_id:
        return JsonResponse({"ok": False, "error": "conversation_id is required"}, status=400)
    if not user_text:
        return JsonResponse({"ok": False, "error": "message is required"}, status=400)

    user_id = resolve_user_id(request)
    model_type = safe_text(body.get("model_type")) or safe_text(getattr(settings, "MODEL_TYPE", "OPENAI")) or "OPENAI"

    try:
        result = service.chat(user_id=user_id, conversation_id=conversation_id, user_text=user_text, model_type=model_type)
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "reply": result["reply"],
                "conversation_title": result["conversation_title"],
                "meta": {
                    "model_type": result["model_type"],
                    "latency_ms": result["latency_ms"],
                    "debug": bool(getattr(settings, "DEBUG", False)),
                },
            }
        )
    except Exception as exc:
        logger.exception("chatbotui api_chat failed")
        return JsonResponse(
            {
                "ok": False,
                "error": "chat request failed",
                "detail": str(exc) if getattr(settings, "DEBUG", False) else "",
            },
            status=502,
        )
