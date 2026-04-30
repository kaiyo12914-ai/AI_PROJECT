import json
import os
from types import SimpleNamespace

from django.test import RequestFactory

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


class _FakeFilterResult:
    def __init__(self, obj=None):
        self.obj = obj

    def first(self):
        return self.obj


def test_api_conversations_delete_deletes_conversation(monkeypatch):
    _allow_acl(monkeypatch)
    created_logs = []
    deleted = {"flag": False}

    class _FakeConversation:
        def __init__(self):
            self.id = 15
            self.project_id = 4
            self.title = "採購案對話"

        def delete(self):
            deleted["flag"] = True

    conv = _FakeConversation()
    monkeypatch.setattr(views.Conversation.objects, "filter", lambda **kwargs: _FakeFilterResult(conv))
    monkeypatch.setattr(
        views.ActivityLog.objects,
        "create",
        lambda **kwargs: created_logs.append(kwargs) or SimpleNamespace(id=1),
    )

    req = RequestFactory().delete(
        "/projectnotes/conversations/",
        data=json.dumps({"conversation_id": 15}),
        content_type="application/json",
    )
    resp = views.api_conversations(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["deleted"]["id"] == 15
    assert data["deleted"]["title"] == "採購案對話"
    assert deleted["flag"] is True
    assert created_logs[0]["action"] == "conversation_delete"
