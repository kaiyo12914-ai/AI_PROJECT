import json
import os
from pathlib import Path

import pytest
from django.test import Client
from django.test.utils import override_settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.videolearning.models import VideoAsset


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


@pytest.mark.django_db
def test_create_video_success(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    payload = {
        "title": "AI Intro",
        "description": "demo",
        "file_path": "/videos/ai-intro.mp4",
        "category_name": "AI",
        "tag_names": ["intro", "demo"],
        "duration_seconds": 120,
        "visibility": "private",
        "status": "draft",
    }
    resp = client.post(
        "/videolearning/api/videos/create/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    data = json.loads(resp.content.decode("utf-8"))
    assert resp.status_code == 201
    assert data["ok"] is True
    assert data["data"]["video"]["title"] == "AI Intro"
    assert VideoAsset.objects.filter(title="AI Intro").exists()


@pytest.mark.django_db
def test_create_video_title_blank(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    payload = {"title": "   ", "file_path": "/videos/blank.mp4"}
    resp = client.post(
        "/videolearning/api/videos/create/",
        data=json.dumps(payload),
        content_type="application/json",
    )
    data = json.loads(resp.content.decode("utf-8"))
    assert resp.status_code == 400
    assert data["ok"] is False
    assert data["error"]["code"] == "TITLE_REQUIRED"


@pytest.mark.django_db
def test_permission_denied(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: False)
    client = Client()
    resp = client.post(
        "/videolearning/api/videos/create/",
        data=json.dumps({"title": "x", "file_path": "/videos/x.mp4"}),
        content_type="application/json",
    )
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_video_not_found(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    resp = client.get("/videolearning/api/videos/999999/")
    data = json.loads(resp.content.decode("utf-8"))
    assert resp.status_code == 404
    assert data["ok"] is False
    assert data["error"]["code"] == "VIDEO_NOT_FOUND"


@pytest.mark.django_db
def test_delete_video_also_deletes_physical_file(monkeypatch, tmp_path: Path):
    _allow_acl(monkeypatch)
    media_root = tmp_path / "media"
    video_dir = media_root / "videolearning" / "ext" / "videos" / "2026" / "05"
    video_dir.mkdir(parents=True, exist_ok=True)
    file_abs = video_dir / "to-delete.mp4"
    file_abs.write_bytes(b"demo")

    video = VideoAsset.objects.create(
        title="Delete Me",
        file_path="/media/videolearning/ext/videos/2026/05/to-delete.mp4",
    )

    client = Client()
    with override_settings(MEDIA_ROOT=str(media_root), MEDIA_URL="/media/"):
        resp = client.post(f"/videolearning/api/videos/{video.id}/delete/")

    data = json.loads(resp.content.decode("utf-8"))
    assert resp.status_code == 200
    assert data["ok"] is True
    assert data["data"]["deleted"]["file_deleted"] is True
    assert not file_abs.exists()
    assert not VideoAsset.objects.filter(id=video.id).exists()
