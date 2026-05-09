import json
import os

import pytest
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()


def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


def _create_video(client: Client) -> int:
    resp = client.post(
        "/videolearning/api/videos/create/",
        data=json.dumps({"title": "T1", "file_path": "/videos/t1.mp4"}),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content.decode("utf-8", errors="ignore")
    return json.loads(resp.content.decode("utf-8"))["data"]["video"]["id"]


@pytest.mark.django_db
def test_upload_transcript_and_generate_chapters(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    video_id = _create_video(client)
    srt = """1
00:00:00,000 --> 00:00:05,000
隤脩?隞晶

2
00:00:05,000 --> 00:00:11,000
??甇仿?
"""
    up = client.post(
        f"/videolearning/api/videos/{video_id}/transcript/upload/",
        data=json.dumps({"format": "srt", "content": srt}),
        content_type="application/json",
    )
    assert up.status_code == 201
    up_data = json.loads(up.content.decode("utf-8"))
    assert up_data["ok"] is True

    gen = client.post(
        f"/videolearning/api/videos/{video_id}/chapters/generate/",
        data=json.dumps({"interval_seconds": 4, "max_chars_per_chapter": 20}),
        content_type="application/json",
    )
    assert gen.status_code == 200
    gen_data = json.loads(gen.content.decode("utf-8"))
    assert gen_data["ok"] is True
    assert len(gen_data["data"]["chapters"]) >= 1


@pytest.mark.django_db
def test_invalid_transcript_format_error(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    video_id = _create_video(client)
    up = client.post(
        f"/videolearning/api/videos/{video_id}/transcript/upload/",
        data=json.dumps({"format": "csv", "content": "x"}),
        content_type="application/json",
    )
    assert up.status_code == 400
    data = json.loads(up.content.decode("utf-8"))
    assert data["ok"] is False
    assert data["error"]["code"] == "TRANSCRIPT_PARSE_ERROR"

