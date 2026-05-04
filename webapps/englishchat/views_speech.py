from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List

import requests
from django.conf import settings
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from webapps.portal.decorators import require_node


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _read_json_body(request: HttpRequest) -> Dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def _api_base(request: HttpRequest) -> str:
    configured = _safe_text(getattr(settings, "TTS_API_BASE_URL", "")).rstrip("/")
    if configured:
        return configured
    return request.build_absolute_uri("/").rstrip("/")


def _service_url(request: HttpRequest, path: str) -> str:
    return f"{_api_base(request)}/{path.lstrip('/')}"


def _timeout() -> int:
    try:
        return int(getattr(settings, "TTS_API_TIMEOUT", 60))
    except Exception:
        return 60


@csrf_exempt
@require_node("englishchat", api=True)
@require_POST
def api_speech_tts(request: HttpRequest):
    body = _read_json_body(request)
    text = _safe_text(body.get("text"))
    if not text:
        return JsonResponse({"ok": False, "error": "text is required"}, status=400)

    model = _safe_text(body.get("model")) or _safe_text(getattr(settings, "ENGLISHCHAT_TTS_MODEL", ""))
    payload = {"text": text}
    if model:
        payload["model"] = model

    try:
        resp = requests.post(
            _service_url(request, "/tts/generate/"),
            json=payload,
            timeout=_timeout(),
        )
        data = resp.json()
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"tts backend failed: {exc}"}, status=200)

    if not isinstance(data, dict):
        return JsonResponse({"ok": False, "error": "tts backend returned invalid data"}, status=200)
    data["backend"] = "tts"
    return JsonResponse(data, status=200)


@csrf_exempt
@require_node("englishchat", api=True)
@require_POST
def api_speech_stt(request: HttpRequest):
    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"ok": False, "error": "audio file is required"}, status=400)

    language = _safe_text(request.POST.get("language") or "en").lower()
    if language not in {"auto", "en", "zh"}:
        return JsonResponse({"ok": False, "error": "language must be auto, en, or zh"}, status=400)

    files = {"audio": (audio.name, audio.file, audio.content_type or "application/octet-stream")}
    try:
        resp = requests.post(
            _service_url(request, "/tts/transcribe/"),
            data={"language": language},
            files=files,
            timeout=_timeout(),
        )
        data = resp.json()
    except Exception as exc:
        return JsonResponse({"ok": False, "error": f"stt backend failed: {exc}"}, status=200)

    if not isinstance(data, dict):
        return JsonResponse({"ok": False, "error": "stt backend returned invalid data"}, status=200)
    data["backend"] = "tts"
    data["language"] = language
    return JsonResponse(data, status=200)


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


@csrf_exempt
@require_node("englishchat", api=True)
@require_POST
def api_speech_evaluate(request: HttpRequest):
    body = _read_json_body(request)
    target = _safe_text(body.get("target"))
    spoken = _safe_text(body.get("spoken"))
    if not target or not spoken:
        return JsonResponse({"ok": False, "error": "target and spoken are required"}, status=400)

    target_tokens = _tokens(target)
    spoken_tokens = _tokens(spoken)
    target_set = set(target_tokens)
    spoken_set = set(spoken_tokens)
    missing = [w for w in target_tokens if w not in spoken_set]
    extra = [w for w in spoken_tokens if w not in target_set]
    similarity = SequenceMatcher(None, " ".join(target_tokens), " ".join(spoken_tokens)).ratio()
    keyword_hit = (len(target_set & spoken_set) / len(target_set)) if target_set else 0
    score = round((similarity * 0.65 + keyword_hit * 0.35) * 100)

    suggestion = "Try again slowly and keep the key words in the same order."
    if score >= 85:
        suggestion = "Good match. Practice once more with natural rhythm."
    elif missing:
        suggestion = f"Practice these missing words: {', '.join(missing[:5])}."

    return JsonResponse(
        {
            "ok": True,
            "score": max(0, min(100, score)),
            "target": target,
            "spoken": spoken,
            "missing_words": missing[:8],
            "extra_words": extra[:8],
            "suggestion": suggestion,
        }
    )
