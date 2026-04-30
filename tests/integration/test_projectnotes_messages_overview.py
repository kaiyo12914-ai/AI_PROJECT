import json
import os
from types import SimpleNamespace

from django.test import RequestFactory
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


class _FakeManager:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, **kwargs):
        rows = self.rows
        for key, value in kwargs.items():
            if key.endswith("__in"):
                attr = key[:-4]
                rows = [r for r in rows if _resolve_attr(r, attr) in value]
            else:
                rows = [r for r in rows if _resolve_attr(r, key) == value]
        return _FakeQuerySet(rows)

    def order_by(self, *_args, **_kwargs):
        return _FakeQuerySet(self.rows)

    def all(self):
        return _FakeQuerySet(self.rows)

    def exists(self):
        return bool(self.rows)


class _FakeQuerySet:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, **kwargs):
        return _FakeManager(self.rows).filter(**kwargs)

    def order_by(self, *_args, **_kwargs):
        return self

    def prefetch_related(self, *_args, **_kwargs):
        return self

    def select_related(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def exists(self):
        return bool(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, item):
        return self.rows[item]


def _resolve_attr(obj, path):
    current = obj
    for part in path.split("__"):
        current = getattr(current, part)
    return current


def test_api_messages_returns_chat_and_citations(monkeypatch):
    _allow_acl(monkeypatch)

    source = SimpleNamespace(id=11, name="採購文件")
    doc = SimpleNamespace(source=source)
    doc_ver = SimpleNamespace(document=doc)
    chunk = SimpleNamespace(chunk_index=7, content="決議本案續行辦理。", document_version=doc_ver)
    citation = SimpleNamespace(citation_text="C1", document_chunk=chunk)

    class _CitationList:
        def all(self):
            return [citation]

    conv = SimpleNamespace(id=5, project_id=9, title="New Chat", project=SimpleNamespace(id=9, name="P"))
    msg_user = SimpleNamespace(
        id=21,
        conversation_id=5,
        sender_type="user",
        sender_id="u1",
        content="詢問內容",
        created_at=timezone.now(),
        citations=_CitationList(),
    )
    msg_ai = SimpleNamespace(
        id=22,
        conversation_id=5,
        sender_type="assistant",
        sender_id="system",
        content="回答內容",
        created_at=timezone.now(),
        citations=_CitationList(),
    )

    monkeypatch.setattr(views.Conversation, "objects", _FakeManager([conv]))
    monkeypatch.setattr(views.Message, "objects", _FakeManager([msg_user, msg_ai]))

    req = RequestFactory().get("/projectnotes/messages/?conversation_id=5")
    resp = views.api_messages(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["conversation"]["id"] == 5
    assert len(data["messages"]) == 2
    assert data["messages"][1]["citations"][0]["source_id"] == 11
    assert data["messages"][1]["citations"][0]["chunk_index"] == 7


def test_api_citation_click_writes_activity(monkeypatch):
    _allow_acl(monkeypatch)
    created_logs = []
    monkeypatch.setattr(
        views.ActivityLog.objects,
        "create",
        lambda **kwargs: created_logs.append(kwargs) or SimpleNamespace(id=1),
    )

    req = RequestFactory().post(
        "/projectnotes/citation_click/",
        data=json.dumps(
            {
                "project_id": 9,
                "conversation_id": 5,
                "source_id": 11,
                "chunk_index": 7,
                "ref": "C1",
                "excerpt": "決議本案續行辦理。",
            }
        ),
        content_type="application/json",
    )
    resp = views.api_citation_click(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert created_logs
    assert created_logs[0]["action"] == "citation_click"
    assert created_logs[0]["detail_json"]["conversation_id"] == 5


def test_api_overview_returns_summary_and_lists(monkeypatch):
    _allow_acl(monkeypatch)
    now = timezone.now()

    source_rows = [
        SimpleNamespace(id=11, project_id=9, name="採購文件"),
        SimpleNamespace(id=12, project_id=9, name="履約須知"),
    ]
    doc = SimpleNamespace(id=31, source=source_rows[0])
    doc2 = SimpleNamespace(id=32, source=source_rows[1])
    ver_rows = [
        SimpleNamespace(id=41, document_id=31, document=doc),
        SimpleNamespace(id=42, document_id=32, document=doc2),
    ]
    chunk_rows = [
        {
            "chunk_index": 1,
            "content": "本案決議續行採購程序，並依規定辦理。",
            "document_version__document__source__name": "採購文件",
        },
        {
            "chunk_index": 2,
            "content": "履約文件說明驗收與交付要求。",
            "document_version__document__source__name": "履約須知",
        },
    ]
    activity_rows = [
        SimpleNamespace(
            project_id=9,
            action="chat_query",
            detail_json={"query": "何謂巨額採購"},
            created_at=now,
        ),
        SimpleNamespace(
            project_id=9,
            action="source_upload",
            detail_json={"status": "ok"},
            created_at=now,
        ),
    ]

    monkeypatch.setattr(views.Project, "objects", _FakeManager([SimpleNamespace(id=9)]))
    monkeypatch.setattr(views.Source, "objects", _FakeManager(source_rows))
    monkeypatch.setattr(views.DocumentVersion, "objects", _FakeManager(ver_rows))

    class _FakeChunkValues:
        def __init__(self, rows):
            self.rows = rows

        def values(self, *_args, **_kwargs):
            return list(self.rows)

    class _FakeChunkManager:
        def filter(self, **kwargs):
            assert sorted(kwargs["document_version_id__in"]) == [41, 42]
            return _FakeChunkValues(chunk_rows)

    monkeypatch.setattr(views.DocumentChunk, "objects", _FakeChunkManager())
    monkeypatch.setattr(views.ActivityLog, "objects", _FakeManager(activity_rows))

    req = RequestFactory().get("/projectnotes/overview/?project_id=9")
    resp = views.api_overview(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert "2 份來源" in data["overview"]["summary"]
    assert data["overview"]["faq"] == ["何謂巨額採購"]
    assert data["overview"]["keywords"]
    assert data["overview"]["decisions"]
