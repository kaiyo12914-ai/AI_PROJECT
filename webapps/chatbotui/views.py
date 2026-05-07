from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node

from .service import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SEC,
    ChatbotUIService,
    resolve_model_name,
    resolve_user_id,
    safe_text,
)

import requests

from webapps.projectnotes.models import Project

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
    default_model_type = safe_text(getattr(settings, "MODEL_TYPE", "OPENAI")) or "OPENAI"
    return render(
        request,
        "chatbotui/index.html",
        {
            "debug_mode": bool(getattr(settings, "DEBUG", False)),
            "default_model_type": default_model_type,
            "default_model_name": resolve_model_name(default_model_type),
            "google_model_name": safe_text(os.getenv("GOOGLE_MODEL")) or "gemini-1.5-flash",
            "openai_model_name": safe_text(os.getenv("OPENAI_MODEL")) or "gpt-4o-mini",
            "ollama_model_name": safe_text(os.getenv("OLLAMA_MODEL")) or "mistral_small_3_1_2503:latest",
            "lm_studio_model_name": safe_text(os.getenv("LM_STUDIO_MODEL")) or "ministral-3-14b-instruct-2512",
            "default_temperature": DEFAULT_TEMPERATURE,
            "default_timeout_sec": DEFAULT_TIMEOUT_SEC,
            "project_options": list(Project.objects.all().order_by("-updated_at")[:50].values("id", "name")),
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
def api_conversation_rename(request, conversation_id: str):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    user_id = resolve_user_id(request)
    title = safe_text(body.get("title"))
    if not title:
        return JsonResponse({"ok": False, "error": "title is required"}, status=400)

    try:
        result = service.rename_conversation(user_id, safe_text(conversation_id), title)
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse({"ok": True, "conversation": result})
    except Exception as exc:
        logger.exception("chatbotui api_conversation_rename failed")
        return JsonResponse({"ok": False, "error": "conversation rename failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)

@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_model(request, conversation_id: str):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    user_id = resolve_user_id(request)
    model_type = safe_text(body.get("model_type"))
    model_name = safe_text(body.get("model_name")) or ""
    if not model_type:
        return JsonResponse({"ok": False, "error": "model_type is required"}, status=400)
    try:
        result = service.update_conversation_model(user_id, safe_text(conversation_id), model_type, model_name)
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse({"ok": True, "conversation": result})
    except Exception as exc:
        logger.exception("chatbotui api_conversation_model failed")
        return JsonResponse({"ok": False, "error": "conversation model update failed", "detail": str(exc) if settings.DEBUG else ""}, status=502)


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_config(request, conversation_id: str):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
    if "temperature" not in body and "timeout_sec" not in body and "system_prompt" not in body and "chat_mode" not in body and "rag_source" not in body:
        return JsonResponse({"ok": False, "error": "at least one field is required"}, status=400)

    user_id = resolve_user_id(request)
    try:
        result = service.update_conversation_config(
            user_id=user_id,
            conversation_id=safe_text(conversation_id),
            temperature=body["temperature"] if "temperature" in body else None,
            timeout_sec=body["timeout_sec"] if "timeout_sec" in body else None,
            system_prompt=body["system_prompt"] if "system_prompt" in body else None,
            chat_mode=body.get("chat_mode"),
            rag_source=body.get("rag_source"),
        )
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse({"ok": True, "conversation": result})
    except Exception as exc:
        logger.exception("chatbotui api_conversation_config failed")
        return JsonResponse(
            {"ok": False, "error": "conversation config update failed", "detail": str(exc) if settings.DEBUG else ""},
            status=502,
        )


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_config_reset_profile(request, conversation_id: str):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    user_id = resolve_user_id(request)
    try:
        result = service.reset_conversation_config_from_profile(
            user_id=user_id,
            conversation_id=safe_text(conversation_id),
        )
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse({"ok": True, "conversation": result})
    except Exception as exc:
        logger.exception("chatbotui api_conversation_config_reset_profile failed")
        return JsonResponse(
            {"ok": False, "error": "conversation config reset failed", "detail": str(exc) if settings.DEBUG else ""},
            status=502,
        )


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_prompt_history(request, conversation_id: str):
    user_id = resolve_user_id(request)
    cid = safe_text(conversation_id)
    if not cid:
        return JsonResponse({"ok": False, "error": "conversation_id is required"}, status=400)

    if request.method == "GET":
        try:
            limit = int(request.GET.get("limit") or 20)
        except Exception:
            limit = 20
        try:
            rows = service.list_prompt_history(user_id=user_id, conversation_id=cid, limit=limit)
            return JsonResponse({"ok": True, "history": rows})
        except Exception as exc:
            logger.exception("chatbotui api_conversation_prompt_history list failed")
            return JsonResponse(
                {"ok": False, "error": "prompt history list failed", "detail": str(exc) if settings.DEBUG else ""},
                status=502,
            )

    if request.method == "POST":
        body = _read_json_body(request)
        if body is None:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        history_id = int(body.get("history_id") or 0)
        if history_id <= 0:
            return JsonResponse({"ok": False, "error": "history_id is required"}, status=400)
        try:
            conversation = service.restore_prompt_history(user_id=user_id, conversation_id=cid, history_id=history_id)
            if not conversation:
                return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
            return JsonResponse({"ok": True, "conversation": conversation})
        except Exception as exc:
            logger.exception("chatbotui api_conversation_prompt_history restore failed")
            return JsonResponse(
                {"ok": False, "error": "prompt history restore failed", "detail": str(exc) if settings.DEBUG else ""},
                status=502,
            )

    return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)


@csrf_exempt
@require_node("chatbotui", api=True)
def api_conversation_attachments(request, conversation_id: str):
    user_id = resolve_user_id(request)
    cid = safe_text(conversation_id)
    if not cid:
        return JsonResponse({"ok": False, "error": "conversation_id is required"}, status=400)

    if request.method == "GET":
        try:
            limit = int(request.GET.get("limit") or 20)
        except Exception:
            limit = 20
        try:
            rows = service.list_attachments(user_id=user_id, conversation_id=cid, limit=limit)
            return JsonResponse({"ok": True, "attachments": rows})
        except Exception as exc:
            logger.exception("chatbotui api_conversation_attachments list failed")
            return JsonResponse(
                {"ok": False, "error": "attachment list failed", "detail": str(exc) if settings.DEBUG else ""},
                status=502,
            )

    if request.method == "POST":
        file_obj = request.FILES.get("file")
        if file_obj is None:
            return JsonResponse({"ok": False, "error": "file is required"}, status=400)
        try:
            content_bytes = file_obj.read()
            item = service.upload_attachment(
                user_id=user_id,
                conversation_id=cid,
                filename=safe_text(getattr(file_obj, "name", "")),
                mime_type=safe_text(getattr(file_obj, "content_type", "")),
                content_bytes=content_bytes,
            )
            if not item:
                return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
            return JsonResponse({"ok": True, "attachment": item}, status=201)
        except Exception as exc:
            logger.exception("chatbotui api_conversation_attachments upload failed")
            return JsonResponse(
                {"ok": False, "error": "attachment upload failed", "detail": str(exc) if settings.DEBUG else ""},
                status=502,
            )

    if request.method == "DELETE":
        body = _read_json_body(request) or {}
        attachment_id = int(request.GET.get("attachment_id") or body.get("attachment_id") or 0)
        if attachment_id <= 0:
            return JsonResponse({"ok": False, "error": "attachment_id is required"}, status=400)
        try:
            success = service.delete_attachment(user_id=user_id, conversation_id=cid, attachment_id=attachment_id)
            if not success:
                return JsonResponse({"ok": False, "error": "attachment not found"}, status=404)
            return JsonResponse({"ok": True, "attachment_id": attachment_id})
        except Exception as exc:
            logger.exception("chatbotui api_conversation_attachments delete failed")
            return JsonResponse(
                {"ok": False, "error": "attachment delete failed", "detail": str(exc) if settings.DEBUG else ""},
                status=502,
            )

    return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)


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
    model_name = safe_text(body.get("model_name")) or ""

    try:
        service.update_conversation_model(user_id, conversation_id, model_type, model_name)
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
                    "model_name": result.get("model_name", ""),
                    "latency_ms": result["latency_ms"],
                    "temperature": result.get("temperature", DEFAULT_TEMPERATURE),
                    "timeout_sec": result.get("timeout_sec", DEFAULT_TIMEOUT_SEC),
                    "attachment_used": bool(result.get("attachment_used")),
                    "attachment_count": int(result.get("attachment_count") or 0),
                    "rag_used": bool(result.get("rag_used")),
                    "citation_count": int(result.get("citation_count") or 0),
                    "rag_reason": safe_text(result.get("rag_reason")),
                    "citations": result.get("citations") if isinstance(result.get("citations"), list) else [],
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


@csrf_exempt
@require_node("chatbotui", api=True)
def api_chat_regenerate(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    conversation_id = safe_text(body.get("conversation_id"))
    if not conversation_id:
        return JsonResponse({"ok": False, "error": "conversation_id is required"}, status=400)

    user_id = resolve_user_id(request)
    model_type = safe_text(body.get("model_type")) or safe_text(getattr(settings, "MODEL_TYPE", "OPENAI")) or "OPENAI"

    try:
        result = service.regenerate_last_reply(user_id=user_id, conversation_id=conversation_id, model_type=model_type)
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "reply": result["reply"],
                "conversation_title": result["conversation_title"],
                "user_message": result["user_message"],
                "meta": {
                    "model_type": result["model_type"],
                    "model_name": result.get("model_name", ""),
                    "latency_ms": result["latency_ms"],
                    "temperature": result.get("temperature", DEFAULT_TEMPERATURE),
                    "timeout_sec": result.get("timeout_sec", DEFAULT_TIMEOUT_SEC),
                    "attachment_used": bool(result.get("attachment_used")),
                    "attachment_count": int(result.get("attachment_count") or 0),
                    "rag_used": bool(result.get("rag_used")),
                    "citation_count": int(result.get("citation_count") or 0),
                    "rag_reason": safe_text(result.get("rag_reason")),
                    "citations": result.get("citations") if isinstance(result.get("citations"), list) else [],
                    "debug": bool(getattr(settings, "DEBUG", False)),
                },
            }
        )
    except Exception as exc:
        logger.exception("chatbotui api_chat_regenerate failed")
        return JsonResponse(
            {
                "ok": False,
                "error": "chat regenerate failed",
                "detail": str(exc) if getattr(settings, "DEBUG", False) else "",
            },
            status=502,
        )


@csrf_exempt
@require_node("chatbotui", api=True)
def api_chat_resend(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    body = _read_json_body(request)
    if body is None:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    conversation_id = safe_text(body.get("conversation_id"))
    user_text = safe_text(body.get("message"))
    target_message_id = int(body.get("target_message_id") or 0)
    if not conversation_id:
        return JsonResponse({"ok": False, "error": "conversation_id is required"}, status=400)
    if target_message_id <= 0:
        return JsonResponse({"ok": False, "error": "target_message_id is required"}, status=400)
    if not user_text:
        return JsonResponse({"ok": False, "error": "message is required"}, status=400)

    user_id = resolve_user_id(request)
    model_type = safe_text(body.get("model_type")) or safe_text(getattr(settings, "MODEL_TYPE", "OPENAI")) or "OPENAI"

    try:
        result = service.resend_from_user_message(
            user_id=user_id,
            conversation_id=conversation_id,
            target_message_id=target_message_id,
            user_text=user_text,
            model_type=model_type,
        )
        if not result:
            return JsonResponse({"ok": False, "error": "conversation not found"}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "reply": result["reply"],
                "conversation_title": result["conversation_title"],
                "user_message": result["user_message"],
                "meta": {
                    "model_type": result["model_type"],
                    "model_name": result.get("model_name", ""),
                    "latency_ms": result["latency_ms"],
                    "temperature": result.get("temperature", DEFAULT_TEMPERATURE),
                    "timeout_sec": result.get("timeout_sec", DEFAULT_TIMEOUT_SEC),
                    "attachment_used": bool(result.get("attachment_used")),
                    "attachment_count": int(result.get("attachment_count") or 0),
                    "rag_used": bool(result.get("rag_used")),
                    "citation_count": int(result.get("citation_count") or 0),
                    "rag_reason": safe_text(result.get("rag_reason")),
                    "citations": result.get("citations") if isinstance(result.get("citations"), list) else [],
                    "debug": bool(getattr(settings, "DEBUG", False)),
                },
            }
        )
    except Exception as exc:
        logger.exception("chatbotui api_chat_resend failed")
        return JsonResponse(
            {
                "ok": False,
                "error": "chat resend failed",
                "detail": str(exc) if getattr(settings, "DEBUG", False) else "",
            },
            status=502,
        )

@csrf_exempt
@require_node("chatbotui", api=True)
def api_ollama_tags(request):
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    
    try:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434")
        if not base_url.startswith("http"):
            base_url = "http://" + base_url
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        if "gemma3:4b" not in models:
            models.append("gemma3:4b")
        return JsonResponse({"ok": True, "models": models})
    except Exception as exc:
        logger.warning(f"chatbotui api_ollama_tags failed: {exc}")
        return JsonResponse({"ok": True, "models": ["mistral_small_3_1_2503:latest", "gemma3:4b"]})
