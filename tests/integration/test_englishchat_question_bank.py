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
from webapps.englishchat.repository import EnglishChatQuestionBankRepository
from webapps.englishchat.services import get_db_question, get_seed_question


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


def test_repository_maps_tuple_rows():
    row = (
        "db-translation-001",
        "travel",
        "translation",
        "beginner",
        "",
        [],
        [],
        "",
        "test",
        "",
        "我想預訂一間房間。",
        "I would like to book a room.",
        ["I would like to + V", "book a room"],
        1,
    )
    mapped = EnglishChatQuestionBankRepository._row_to_dict(row)

    assert mapped["question_id"] == "db-translation-001"
    assert mapped["topic_key"] == "travel"
    assert mapped["zh_prompt"] == "我想預訂一間房間。"


def test_get_db_question_skips_excluded_id(monkeypatch):
    monkeypatch.setattr(
        EnglishChatQuestionBankRepository,
        "fetch_questions",
        lambda self, topic_key, mode, level: [
            {
                "question_id": "q1",
                "zh_prompt": "第一題",
                "sample_answer": "first",
                "explanation_zh": "x",
                "patterns_json": ["p1"],
            },
            {
                "question_id": "q2",
                "zh_prompt": "第二題",
                "sample_answer": "second",
                "explanation_zh": "x",
                "patterns_json": ["p2"],
            },
        ],
    )

    item = get_db_question("travel", "translation", "beginner", ["q1"])
    assert item["question_id"] == "q2"


def test_get_db_question_uses_random_choice_on_available_rows(monkeypatch):
    monkeypatch.setattr(
        EnglishChatQuestionBankRepository,
        "fetch_questions",
        lambda self, topic_key, mode, level: [
            {"question_id": "q1", "zh_prompt": "a", "sample_answer": "a", "explanation_zh": "x", "patterns_json": ["p1"]},
            {"question_id": "q2", "zh_prompt": "b", "sample_answer": "b", "explanation_zh": "x", "patterns_json": ["p2"]},
            {"question_id": "q3", "zh_prompt": "c", "sample_answer": "c", "explanation_zh": "x", "patterns_json": ["p3"]},
        ],
    )
    monkeypatch.setattr("webapps.englishchat.services.random.choice", lambda rows: rows[-1])

    item = get_db_question("travel", "translation", "beginner", ["q1"])
    assert item["question_id"] == "q3"


def test_get_seed_question_differs_by_level():
    beginner = get_seed_question("restaurant", "fill_blank", "beginner", [])
    advanced = get_seed_question("restaurant", "fill_blank", "advanced", [])

    assert beginner is not None
    assert advanced is not None
    assert beginner["question_id"] != advanced["question_id"]


def test_fill_blank_api_differs_by_level(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    beginner_response = views.api_fill_blank_quiz(
        _post_json("/englishchat/quiz/fill_blank/", {"topic": "restaurant", "level": "beginner"})
    )
    advanced_response = views.api_fill_blank_quiz(
        _post_json("/englishchat/quiz/fill_blank/", {"topic": "restaurant", "level": "advanced"})
    )

    beginner = json.loads(beginner_response.content.decode("utf-8"))
    advanced = json.loads(advanced_response.content.decode("utf-8"))

    assert beginner["source"] in {"seed_bank", "question_bank"}
    assert advanced["source"] in {"seed_bank", "question_bank"}
    assert beginner["question_id"] != advanced["question_id"]
