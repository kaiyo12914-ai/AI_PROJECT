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


def test_practice_summary_counts_accuracy_and_weak_patterns():
    summary = views._practice_summary(
        [
            {"mode": "fill_blank", "correct": True, "score": 100, "pattern": "I usually + V"},
            {"mode": "reorder", "correct": False, "score": 0, "pattern": "I like to + V"},
            {"mode": "translate", "correct": False, "score": 70, "pattern": "I like to + V"},
        ]
    )

    assert summary["total"] == 3
    assert summary["correct"] == 1
    assert summary["accuracy"] == 33
    assert summary["average_score"] == 57
    assert summary["weak_modes"] == ["reorder", "translate"]
    assert summary["weak_patterns"][0] == "I like to + V"
    assert summary["recommendations"]


def test_practice_summary_api_returns_schema(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)

    response = views.api_practice_summary(
        _post_json(
            "/englishchat/practice/summary/",
            {
                "attempts": [
                    {"mode": "fill_blank", "correct": True, "score": 100, "pattern": "I usually + V"},
                    {"mode": "translate", "correct": False, "score": 65, "pattern": "I like to + V"},
                ]
            },
        )
    )
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["total"] == 2
    assert payload["correct"] == 1
    assert payload["accuracy"] == 50
    assert isinstance(payload["recommendations"], list)


def test_practice_summary_api_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    request = RequestFactory().post("/englishchat/practice/summary/", data="{bad", content_type="application/json")
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")

    response = views.api_practice_summary(request)
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 400
    assert payload == {"ok": False, "error": "invalid json"}
