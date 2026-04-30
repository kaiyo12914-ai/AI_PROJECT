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


def test_api_conversations_patch_renames_conversation(monkeypatch):
    _allow_acl(monkeypatch)
    created_logs = []

    class _FakeConversation:
        def __init__(self):
            self.id = 9
            self.project_id = 3
            self.title = "New Chat"
            self.saved = False

        def save(self, update_fields=None):
            self.saved = True
            self.update_fields = list(update_fields or [])

    conv = _FakeConversation()
    monkeypatch.setattr(views.Conversation.objects, "filter", lambda **kwargs: _FakeFilterResult(conv))
    monkeypatch.setattr(
        views.ActivityLog.objects,
        "create",
        lambda **kwargs: created_logs.append(kwargs) or SimpleNamespace(id=1),
    )

    req = RequestFactory().patch(
        "/projectnotes/conversations/",
        data=json.dumps({"conversation_id": 9, "title": "採購規格討論"}),
        content_type="application/json",
    )
    resp = views.api_conversations(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["conversation"]["title"] == "採購規格討論"
    assert conv.title == "採購規格討論"
    assert conv.saved is True
    assert created_logs[0]["action"] == "conversation_rename"
