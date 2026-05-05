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


def test_reorder_quiz_returns_llm_question(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.quiz_pipeline.invoke_json",
        lambda prompt, purpose: {
            "question_id": "r1",
            "prompt": "Put the words in order.",
            "words": ["like", "I", "to", "travel"],
            "answer": "I like to travel.",
            "explanation_zh": "依照正常英文語序排列。",
            "pattern": "I like to + V",
        },
    )
    response = views.api_reorder_quiz(_post_json("/englishchat/quiz/reorder/", {"topic": "custom", "level": "beginner"}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["question_id"] == "r1"
    assert payload["source"] == "llm"


def test_check_reorder_accepts_sentence_without_final_period(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    response = views.api_check_reorder(_post_json("/englishchat/quiz/reorder/check/", {"user_answer": "I like to travel", "answer": "I like to travel."}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["correct"] is True


def test_translation_quiz_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.quiz_pipeline.invoke_json",
        lambda prompt, purpose: (_ for _ in ()).throw(views.EnglishChatLLMError("failed")),
    )
    response = views.api_translation_quiz(_post_json("/englishchat/quiz/translate/", {"topic": "custom", "level": "beginner"}))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["source"] == "fallback"
    assert payload["zh_prompt"]


def test_evaluate_translation_returns_llm_feedback(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views,
        "invoke_json",
        lambda prompt, purpose: {
            "score": 90,
            "corrected": "I like to travel.",
            "feedback_zh": "語意正確，補上 to 會更自然。",
            "suggestions": ["I like to + V"],
        },
    )
    response = views.api_evaluate_translation(
        _post_json(
            "/englishchat/quiz/translate/evaluate/",
            {"zh_prompt": "我喜歡旅遊。", "user_answer": "I like travel.", "sample_answer": "I like to travel.", "level": "beginner"},
        )
    )
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 200
    assert payload["score"] == 90
