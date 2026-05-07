import json
import sys
import types
from pathlib import Path

import django
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        DEBUG=True,
        DEFAULT_CHARSET="utf-8",
        ROOT_URLCONF="webproj.urls",
        INSTALLED_APPS=[],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    )
django.setup()

from webapps.chatbotui import views


def _request(method, path, payload=None):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path)
    elif method == "DELETE":
        request = factory.delete(path)
    else:
        request = factory.post(path, data=json.dumps(payload or {}), content_type="application/json")
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    request.login_user = "EMP001"
    return request


def test_conversation_rename_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "rename_conversation",
        lambda user_id, conversation_id, title: {"id": conversation_id, "title": title, "model_type": "GOOGLE"},
    )
    response = views.api_conversation_rename(
        _request("POST", "/chatbotui/conversations/c1/rename/", {"title": "Project Summary"}),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["conversation"]["title"] == "Project Summary"


def test_chat_regenerate_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "regenerate_last_reply",
        lambda user_id, conversation_id, model_type: {
            "reply": "Regenerated answer",
            "conversation_title": "Chat A",
            "latency_ms": 88,
            "model_type": model_type,
            "user_message": "hello",
            "attachment_used": True,
            "attachment_count": 1,
            "rag_used": False,
            "citation_count": 0,
            "rag_reason": "rag_disabled",
            "citations": [],
        },
    )
    response = views.api_chat_regenerate(
        _request(
            "POST",
            "/chatbotui/chat/regenerate/",
            {"conversation_id": "c1", "model_type": "GOOGLE"},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["reply"] == "Regenerated answer"
    assert payload["meta"]["latency_ms"] == 88
    assert payload["meta"]["attachment_used"] is True
    assert payload["meta"]["attachment_count"] == 1
    assert payload["meta"]["rag_used"] is False
    assert payload["meta"]["citation_count"] == 0
    assert payload["meta"]["rag_reason"] == "rag_disabled"
    assert payload["meta"]["citations"] == []


def test_chat_regenerate_missing_conversation_id(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    response = views.api_chat_regenerate(_request("POST", "/chatbotui/chat/regenerate/", {"conversation_id": ""}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 400
    assert payload == {"ok": False, "error": "conversation_id is required"}


def test_chat_resend_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "resend_from_user_message",
        lambda user_id, conversation_id, target_message_id, user_text, model_type: {
            "reply": "Updated answer",
            "conversation_title": "Chat A",
            "latency_ms": 91,
            "model_type": model_type,
            "user_message": user_text,
            "attachment_used": False,
            "attachment_count": 0,
            "rag_used": True,
            "citation_count": 2,
            "rag_reason": "rag_hit",
            "citations": [{"ref": "C1", "source_title": "DocA", "source_url": "", "confidence": 0.8, "excerpt": "x"}],
        },
    )
    response = views.api_chat_resend(
        _request(
            "POST",
            "/chatbotui/chat/resend/",
            {"conversation_id": "c1", "target_message_id": 5, "message": "updated text", "model_type": "GOOGLE"},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["reply"] == "Updated answer"
    assert payload["meta"]["latency_ms"] == 91
    assert payload["meta"]["rag_used"] is True
    assert payload["meta"]["citation_count"] == 2
    assert payload["meta"]["rag_reason"] == "rag_hit"
    assert payload["meta"]["citations"][0]["ref"] == "C1"


def test_conversation_model_update_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "update_conversation_model",
        lambda user_id, conversation_id, model_type, model_name="": {
            "id": conversation_id,
            "title": "Chat A",
            "model_type": model_type,
            "model_name": "gemma3:4b",
        },
    )
    response = views.api_conversation_model(
        _request("POST", "/chatbotui/conversations/c1/model/", {"model_type": "OLLAMA"}),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["conversation"]["model_type"] == "OLLAMA"


def test_conversation_config_update_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "update_conversation_config",
        lambda user_id, conversation_id, temperature, timeout_sec, system_prompt, chat_mode=None, rag_source=None: {
            "id": conversation_id,
            "title": "Chat A",
            "model_type": "OLLAMA",
            "model_name": "gemma-4",
            "temperature": 0.2,
            "timeout_sec": 180,
            "system_prompt": "You are concise.",
        },
    )
    response = views.api_conversation_config(
        _request(
            "POST",
            "/chatbotui/conversations/c1/config/",
            {"temperature": 0.2, "timeout_sec": 180, "system_prompt": "You are concise."},
        ),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["conversation"]["temperature"] == 0.2
    assert payload["conversation"]["timeout_sec"] == 180


def test_chat_meta_fields_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(views.service, "update_conversation_model", lambda user_id, conversation_id, model_type, model_name="": {})
    monkeypatch.setattr(
        views.service,
        "chat",
        lambda user_id, conversation_id, user_text, model_type: {
            "reply": "ok",
            "conversation_title": "Chat A",
            "latency_ms": 55,
            "model_type": model_type,
            "model_name": "gemma3:4b",
            "temperature": 0.3,
            "timeout_sec": 120,
            "attachment_used": True,
            "attachment_count": 2,
            "rag_used": True,
            "citation_count": 3,
            "rag_reason": "rag_hit",
            "citations": [{"ref": "C2", "source_title": "DocB", "source_url": "https://example.com", "confidence": 0.9, "excerpt": "y"}],
        },
    )
    response = views.api_chat(
        _request("POST", "/chatbotui/chat/", {"conversation_id": "c1", "message": "hello", "model_type": "OLLAMA"})
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["meta"]["attachment_used"] is True
    assert payload["meta"]["attachment_count"] == 2
    assert payload["meta"]["rag_used"] is True
    assert payload["meta"]["citation_count"] == 3
    assert payload["meta"]["rag_reason"] == "rag_hit"
    assert payload["meta"]["citations"][0]["source_title"] == "DocB"


def test_conversation_config_update_requires_field(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    response = views.api_conversation_config(
        _request("POST", "/chatbotui/conversations/c1/config/", {}),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 400
    assert payload == {"ok": False, "error": "at least one field is required"}


def test_prompt_history_list_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "list_prompt_history",
        lambda user_id, conversation_id, limit: [
            {"id": 11, "prompt_text": "A", "created_at": "2026-05-06T12:00:00+08:00"},
            {"id": 10, "prompt_text": "B", "created_at": "2026-05-06T11:00:00+08:00"},
        ],
    )
    response = views.api_conversation_prompt_history(
        _request("GET", "/chatbotui/conversations/c1/prompt-history/?limit=20"),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert len(payload["history"]) == 2
    assert payload["history"][0]["id"] == 11


def test_prompt_history_restore_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "restore_prompt_history",
        lambda user_id, conversation_id, history_id: {
            "id": conversation_id,
            "title": "Chat A",
            "model_type": "OLLAMA",
            "model_name": "gemma-4",
            "temperature": 0.4,
            "timeout_sec": 180,
            "system_prompt": "restored prompt",
        },
    )
    response = views.api_conversation_prompt_history(
        _request("POST", "/chatbotui/conversations/c1/prompt-history/", {"history_id": 11}),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["conversation"]["system_prompt"] == "restored prompt"


def test_attachment_list_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "list_attachments",
        lambda user_id, conversation_id, limit: [
            {"id": 1, "filename": "notes.txt", "mime_type": "text/plain", "size_bytes": 12, "content_preview": "abc", "created_at": "2026-05-06T13:00:00+08:00"},
        ],
    )
    response = views.api_conversation_attachments(
        _request("GET", "/chatbotui/conversations/c1/attachments/?limit=20"),
        "c1",
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["attachments"][0]["filename"] == "notes.txt"


def test_attachment_upload_success(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "upload_attachment",
        lambda user_id, conversation_id, filename, mime_type, content_bytes: {
            "id": 2,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content_bytes),
            "content_preview": "hello",
            "created_at": "2026-05-06T13:05:00+08:00",
        },
    )
    factory = RequestFactory()
    file_obj = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
    request = factory.post("/chatbotui/conversations/c1/attachments/", {"file": file_obj})
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    request.login_user = "EMP001"
    response = views.api_conversation_attachments(request, "c1")
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["attachment"]["filename"] == "notes.txt"
