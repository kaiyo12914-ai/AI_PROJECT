import json
import os

import pytest
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.videolearning.models import VideoAsset


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


@pytest.mark.django_db
def test_import_youtube_success(monkeypatch):
    _allow_acl(monkeypatch)
    monkeypatch.setattr(
        "webapps.videolearning.views.import_youtube_to_media",
        lambda url: {
            "file_path": "/media/videolearning/ext/videos/2026/05/test.mp4",
            "title": "YT 測試片",
            "duration_seconds": 123,
            "thumbnail_url": "https://img.youtube.com/vi/x/default.jpg",
            "source_url": url,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "video_bitrate_kbps": 4500,
            "metadata_json": {"youtube_id": "abc123"},
        },
    )
    client = Client()
    resp = client.post(
        "/videolearning/api/videos/import-youtube/",
        data=json.dumps({"youtube_url": "https://www.youtube.com/watch?v=abc123"}),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content.decode("utf-8", errors="ignore")
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["video"]["title"] == "YT 測試片"
    assert data["data"]["video"]["quality_text"] == "1920x1080 / 30fps / 4500kbps"
    assert VideoAsset.objects.filter(title="YT 測試片", width=1920, height=1080).exists()


@pytest.mark.django_db
def test_import_youtube_url_required(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    resp = client.post(
        "/videolearning/api/videos/import-youtube/",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "YOUTUBE_URL_REQUIRED"


@pytest.mark.django_db
def test_import_youtube_service_error(monkeypatch):
    _allow_acl(monkeypatch)

    from webapps.videolearning.services import YouTubeImportError

    def _raise(_url):
        raise YouTubeImportError("下載失敗")

    monkeypatch.setattr("webapps.videolearning.views.import_youtube_to_media", _raise)
    client = Client()
    resp = client.post(
        "/videolearning/api/videos/import-youtube/",
        data=json.dumps({"youtube_url": "https://youtu.be/abc123"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "YOUTUBE_IMPORT_ERROR"