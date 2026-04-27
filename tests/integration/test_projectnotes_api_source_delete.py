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
    def __init__(self, *, first_obj=None, values=None, count_value=0):
        self._first_obj = first_obj
        self._values = list(values or [])
        self._count_value = int(count_value)

    def first(self):
        return self._first_obj

    def values_list(self, *_args, **_kwargs):
        return list(self._values)

    def count(self):
        return self._count_value


def test_api_source_delete_happy_path(monkeypatch):
    _allow_acl(monkeypatch)
    deleted = {"flag": False}

    source_obj = SimpleNamespace(id=55, name="測試來源", project_id=7)
    source_obj.delete = lambda: deleted.__setitem__("flag", True)

    monkeypatch.setattr(views.Source.objects, "filter", lambda **kwargs: _FakeFilterResult(first_obj=source_obj))
    monkeypatch.setattr(views.Document.objects, "filter", lambda **kwargs: _FakeFilterResult(values=[101, 102]))
    monkeypatch.setattr(views.DocumentVersion.objects, "filter", lambda **kwargs: _FakeFilterResult(values=[201, 202, 203]))
    monkeypatch.setattr(views.DocumentChunk.objects, "filter", lambda **kwargs: _FakeFilterResult(count_value=9))

    req = RequestFactory().delete("/projectnotes/sources/55/")
    resp = views.api_source_delete(req, 55)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["deleted"]["source_id"] == 55
    assert data["deleted"]["deleted_documents"] == 2
    assert data["deleted"]["deleted_versions"] == 3
    assert data["deleted"]["deleted_chunks"] == 9
    assert deleted["flag"] is True


def test_api_source_delete_boundary_invalid_id(monkeypatch):
    _allow_acl(monkeypatch)
    req = RequestFactory().delete("/projectnotes/sources/0/")
    resp = views.api_source_delete(req, 0)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 400
    assert data["ok"] is False
    assert data["error_code"] == "missing_source_id"


def test_api_source_delete_error_not_found(monkeypatch):
    _allow_acl(monkeypatch)
    monkeypatch.setattr(views.Source.objects, "filter", lambda **kwargs: _FakeFilterResult(first_obj=None))

    req = RequestFactory().delete("/projectnotes/sources/999/")
    resp = views.api_source_delete(req, 999)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 404
    assert data["ok"] is False
    assert data["error_code"] == "source_not_found"
