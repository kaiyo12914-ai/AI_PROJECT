import json
import os

import pytest
from django.test import Client

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

def _allow_acl(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)


def _create_video(client: Client, title: str, file_path: str) -> int:
    resp = client.post(
        "/videolearning/api/videos/create/",
        data=json.dumps({"title": title, "file_path": file_path}),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content.decode("utf-8", errors="ignore")
    payload = json.loads(resp.content.decode("utf-8"))
    return payload["data"]["video"]["id"]


@pytest.mark.django_db
def test_create_playlist_success(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    resp = client.post(
        "/videolearning/api/playlists/create/",
        data=json.dumps({"title": "AI Onboarding", "visibility": "department"}),
        content_type="application/json",
    )
    data = json.loads(resp.content.decode("utf-8"))
    assert resp.status_code == 201, resp.content.decode("utf-8", errors="ignore")
    assert data["ok"] is True
    assert data["data"]["playlist"]["title"] == "AI Onboarding"


@pytest.mark.django_db
def test_playlist_add_video_and_detail(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    v1 = _create_video(client, "Video 1", "/videos/v1.mp4")
    v2 = _create_video(client, "Video 2", "/videos/v2.mp4")

    p_resp = client.post(
        "/videolearning/api/playlists/create/",
        data=json.dumps({"title": "Series A"}),
        content_type="application/json",
    )
    playlist_id = json.loads(p_resp.content.decode("utf-8"))["data"]["playlist"]["id"]

    for video_id in (v1, v2):
        resp = client.post(
            f"/videolearning/api/playlists/{playlist_id}/add-video/",
            data=json.dumps({"video_id": video_id}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        payload = json.loads(resp.content.decode("utf-8"))
        assert payload["ok"] is True

    detail = client.get(f"/videolearning/api/playlists/{playlist_id}/")
    detail_payload = json.loads(detail.content.decode("utf-8"))
    assert detail.status_code == 200
    assert detail_payload["ok"] is True
    items = detail_payload["data"]["playlist"]["items"]
    assert len(items) == 2
    assert [x["order_index"] for x in items] == [1, 2]


@pytest.mark.django_db
def test_playlist_reorder_success(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    v1 = _create_video(client, "Video 1", "/videos/v1.mp4")
    v2 = _create_video(client, "Video 2", "/videos/v2.mp4")

    p_resp = client.post(
        "/videolearning/api/playlists/create/",
        data=json.dumps({"title": "Series B"}),
        content_type="application/json",
    )
    playlist_id = json.loads(p_resp.content.decode("utf-8"))["data"]["playlist"]["id"]

    first = client.post(
        f"/videolearning/api/playlists/{playlist_id}/add-video/",
        data=json.dumps({"video_id": v1}),
        content_type="application/json",
    )
    second = client.post(
        f"/videolearning/api/playlists/{playlist_id}/add-video/",
        data=json.dumps({"video_id": v2}),
        content_type="application/json",
    )
    item_ids = [
        json.loads(first.content.decode("utf-8"))["data"]["playlist"]["items"][0]["id"],
        json.loads(second.content.decode("utf-8"))["data"]["playlist"]["items"][1]["id"],
    ]

    reorder = client.post(
        f"/videolearning/api/playlists/{playlist_id}/reorder/",
        data=json.dumps({"item_ids": [item_ids[1], item_ids[0]]}),
        content_type="application/json",
    )
    payload = json.loads(reorder.content.decode("utf-8"))
    assert reorder.status_code == 200
    assert payload["ok"] is True
    reordered = payload["data"]["playlist"]["items"]
    assert [x["order_index"] for x in reordered] == [1, 2]
    assert reordered[0]["video"]["id"] == v2
    assert reordered[1]["video"]["id"] == v1


@pytest.mark.django_db
def test_playlist_add_video_not_found(monkeypatch):
    _allow_acl(monkeypatch)
    client = Client()
    p_resp = client.post(
        "/videolearning/api/playlists/create/",
        data=json.dumps({"title": "Series C"}),
        content_type="application/json",
    )
    playlist_id = json.loads(p_resp.content.decode("utf-8"))["data"]["playlist"]["id"]

    resp = client.post(
        f"/videolearning/api/playlists/{playlist_id}/add-video/",
        data=json.dumps({"video_id": 999999}),
        content_type="application/json",
    )
    data = json.loads(resp.content.decode("utf-8"))
    assert resp.status_code == 404
    assert data["ok"] is False
    assert data["error"]["code"] == "VIDEO_NOT_FOUND"

