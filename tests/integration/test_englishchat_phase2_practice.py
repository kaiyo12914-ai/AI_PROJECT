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
    request = RequestFactory().post(path, data=json.dumps(payload), content_type="application/json")
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    return request


def test_reorder_quiz_returns_llm_question(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views,
        "_invoke_llm",
        lambda prompt: json.dumps(
            {
                "question_id": "r1",
                "prompt": "Put the words in order.",
                "words": ["like", "I", "travel"],
                "answer": "I like travel.",
                "explanation_zh": "主詞放前面。",
                "pattern": "I + V ...",
            },
            ensure_ascii=False,
        ),
    )

    response = views.api_reorder_quiz(
        _post_json("/englishchat/quiz/reorder/", {"topic": "rare custom topic", "level": "beginner"})
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["question_id"] == "r1"
    assert payload["words"] == ["like", "I", "travel"]
    assert payload["answer"] == "I like travel."


def test_check_reorder_accepts_sentence_without_final_period(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    response = views.api_check_reorder(
        _post_json(
            "/englishchat/quiz/reorder/check/",
            {"user_answer": "I like travel", "answer": "I like travel."},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["correct"] is True


def test_translation_quiz_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    def raise_error(prompt):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(views, "_invoke_llm", raise_error)

    response = views.api_translation_quiz(
        _post_json("/englishchat/quiz/translate/", {"topic": "rare custom topic", "level": "beginner"})
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["question_id"].startswith("fallback-translate-")
    assert payload["zh_prompt"]
    assert payload["sample_answer"]


def test_evaluate_translation_returns_llm_feedback(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views,
        "_invoke_llm",
        lambda prompt: json.dumps(
            {
                "score": 90,
                "corrected": "I like to travel.",
                "feedback_zh": "句子自然。",
                "suggestions": ["I like to + V"],
            },
            ensure_ascii=False,
        ),
    )

    response = views.api_evaluate_translation(
        _post_json(
            "/englishchat/quiz/translate/evaluate/",
            {
                "zh_prompt": "我喜歡旅行。",
                "user_answer": "I like travel.",
                "sample_answer": "I like to travel.",
                "level": "beginner",
            },
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["score"] == 90
    assert payload["corrected"] == "I like to travel."
