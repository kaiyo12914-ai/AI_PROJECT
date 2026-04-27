import os
import json
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


def test_e2e_projectnotes_sources_upload_cp950(monkeypatch):
    """
    E2E (thin): POST /projectnotes/sources/ with non-UTF8 text should still be readable in pipeline.
    """
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(views, "_preprocess_rag_text", lambda s: s.strip())

    source_obj = SimpleNamespace(id=11)
    doc_obj = SimpleNamespace(id=22, title="x", path="x.txt", source_id=11)
    doc_ver_obj = SimpleNamespace(id=33, version_number=1)

    monkeypatch.setattr(views.Source.objects, "create", lambda **kwargs: source_obj)
    monkeypatch.setattr(views.Document.objects, "create", lambda **kwargs: doc_obj)
    monkeypatch.setattr(views.DocumentVersion.objects, "create", lambda **kwargs: doc_ver_obj)

    class _FakeChunk:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _FakeChunkManager:
        @staticmethod
        def bulk_create(objs):
            return None

    _FakeChunk.objects = _FakeChunkManager()
    monkeypatch.setattr(views, "DocumentChunk", _FakeChunk)

    upload = SimpleUploadedFile("cp950.txt", "匯入編碼測試".encode("cp950"), content_type="text/plain")
    client = Client(HTTP_HOST="127.0.0.1")
    resp = client.post("/projectnotes/sources/", data={"project_id": "1", "title": "e2e", "file": upload})
    payload = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert payload["ok"] is True
    assert payload["source"]["chunk_count"] >= 1
    assert payload["is_non_utf8"] is True
    assert payload["detected_encoding"] in {"cp950", "big5"}
