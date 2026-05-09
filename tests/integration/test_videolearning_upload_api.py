import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


@pytest.mark.django_db
@override_settings(VIDEOLEARNING_MAX_UPLOAD_MB=1)
def test_video_upload_success(monkeypatch, tmp_path):
    _allow_acl(monkeypatch)
    client = Client()
    with override_settings(MEDIA_ROOT=str(tmp_path), MEDIA_URL="/media/"):
        f = SimpleUploadedFile("demo.mp4", b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4")
        resp = client.post("/videolearning/api/videos/upload/", data={"file": f})
        assert resp.status_code == 201, resp.content.decode("utf-8", errors="ignore")
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["upload"]["file_path"].startswith("/media/videolearning/")


@pytest.mark.django_db
def test_video_upload_file_required(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    resp = client.post("/videolearning/api/videos/upload/", data={})
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "FILE_REQUIRED"


@pytest.mark.django_db
def test_video_upload_invalid_extension(monkeypatch, tmp_path):
    _allow_acl(monkeypatch)
    client = Client()
    with override_settings(MEDIA_ROOT=str(tmp_path), MEDIA_URL="/media/"):
        f = SimpleUploadedFile("bad.exe", b"MZ...", content_type="application/octet-stream")
        resp = client.post("/videolearning/api/videos/upload/", data={"file": f})
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "UPLOAD_ERROR"


@pytest.mark.django_db
@override_settings(VIDEOLEARNING_MAX_UPLOAD_MB=1)
def test_video_upload_too_large(monkeypatch, tmp_path):
    _allow_acl(monkeypatch)
    client = Client()
    with override_settings(MEDIA_ROOT=str(tmp_path), MEDIA_URL="/media/"):
        big = b"a" * (1024 * 1024 + 1)
        f = SimpleUploadedFile("big.mp4", big, content_type="video/mp4")
        resp = client.post("/videolearning/api/videos/upload/", data={"file": f})
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False
        assert data["error"]["code"] == "UPLOAD_ERROR"

# py -m pytest tests/integration/test_videolearning_upload_api.py -q