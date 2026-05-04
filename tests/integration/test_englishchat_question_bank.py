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


def test_fill_blank_prefers_question_bank(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.views.get_db_question",
        lambda topic, mode, level, exclude_ids: {
            "question_id": "db-fill-001",
            "question": "I would like to ____ a room.",
            "choices": ["book", "take", "bring"],
            "answer": "book",
            "explanation_zh": "test",
            "pattern": "I would like to + V",
        },
    )
    monkeypatch.setattr(views, "_invoke_llm", lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))

    response = views.api_fill_blank_quiz(_post_json("/englishchat/quiz/fill_blank/", {"topic": "travel"}))
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["source"] == "question_bank"
    assert payload["question_id"] == "db-fill-001"


def test_reorder_prefers_question_bank(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.views.get_db_question",
        lambda topic, mode, level, exclude_ids: {
            "question_id": "db-reorder-001",
            "prompt": "Put the words in the correct order.",
            "words": ["I", "like", "to", "travel"],
            "answer": "I like to travel.",
            "explanation_zh": "test",
            "pattern": "I like to + V",
        },
    )
    monkeypatch.setattr(views, "_invoke_llm", lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))

    response = views.api_reorder_quiz(_post_json("/englishchat/quiz/reorder/", {"topic": "travel"}))
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["source"] == "question_bank"
    assert payload["question_id"] == "db-reorder-001"


def test_translation_prefers_question_bank(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        "webapps.englishchat.views.get_db_question",
        lambda topic, mode, level, exclude_ids: {
            "question_id": "db-translation-001",
            "zh_prompt": "我想預訂一間房間。",
            "sample_answer": "I would like to book a room.",
            "explanation_zh": "test",
            "patterns": ["I would like to + V", "book a room"],
        },
    )
    monkeypatch.setattr(views, "_invoke_llm", lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))

    response = views.api_translation_quiz(_post_json("/englishchat/quiz/translate/", {"topic": "travel"}))
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["source"] == "question_bank"
    assert payload["question_id"] == "db-translation-001"
