import json
import os
from pathlib import Path

from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


def test_portal_template_contains_videolearning_entry():
    text = (Path(__file__).resolve().parents[2] / "webapps/portal/templates/portal/index.html").read_text(encoding="utf-8")
    assert '{% allow "videolearning" as can_videolearning %}' in text
    assert "{% url 'videolearning:page' as videolearning_href %}" in text


def test_videolearning_index_smoke(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    resp = client.get("/videolearning/")
    assert resp.status_code == 200


def test_videolearning_health_api_smoke(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    resp = client.get("/videolearning/api/health/")
    data = json.loads(resp.content.decode("utf-8"))

    assert resp.status_code == 200
    assert data["ok"] is True
    assert isinstance(data["data"], dict)
    assert data["data"]["service"] == "videolearning"
    assert data["data"]["status"] == "healthy"
    assert data["error"] is None
