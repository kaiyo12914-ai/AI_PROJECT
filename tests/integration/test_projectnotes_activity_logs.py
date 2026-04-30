import json
import os
from datetime import timedelta
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


def test_api_sources_post_writes_activity_log(monkeypatch):
    _allow_acl(monkeypatch)
    created_logs = []

    monkeypatch.setattr(views, "_preprocess_rag_text", lambda s: s.strip())
    monkeypatch.setattr(
        views.ActivityLog.objects,
        "create",
        lambda **kwargs: created_logs.append(kwargs) or SimpleNamespace(id=1),
    )

    source_obj = SimpleNamespace(id=101, name="測試來源")
    doc_obj = SimpleNamespace(id=202, title="t", path="f.txt", source_id=101)
    doc_ver_obj = SimpleNamespace(id=303, version_number=1)
    monkeypatch.setattr(views.Source.objects, "create", lambda **kwargs: source_obj)
    monkeypatch.setattr(views.Document.objects, "create", lambda **kwargs: doc_obj)
    monkeypatch.setattr(views.DocumentVersion.objects, "create", lambda **kwargs: doc_ver_obj)

    class _FakeChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeChunkManager:
        @staticmethod
        def bulk_create(objs):
            return objs

    _FakeChunk.objects = _FakeChunkManager()
    monkeypatch.setattr(views, "DocumentChunk", _FakeChunk)

    upload = SimpleUploadedFile("a.txt", "中文內容".encode("cp950"), content_type="text/plain")
    req = RequestFactory().post("/projectnotes/sources/", {"project_id": "1", "title": "測試", "file": upload})
    resp = views.api_sources(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert created_logs
    assert created_logs[0]["action"] == "source_upload"
    assert created_logs[0]["target_type"] == "source"
    assert created_logs[0]["detail_json"]["chunk_count"] == 1


class _FakeQuerySet:
    def __init__(self, rows):
        self.rows = list(rows)

    def all(self):
        return _FakeQuerySet(self.rows)

    def select_related(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, **kwargs):
        rows = self.rows
        for key, value in kwargs.items():
            rows = [r for r in rows if getattr(r, key) == value]
        return _FakeQuerySet(rows)

    def __getitem__(self, item):
        return self.rows[item]

    def __iter__(self):
        return iter(self.rows)


def test_audit_logs_and_metrics_api(monkeypatch):
    _allow_acl(monkeypatch)
    now = timezone.now()
    rows = [
        SimpleNamespace(
            id=1,
            project_id=7,
            project=SimpleNamespace(name="專案A"),
            user_id="u1",
            action="chat_query",
            target_type="conversation",
            target_id=88,
            detail_json={"conversation_id": 88, "status": "ok", "latency_ms": 100, "citation_count": 2},
            created_at=now,
        ),
        SimpleNamespace(
            id=2,
            project_id=7,
            project=SimpleNamespace(name="專案A"),
            user_id="u1",
            action="chat_query",
            target_type="conversation",
            target_id=88,
            detail_json={"conversation_id": 88, "status": "insufficient", "latency_ms": 50, "citation_count": 0},
            created_at=now - timedelta(hours=1),
        ),
        SimpleNamespace(
            id=3,
            project_id=7,
            project=SimpleNamespace(name="專案A"),
            user_id="u1",
            action="source_upload",
            target_type="source",
            target_id=5,
            detail_json={"chunk_count": 3},
            created_at=now - timedelta(hours=2),
        ),
    ]

    monkeypatch.setattr(views.ActivityLog, "objects", _FakeQuerySet(rows))

    audit_req = RequestFactory().get("/projectnotes/audit_logs/?project_id=7&limit=10")
    audit_resp = views.api_audit_logs(audit_req)
    audit_data = json.loads(audit_resp.content.decode("utf-8"))

    assert audit_resp.status_code == 200
    assert audit_data["ok"] is True
    assert len(audit_data["rows"]) == 3
    assert audit_data["rows"][0]["action"] == "chat_query"

    metrics_req = RequestFactory().get("/projectnotes/metrics_api/?project_id=7&days=7")
    metrics_resp = views.api_metrics(metrics_req)
    metrics_data = json.loads(metrics_resp.content.decode("utf-8"))

    assert metrics_resp.status_code == 200
    assert metrics_data["ok"] is True
    assert metrics_data["metrics"]["query_count"] == 2
    assert metrics_data["metrics"]["insufficient_count"] == 1
    assert metrics_data["metrics"]["source_upload_count"] == 1
    assert metrics_data["metrics"]["avg_latency_ms"] == 75.0
