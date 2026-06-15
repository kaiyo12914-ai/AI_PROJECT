import json
import sys
import types
from pathlib import Path

import django
from django.conf import settings
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


def test_chatbotui_page_renders(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.chatbotui.views.render",
        lambda request, template_name, context: types.SimpleNamespace(
            status_code=200,
            content=f"{template_name}|{context['default_model_type']}".encode("utf-8"),
        ),
    )
    response = views.index(_request("GET", "/chatbotui/"))
    assert response.status_code == 200
    assert "chatbotui/index.html" in response.content.decode("utf-8")


def test_chatbotui_ext_only_uses_ollama(monkeypatch):
    monkeypatch.setenv("ENV", "EXT")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.0.137:11434")
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.chatbotui.views.render",
        lambda request, template_name, context: types.SimpleNamespace(
            status_code=200,
            content=f"{context['default_model_type']}|{','.join(context['allowed_model_types'])}".encode("utf-8"),
        ),
    )

    response = views.index(_request("GET", "/chatbotui/"))
    text = response.content.decode("utf-8")
    assert text == "OLLAMA|OLLAMA"

    called = {"hit": False}

    def fail_if_called(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("requests.get should not be called under ENV=EXT")

    monkeypatch.setattr("webapps.chatbotui.views.requests.get", fail_if_called)
    response = views.api_lm_studio_models(_request("GET", "/chatbotui/lmstudio/models/"))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["models"] == []
    assert called["hit"] is False


def test_conversation_list_returns_rows(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "list_conversations",
        lambda user_id: [{"id": "c1", "title": "Chat 1", "model_type": "GOOGLE", "preview": "hello", "message_count": 2}],
    )
    response = views.api_conversations(_request("GET", "/chatbotui/conversations/"))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["conversations"][0]["id"] == "c1"


def test_conversation_create_returns_conversation(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "create_conversation",
        lambda user_id, title, model_type: {"id": "c2", "title": title, "model_type": model_type, "messages": []},
    )
    response = views.api_conversations(
        _request("POST", "/chatbotui/conversations/", {"title": "New Chat", "model_type": "GOOGLE"})
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 201
    assert payload["conversation"]["id"] == "c2"


def test_chatbotui_chat_returns_reply(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views.service,
        "chat",
        lambda user_id, conversation_id, user_text, model_type: {
            "reply": "這是測試回覆。",
            "conversation_title": "請幫我整理重點",
            "latency_ms": 123,
            "model_type": model_type,
        },
    )
    response = views.api_chat(
        _request(
            "POST",
            "/chatbotui/chat/",
            {"conversation_id": "c1", "message": "請幫我整理重點", "model_type": "GOOGLE"},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["reply"] == "這是測試回覆。"
    assert payload["meta"]["latency_ms"] == 123


def test_chatbotui_chat_rejects_missing_message(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    response = views.api_chat(_request("POST", "/chatbotui/chat/", {"conversation_id": "c1", "message": ""}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 400
    assert payload == {"ok": False, "error": "message is required"}
