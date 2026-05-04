import json
import os
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
    request = RequestFactory().post(
        path,
        data=json.dumps(payload),
        content_type="application/json",
    )
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    return request


def test_fill_blank_quiz_returns_llm_question(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views,
        "_invoke_llm",
        lambda prompt: json.dumps(
            {
                "question_id": "q1",
                "question": "I usually ____ coffee in the morning.",
                "choices": ["drink", "drinks", "drinking"],
                "answer": "drink",
                "explanation_zh": "主詞 I 搭配原形動詞。",
                "pattern": "I usually + V ...",
            },
            ensure_ascii=False,
        ),
    )

    response = views.api_fill_blank_quiz(
        _post_json(
            "/englishchat/quiz/fill_blank/",
            {"topic": "daily life", "level": "beginner"},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["question_id"] == "q1"
    assert payload["answer"] in payload["choices"]
    assert "____" in payload["question"]


def test_fill_blank_quiz_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    def raise_error(prompt):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(views, "_invoke_llm", raise_error)

    response = views.api_fill_blank_quiz(
        _post_json(
            "/englishchat/quiz/fill_blank/",
            {"topic": "daily life", "level": "beginner"},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["question_id"].startswith("fallback-")
    assert payload["answer"] in payload["choices"]


def test_check_fill_blank_answer_returns_correct_flag(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    response = views.api_check_fill_blank(
        _post_json(
            "/englishchat/quiz/check/",
            {
                "selected": "drink",
                "answer": "drink",
                "explanation_zh": "主詞 I 搭配原形動詞。",
                "pattern": "I usually + V ...",
            },
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["correct"] is True
    assert payload["answer"] == "drink"


def test_fill_blank_quiz_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    request = RequestFactory().post(
        "/englishchat/quiz/fill_blank/",
        data="{bad json",
        content_type="application/json",
    )
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")

    response = views.api_fill_blank_quiz(request)
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 400
    assert payload == {"ok": False, "error": "invalid json"}
