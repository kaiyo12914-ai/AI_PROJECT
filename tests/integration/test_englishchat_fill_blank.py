import json
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
        INSTALLED_APPS=[],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        PORTAL_ACL_BYPASS_NODES_EXT=[],
    )
django.setup()

from webapps.englishchat import views


def _post_json(path, payload):
    request = RequestFactory().post(path, data=json.dumps(payload), content_type="application/json")
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    return request


def test_fill_blank_quiz_returns_llm_question(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.quiz_pipeline.invoke_json",
        lambda prompt, purpose: {
            "question_id": "q1",
            "question": "I usually ____ coffee in the morning.",
            "choices": ["drink", "drinks", "drinking"],
            "answer": "drink",
            "explanation_zh": "主詞是 I，所以動詞用原形。",
            "pattern": "I usually + V ...",
        },
    )
    response = views.api_fill_blank_quiz(_post_json("/englishchat/quiz/fill_blank/", {"topic": "daily life", "level": "beginner"}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["question_id"] == "q1"
    assert payload["source"] == "llm"


def test_fill_blank_quiz_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.quiz_pipeline.invoke_json",
        lambda prompt, purpose: (_ for _ in ()).throw(views.EnglishChatLLMError("failed")),
    )
    response = views.api_fill_blank_quiz(_post_json("/englishchat/quiz/fill_blank/", {"topic": "daily life", "level": "beginner"}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["source"] == "fallback"
    assert payload["question_id"].startswith("fallback-")


def test_check_fill_blank_answer_returns_correct_flag(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    response = views.api_check_fill_blank(
        _post_json("/englishchat/quiz/check/", {"selected": "drink", "answer": "drink", "pattern": "I usually + V ..."})
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["correct"] is True


def test_fill_blank_quiz_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    request = RequestFactory().post("/englishchat/quiz/fill_blank/", data="{bad json", content_type="application/json")
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    response = views.api_fill_blank_quiz(request)
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 400
    assert payload == {"ok": False, "error": "invalid json"}
