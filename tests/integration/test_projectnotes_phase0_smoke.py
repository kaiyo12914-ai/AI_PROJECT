import json
import os
from types import SimpleNamespace
from pathlib import Path

from django.test import RequestFactory

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes import views


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


def test_portal_template_contains_projectnotes_entry():
    text = (Path(__file__).resolve().parents[2] / "webapps/portal/templates/portal/index.html").read_text(encoding="utf-8")
    assert '{% allow "projectnotes" as can_projectnotes %}' in text
    assert "{% url 'projectnotes:page' as projectnotes_href %}" in text


def test_projectnotes_index_render_smoke(monkeypatch):
    _allow_acl(monkeypatch)
    req = RequestFactory().get("/projectnotes/")
    resp = views.index(req)
    assert resp.status_code == 200


class _ProjectQuerySet:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def __getitem__(self, item):
        return self._rows[item]


class _SourceCountQuerySet:
    @staticmethod
    def count():
        return 0


class _SourceObjects:
    @staticmethod
    def filter(**_kwargs):
        return _SourceCountQuerySet()


def test_api_projects_get_response_schema_smoke(monkeypatch):
    _allow_acl(monkeypatch)
    fake_rows = [
        SimpleNamespace(
            id=1,
            name="P1",
            description="desc",
            updated_at=None,
        )
    ]
    monkeypatch.setattr(views.Project, "objects", _ProjectQuerySet(fake_rows))
    monkeypatch.setattr(views.Source, "objects", _SourceObjects())

    req = RequestFactory().get("/projectnotes/projects/")
    resp = views.api_projects(req)
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert isinstance(data.get("projects"), list)
    assert "can_manage_projects" in data
    assert data["projects"][0]["id"] == 1
    assert "source_count" in data["projects"][0]


def test_api_sources_and_chat_error_schema_smoke(monkeypatch):
    _allow_acl(monkeypatch)

    src_req = RequestFactory().get("/projectnotes/sources/")
    src_resp = views.api_sources(src_req)
    src_data = json.loads(src_resp.content.decode("utf-8"))
    assert src_resp.status_code == 400
    assert src_data["ok"] is False
    assert "error" in src_data

    chat_req = RequestFactory().post(
        "/projectnotes/chat/",
        data=json.dumps({}),
        content_type="application/json",
    )
    chat_resp = views.api_chat(chat_req)
    chat_data = json.loads(chat_resp.content.decode("utf-8"))
    assert chat_resp.status_code == 400
    assert chat_data["ok"] is False
    assert "error" in chat_data
