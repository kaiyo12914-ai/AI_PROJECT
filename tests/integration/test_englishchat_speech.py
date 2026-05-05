import json
import types
from pathlib import Path

import django
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        DEBUG=True,
        DEFAULT_CHARSET="utf-8",
        ROOT_URLCONF="webproj.urls",
        INSTALLED_APPS=[],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        PORTAL_ACL_BYPASS_NODES_EXT=[],
        ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    )
django.setup()

from webapps.englishchat import views_speech
from webapps.tts import views as tts_views


def _attach_user(request):
    request.session = {}
    request.user = types.SimpleNamespace(is_authenticated=True, username="tester")
    return request


def test_speech_evaluate_scores_and_reports_missing_words(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    request = RequestFactory().post(
        "/englishchat/speech/evaluate/",
        data=json.dumps({"target": "I would like to book a room.", "spoken": "I like book room"}),
        content_type="application/json",
    )

    response = views_speech.api_speech_evaluate(_attach_user(request))
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["score"] < 100
    assert "would" in payload["missing_words"]


def test_englishchat_tts_wrapper_calls_tts_backend(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(views_speech.settings, "TTS_API_BASE_URL", "http://127.0.0.1:8000", raising=False)
    seen = {}

    class FakeResponse:
        def json(self):
            return {"ok": True, "wav_url": "/media/tts/test.wav"}

    def fake_post(url, json=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(views_speech.requests, "post", fake_post)
    request = RequestFactory().post(
        "/englishchat/speech/tts/",
        data=json.dumps({"text": "Please repeat this sentence."}),
        content_type="application/json",
        HTTP_HOST="testserver",
    )

    response = views_speech.api_speech_tts(_attach_user(request))
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["backend"] == "tts"
    assert seen["url"].endswith("/tts/generate/")
    assert seen["json"]["text"] == "Please repeat this sentence."


def test_englishchat_tts_wrapper_returns_502_when_backend_fails(monkeypatch):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    monkeypatch.setattr(views_speech.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    request = RequestFactory().post(
        "/englishchat/speech/tts/",
        data=json.dumps({"text": "Please repeat this sentence."}),
        content_type="application/json",
        HTTP_HOST="testserver",
    )
    response = views_speech.api_speech_tts(_attach_user(request))
    payload = json.loads(response.content.decode("utf-8"))
    assert response.status_code == 502
    assert payload["ok"] is False


def test_tts_stt_accepts_english_language(monkeypatch, tmp_path):
    monkeypatch.setattr("webapps.portal.decorators.can_access", lambda user, node: True)
    whisper_exe = tmp_path / "whisper-cli.exe"
    whisper_model = tmp_path / "ggml.bin"
    whisper_exe.write_text("stub", encoding="utf-8")
    whisper_model.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(tts_views.settings, "WHISPER_EXE", str(whisper_exe), raising=False)
    monkeypatch.setattr(tts_views.settings, "WHISPER_MODEL", str(whisper_model), raising=False)
    monkeypatch.setattr(tts_views.settings, "STT_OUTPUT_DIR", tmp_path, raising=False)

    captured = {}

    def fake_run(cmd, stdout=None, stderr=None, check=False):
        captured["cmd"] = cmd
        out_prefix = cmd[cmd.index("-of") + 1]
        Path(str(out_prefix) + ".txt").write_text("hello world", encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(tts_views.subprocess, "run", fake_run)
    upload = SimpleUploadedFile("speech.wav", b"fake wav", content_type="audio/wav")
    request = RequestFactory().post("/tts/transcribe/", data={"audio": upload, "language": "en"})

    response = tts_views.api_stt_transcribe(_attach_user(request))
    payload = json.loads(response.content.decode("utf-8"))

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["language"] == "en"
    assert "-l" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("-l") + 1] == "en"
