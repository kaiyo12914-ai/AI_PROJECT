import json
import os
import sys
import types

import django
from django.conf import settings
from django.test import RequestFactory

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        DEBUG=True,
        DEFAULT_CHARSET="utf-8",
        ROOT_URLCONF="webproj.urls",
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "webapps.comment",
        ],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        USE_TZ=True,
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        PORTAL_ACL_BYPASS_NODES_EXT=[],
    )
django.setup()

from webapps.comment import views as comment_views
from webapps.llm import llm_factory


def test_lm_studio_factory_uses_lm_studio_env(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, input, **kwargs):
            return "ok"

    fake_module = types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    monkeypatch.setenv("MODEL_TYPE", "LM_STUDIO")
    monkeypatch.setenv("MODEL_TEMPERATURE", "0.2")
    monkeypatch.setenv("MODEL_TIMEOUT", "120")
    monkeypatch.setenv("LM_STUDIO_BASE_URL", "http://lmstudio.local:1234/v1")
    monkeypatch.setenv("LM_STUDIO_MODEL", "local-test-model")
    monkeypatch.setenv("LM_STUDIO_TEMPERATURE", "0.7")
    monkeypatch.setenv("LM_STUDIO_TIMEOUT", "33")
    monkeypatch.delenv("LM_STUDIO_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    llm = llm_factory.get_chat_model()

    assert repr(llm) == "LMStudioChatModel(model=local-test-model)"
    assert captured["base_url"] == "http://lmstudio.local:1234/v1"
    assert captured["model"] == "local-test-model"
    assert captured["temperature"] == 0.7
    assert captured["timeout"] == 33
    assert captured["api_key"] == "lm-studio"
    assert "lmstudio.local" in os.environ["NO_PROXY"]


def test_comment_generate_comment_uses_env_model_type_without_override(monkeypatch):
    calls = {}

    class FakeLLM:
        def invoke(self, prompt):
            calls["prompt"] = prompt
            return types.SimpleNamespace(content="generated comment")

        def __repr__(self):
            return "LMStudioChatModel(model=local-test-model)"

    def fake_get_chat_model(*, temperature=None, timeout=None, model_type=None):
        calls["temperature"] = temperature
        calls["timeout"] = timeout
        calls["model_type"] = model_type
        return FakeLLM()

    monkeypatch.setenv("MODEL_TYPE", "LM_STUDIO")
    monkeypatch.setattr(comment_views, "get_chat_model", fake_get_chat_model)
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    request = RequestFactory().post(
        "/comment/api/generate_comment/",
        data=json.dumps(
            {
                "student_name": "Tester",
                "performance_grade": "甲上",
                "traits": ["負責任"],
                "temperature": 0.4,
                "timeout": 22,
                "store": False,
            }
        ),
        content_type="application/json",
    )
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")

    response = comment_views.api_generate_comment(request)
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["reply"] == "generated comment"
    assert payload["provider"] == "lm_studio"
    assert calls["model_type"] is None
    assert calls["temperature"] == 0.4
    assert calls["timeout"] == 22
