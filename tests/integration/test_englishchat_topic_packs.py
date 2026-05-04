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
from webapps.englishchat.topic_packs import find_topic_pack, get_topic_pack_item


def _post_json(path, payload):
    request = RequestFactory().post(path, data=json.dumps(payload), content_type="application/json")
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    return request


def test_topic_pack_lookup_matches_chinese_and_english_labels():
    assert find_topic_pack("travel")
    assert find_topic_pack("旅遊")
    assert get_topic_pack_item("restaurant", "fill_blank")["answer"] == "have"


def test_fill_blank_uses_topic_pack_without_llm(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    def fail_if_called(prompt):
        raise AssertionError("LLM should not be called for topic-pack question")

    monkeypatch.setattr(views, "_invoke_llm", fail_if_called)

    response = views.api_fill_blank_quiz(
        _post_json("/englishchat/quiz/fill_blank/", {"topic": "travel", "level": "beginner"})
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "topic_pack"
    assert payload["question_id"].startswith("pack-travel-")
    assert payload["answer"] in payload["choices"]


def test_reorder_uses_topic_pack_without_llm(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(views, "_invoke_llm", lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))

    response = views.api_reorder_quiz(
        _post_json("/englishchat/quiz/reorder/", {"topic": "meeting", "level": "beginner"})
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "topic_pack"
    assert payload["question_id"].startswith("pack-meeting-")
    assert payload["words"]


def test_translation_uses_topic_pack_without_llm(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(views, "_invoke_llm", lambda prompt: (_ for _ in ()).throw(AssertionError("no llm")))

    response = views.api_translation_quiz(
        _post_json("/englishchat/quiz/translate/", {"topic": "phone", "level": "beginner"})
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "topic_pack"
    assert payload["question_id"].startswith("pack-phone-")
    assert payload["sample_answer"]


def test_unknown_topic_still_falls_back_to_llm_path(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(
        views,
        "_invoke_llm",
        lambda prompt: json.dumps(
            {
                "question_id": "llm-custom-001",
                "question": "I ____ this custom topic.",
                "choices": ["like", "likes", "liking"],
                "answer": "like",
                "explanation_zh": "I 後面接原形動詞。",
                "pattern": "I + V ...",
            },
            ensure_ascii=False,
        ),
    )

    response = views.api_fill_blank_quiz(
        _post_json("/englishchat/quiz/fill_blank/", {"topic": "rare custom topic", "level": "beginner"})
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "llm"
    assert payload["question_id"] == "llm-custom-001"


def test_topic_pack_excludes_seen_question_ids():
    first = get_topic_pack_item("travel", "fill_blank")
    second = get_topic_pack_item("travel", "fill_blank", exclude_ids=[first["question_id"]])

    assert first["question_id"] == "pack-travel-fill-001"
    assert second["question_id"] == "pack-travel-fill-002"


def test_fill_blank_api_returns_next_topic_pack_question(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    response = views.api_fill_blank_quiz(
        _post_json(
            "/englishchat/quiz/fill_blank/",
            {
                "topic": "travel",
                "level": "beginner",
                "seen_question_ids": ["pack-travel-fill-001"],
            },
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "topic_pack"
    assert payload["question_id"] == "pack-travel-fill-002"
