import os
import json
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


def _stub_persistence(monkeypatch, captured):
    source_obj = SimpleNamespace(id=101)
    doc_obj = SimpleNamespace(id=202, title="t", path="f.txt", source_id=101)
    doc_ver_obj = SimpleNamespace(id=303, version_number=1)

    monkeypatch.setattr(views.Source.objects, "create", lambda **kwargs: source_obj)
    monkeypatch.setattr(views.Document.objects, "create", lambda **kwargs: doc_obj)

    def _fake_doc_ver_create(**kwargs):
        captured["raw_text"] = kwargs.get("raw_text", "")
        return doc_ver_obj

    monkeypatch.setattr(views.DocumentVersion.objects, "create", _fake_doc_ver_create)

    class _FakeChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeChunkManager:
        @staticmethod
        def bulk_create(objs):
            captured["bulk_count"] = len(objs)

    _FakeChunk.objects = _FakeChunkManager()
    monkeypatch.setattr(views, "DocumentChunk", _FakeChunk)


def test_api_sources_post_happy_cp950(monkeypatch):
    _allow_acl(monkeypatch)
    captured = {}
    _stub_persistence(monkeypatch, captured)
    monkeypatch.setattr(views, "_preprocess_rag_text", lambda s: s.strip())

    upload = SimpleUploadedFile("a.txt", "中文內容測試".encode("cp950"), content_type="text/plain")
    req = RequestFactory().post("/projectnotes/sources/", {"project_id": "1", "title": "測試", "file": upload})
    resp = views.api_sources(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert "中文內容測試" in captured["raw_text"]
    assert data["detected_encoding"] in {"cp950", "big5"}
    assert data["is_non_utf8"] is True


def test_api_sources_post_boundary_empty_file(monkeypatch):
    _allow_acl(monkeypatch)
    captured = {}
    _stub_persistence(monkeypatch, captured)
    monkeypatch.setattr(views, "_preprocess_rag_text", lambda s: s.strip())

    upload = SimpleUploadedFile("empty.txt", b"", content_type="text/plain")
    req = RequestFactory().post("/projectnotes/sources/", {"project_id": "1", "title": "空檔", "file": upload})
    resp = views.api_sources(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 400
    assert data["ok"] is False
    assert "empty or unreadable content" in data["error"]


def test_api_sources_post_error_binary_unreadable(monkeypatch):
    _allow_acl(monkeypatch)
    captured = {}
    _stub_persistence(monkeypatch, captured)
    monkeypatch.setattr(views, "_preprocess_rag_text", lambda s: s.strip())

    upload = SimpleUploadedFile("bad.bin", b"\xd8\x1d\x17", content_type="application/octet-stream")
    req = RequestFactory().post("/projectnotes/sources/", {"project_id": "1", "title": "壞檔", "file": upload})
    resp = views.api_sources(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 400
    assert data["ok"] is False
    assert "decode failed" in data["error"]
