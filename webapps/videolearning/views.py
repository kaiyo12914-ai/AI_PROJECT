from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings

from webapps.portal.decorators import require_node
from webapps.portal.identity import resolve_effective_user_id
from .models import (
    VideoAsset,
    VideoCategory,
    VideoChapter,
    VideoPlaylist,
    VideoPlaylistItem,
    VideoTag,
    VideoTranscript,
)
from .services import (
    TranscriptParseError,
    VideoUploadError,
    YouTubeImportError,
    generate_chapters_rule_based,
    import_youtube_to_media,
    parse_srt_transcript,
    parse_txt_transcript,
    parse_vtt_transcript,
    save_uploaded_video,
)


def _can_delete_video(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    is_admin = bool(user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)))
    current_user_id = resolve_effective_user_id(request, user).lower()
    return is_admin or current_user_id == "h121356578"


def _render_index_with_tab(request: HttpRequest, active_tab: str) -> HttpResponse:
    return render(
        request,
        "videolearning/index.html",
        {
            "csrf_token": get_token(request),
            "active_tab": active_tab,
            "can_delete_video": _can_delete_video(request),
        },
    )


@require_node("videolearning")
def index(request: HttpRequest) -> HttpResponse:
    return _render_index_with_tab(request, "query")


@require_node("videolearning")
def import_page(request: HttpRequest) -> HttpResponse:
    return _render_index_with_tab(request, "import")


@require_node("videolearning")
def transcode_page(request: HttpRequest) -> HttpResponse:
    return _render_index_with_tab(request, "transcode")


@require_node("videolearning")
def detail(request: HttpRequest, video_id: int) -> HttpResponse:
    return render(
        request,
        "videolearning/detail.html",
        {"video_id": video_id, "csrf_token": get_token(request)},
    )


def _ok(data: dict, status: int = 200) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data, "error": None}, status=status)


def _err(code: str, message: str, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "data": None, "error": {"code": code, "message": message}},
        status=status,
    )


def _read_json(request: HttpRequest) -> dict | None:
    try:
        raw = request.body or b"{}"
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _as_video_dict(video: VideoAsset) -> dict:
    latest_transcript = video.transcripts.order_by("-updated_at", "-id").first()
    chapters = list(video.chapters.order_by("order_index", "id"))
    prefix= str(getattr(settings, 'PROXY_PREFIX'))

    return {
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "category": (
            {"id": video.category_id, "name": video.category.name}
            if video.category_id and video.category
            else None
        ),
        "tags": [{"id": t.id, "name": t.name} for t in video.tags.all().order_by("name")],
        "file_path": video.file_path,
        "thumbnail_path": prefix+video.thumbnail_path,
        "duration_seconds": video.duration_seconds,
        "width": video.width,
        "height": video.height,
        "fps": float(video.fps) if video.fps is not None else None,
        "video_bitrate_kbps": video.video_bitrate_kbps,
        "metadata_json": video.metadata_json or {},
        "quality_text": _build_quality_text(video.width, video.height, video.fps, video.video_bitrate_kbps),
        "owner": video.owner,
        "visibility": video.visibility,
        "status": video.status,
        "created_at": video.created_at.isoformat(),
        "updated_at": video.updated_at.isoformat(),
        "latest_transcript": _as_transcript_dict(latest_transcript) if latest_transcript else None,
        "chapters": [_as_chapter_dict(c) for c in chapters],
    }


def _build_quality_text(width, height, fps, bitrate_kbps) -> str:
    parts: list[str] = []
    if width and height:
        parts.append(f"{int(width)}x{int(height)}")
    if fps:
        parts.append(f"{float(fps):g}fps")
    if bitrate_kbps:
        parts.append(f"{int(bitrate_kbps)}kbps")
    return " / ".join(parts)


def _parse_or_create_category(name: str | None) -> VideoCategory | None:
    n = (name or "").strip()
    if not n:
        return None
    obj, _ = VideoCategory.objects.get_or_create(name=n)
    return obj


def _parse_or_create_tags(tag_names: list[str] | None) -> list[VideoTag]:
    out: list[VideoTag] = []
    if not tag_names:
        return out
    seen: set[str] = set()
    for raw in tag_names:
        n = (raw or "").strip()
        if not n:
            continue
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        obj, _ = VideoTag.objects.get_or_create(name=n)
        out.append(obj)
    return out


def _as_playlist_dict(playlist: VideoPlaylist) -> dict:
    items = (
        playlist.items.select_related("video", "video__category")
        .prefetch_related("video__tags")
        .all()
    )
    return {
        "id": playlist.id,
        "title": playlist.title,
        "description": playlist.description,
        "owner": playlist.owner,
        "visibility": playlist.visibility,
        "created_at": playlist.created_at.isoformat(),
        "updated_at": playlist.updated_at.isoformat(),
        "items": [
            {
                "id": item.id,
                "order_index": item.order_index,
                "video": _as_video_dict(item.video),
            }
            for item in items
        ],
    }


def _as_transcript_dict(transcript: VideoTranscript) -> dict:
    return {
        "id": transcript.id,
        "video_id": transcript.video_id,
        "source_type": transcript.source_type,
        "format": transcript.format,
        "language": transcript.language,
        "content": transcript.content,
        "cues_json": transcript.cues_json,
        "created_at": transcript.created_at.isoformat(),
        "updated_at": transcript.updated_at.isoformat(),
    }


def _as_chapter_dict(chapter: VideoChapter) -> dict:
    return {
        "id": chapter.id,
        "video_id": chapter.video_id,
        "transcript_id": chapter.transcript_id,
        "title": chapter.title,
        "summary": chapter.summary,
        "start_seconds": chapter.start_seconds,
        "end_seconds": chapter.end_seconds,
        "order_index": chapter.order_index,
        "created_at": chapter.created_at.isoformat(),
        "updated_at": chapter.updated_at.isoformat(),
    }


def _parse_transcript_by_format(fmt: str, content: str) -> list[dict]:
    f = (fmt or "").strip().lower()
    if f == VideoTranscript.FORMAT_TXT:
        return parse_txt_transcript(content)
    if f == VideoTranscript.FORMAT_SRT:
        return parse_srt_transcript(content)
    if f == VideoTranscript.FORMAT_VTT:
        return parse_vtt_transcript(content)
    raise TranscriptParseError("Unsupported transcript format.")


def _resolve_owner(request: HttpRequest) -> str:
    return resolve_effective_user_id(request)


def _resolve_media_abs_path(file_path: str) -> Path | None:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    if not file_path:
        return None

    raw = str(file_path).strip()
    parsed = urlparse(raw)
    path_part = unquote(parsed.path or raw)
    if not path_part:
        return None

    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    normalized = path_part.replace("\\", "/")
    if normalized.startswith(media_url):
        normalized = normalized[len(media_url):]
    elif normalized.startswith("/media/"):
        normalized = normalized[len("/media/"):]
    elif normalized.startswith("/"):
        normalized = normalized[1:]

    candidate = (media_root / normalized).resolve()
    if candidate == media_root or media_root in candidate.parents:
        return candidate
    return None


def _parse_http_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    raw = str(range_header or "").strip()
    if not raw.startswith("bytes="):
        return None
    part = raw[6:].split(",", 1)[0].strip()
    if "-" not in part:
        return None
    start_s, end_s = part.split("-", 1)
    try:
        if start_s == "":
            suffix_len = int(end_s)
            if suffix_len <= 0:
                return None
            start = max(0, file_size - suffix_len)
            end = file_size - 1
            return (start, end)
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    except Exception:
        return None
    if start < 0 or end < start or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return (start, end)


def _iter_file_range(path: Path, start: int, end: int, chunk_size: int = 64 * 1024):
    with path.open("rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = f.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _make_media_url(abs_path: Path) -> str:
    rel_from_media = abs_path.relative_to(Path(settings.MEDIA_ROOT))
    rel_url = "/".join(rel_from_media.parts)
    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    if not media_url.endswith("/"):
        media_url += "/"
    return f"{media_url}{rel_url}"


def _thumbnail_root_for_current_env() -> Path:
    env_name = str(getattr(settings, "ENV_NAME", "EXT") or "EXT").upper()
    env_key = "int" if env_name == "INT" else "ext"
    return Path(settings.MEDIA_ROOT) / "videolearning" / env_key / "thumbnails"


def _download_thumbnail_url_to_media(url: str, seed: str = "") -> str:
    raw = str(url or "").strip()
    if not (raw.startswith("http://") or raw.startswith("https://")):
        return raw
    try:
        parsed = urlparse(raw)
        ext = Path(parsed.path or "").suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
        now = datetime.now()
        root = _thumbnail_root_for_current_env() / f"{now.year:04d}" / f"{now.month:02d}"
        root.mkdir(parents=True, exist_ok=True)
        safe_seed = re.sub(r"[^a-zA-Z0-9_-]+", "_", seed or "") or uuid.uuid4().hex[:8]
        name = f"{now.strftime('%Y%m%d_%H%M%S')}_{safe_seed}_{uuid.uuid4().hex[:6]}{ext}"
        out = root / name
        req = Request(raw, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp, open(out, "wb") as f:
            f.write(resp.read())
        return _make_media_url(out)
    except Exception:
        return ""


def _ensure_int_local_thumbnail(video: VideoAsset) -> None:
    env_name = str(getattr(settings, "ENV_NAME", "EXT") or "EXT").upper()
    # Backfill should run on EXT (internet available) and also allow INT retry.
    if env_name not in {"EXT", "INT"}:
        return
    current = str(video.thumbnail_path or "").strip()
    if not (current.startswith("http://") or current.startswith("https://")):
        return
    try:
        parsed = urlparse(current)
        ext = Path(parsed.path or "").suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
        now = datetime.now()
        # Always build INT thumbnail path so assets can be copied to intranet.
        root = Path(settings.MEDIA_ROOT) / "videolearning" / "int" / "thumbnails" / f"{now.year:04d}" / f"{now.month:02d}"
        root.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(video.id))
        name = f"{now.strftime('%Y%m%d_%H%M%S')}_{safe_id}_{uuid.uuid4().hex[:6]}{ext}"
        out = root / name
        req = Request(current, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp, open(out, "wb") as f:
            f.write(resp.read())
        video.thumbnail_path = _make_media_url(out)
        video.save(update_fields=["thumbnail_path", "updated_at"])
    except Exception:
        return


@require_GET
@require_node("videolearning", api=True)
def api_video_list(request: HttpRequest) -> JsonResponse:
    videos = VideoAsset.objects.select_related("category").prefetch_related("tags").all()[:200]
    return _ok({"videos": [_as_video_dict(v) for v in videos]})


@require_GET
@require_node("videolearning", api=True)
def api_video_detail(request: HttpRequest, video_id: int) -> JsonResponse:
    video = (
        VideoAsset.objects.select_related("category")
        .prefetch_related("tags")
        .filter(id=video_id)
        .first()
    )
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)
    return _ok({"video": _as_video_dict(video)})


@require_GET
@require_node("videolearning", api=True)
def api_video_stream(request: HttpRequest, video_id: int) -> HttpResponse:
    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)

    abs_path = _resolve_media_abs_path(video.file_path)
    if abs_path is None or not abs_path.exists() or not abs_path.is_file():
        return _err("VIDEO_FILE_NOT_FOUND", "Video file not found.", status=404)

    file_size = abs_path.stat().st_size
    range_header = request.headers.get("Range", "")
    parsed = _parse_http_range(range_header, file_size) if range_header else None

    content_type = "video/mp4"
    if parsed is None:
        resp = StreamingHttpResponse(_iter_file_range(abs_path, 0, file_size - 1), content_type=content_type)
        resp["Content-Length"] = str(file_size)
        resp["Accept-Ranges"] = "bytes"
        return resp

    start, end = parsed
    length = end - start + 1
    resp = StreamingHttpResponse(
        _iter_file_range(abs_path, start, end),
        status=206,
        content_type=content_type,
    )
    resp["Content-Length"] = str(length)
    resp["Accept-Ranges"] = "bytes"
    resp["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return resp


@require_POST
@require_node("videolearning", api=True)
def api_video_upload(request: HttpRequest) -> JsonResponse:
    file_obj = request.FILES.get("file")
    if not file_obj:
        return _err("FILE_REQUIRED", "file is required.", status=400)
    try:
        saved = save_uploaded_video(file_obj)
    except VideoUploadError as ex:
        return _err("UPLOAD_ERROR", str(ex), status=400)
    except Exception:
        return _err("UPLOAD_ERROR", "Upload failed.", status=500)
    return _ok({"upload": saved}, status=201)


@require_POST
@require_node("videolearning", api=True)
def api_video_create(request: HttpRequest) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    title = str(body.get("title") or "").strip()
    if not title:
        return _err("TITLE_REQUIRED", "title is required.", status=400)

    file_path = str(body.get("file_path") or "").strip()
    if not file_path:
        return _err("FILE_PATH_REQUIRED", "file_path is required.", status=400)

    category = _parse_or_create_category(body.get("category_name"))
    tags = _parse_or_create_tags(body.get("tag_names") or [])
    visibility = str(body.get("visibility") or VideoAsset.VISIBILITY_PRIVATE).strip().lower()
    status = str(body.get("status") or VideoAsset.STATUS_DRAFT).strip().lower()

    if visibility not in {x for x, _ in VideoAsset.VISIBILITY_CHOICES}:
        return _err("INVALID_VISIBILITY", "Invalid visibility.", status=400)
    if status not in {x for x, _ in VideoAsset.STATUS_CHOICES}:
        return _err("INVALID_STATUS", "Invalid status.", status=400)
    try:
        duration_seconds = max(0, int(body.get("duration_seconds") or 0))
    except Exception:
        return _err("INVALID_DURATION", "duration_seconds must be integer.", status=400)
    try:
        width = int(body.get("width")) if body.get("width") is not None else None
        height = int(body.get("height")) if body.get("height") is not None else None
        fps = float(body.get("fps")) if body.get("fps") is not None else None
        video_bitrate_kbps = (
            int(body.get("video_bitrate_kbps")) if body.get("video_bitrate_kbps") is not None else None
        )
    except Exception:
        return _err("INVALID_VIDEO_TECHNICAL", "width/height/fps/bitrate format invalid.", status=400)

    owner = _resolve_owner(request)

    thumb_input = str(body.get("thumbnail_path") or "").strip()
    thumb_local = _download_thumbnail_url_to_media(thumb_input, seed=title)

    video = VideoAsset.objects.create(
        title=title,
        description=str(body.get("description") or "").strip(),
        category=category,
        file_path=file_path,
        thumbnail_path=thumb_local or thumb_input,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        fps=fps,
        video_bitrate_kbps=video_bitrate_kbps,
        metadata_json=body.get("metadata_json") if isinstance(body.get("metadata_json"), dict) else {},
        owner=owner,
        visibility=visibility,
        status=status,
    )
    if tags:
        video.tags.set(tags)

    video = VideoAsset.objects.select_related("category").prefetch_related("tags").get(id=video.id)
    return _ok({"video": _as_video_dict(video)}, status=201)


@require_POST
@require_node("videolearning", api=True)
def api_video_import_youtube(request: HttpRequest) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    youtube_url = str(body.get("youtube_url") or "").strip()
    if not youtube_url:
        return _err("YOUTUBE_URL_REQUIRED", "youtube_url is required.", status=400)
    output_format = str(body.get("output_format") or "mp4").strip().lower()
    if output_format not in {"mp4", "mp3"}:
        return _err("INVALID_OUTPUT_FORMAT", "output_format must be mp4 or mp3.", status=400)

    try:
        imported = import_youtube_to_media(youtube_url, output_format=output_format)
    except YouTubeImportError as ex:
        return _err("YOUTUBE_IMPORT_ERROR", str(ex), status=400)
    except Exception:
        return _err("YOUTUBE_IMPORT_ERROR", "YouTube import failed.", status=500)

    if output_format == "mp3":
        # MP3 mode: export file only, do not create DB records.
        return _ok(
            {
                "import": imported,
                "db_saved": False,
                "message": "MP3 轉檔完成，已輸出至 MP3 輸出資料夾，不納入影片清單管理。",
            },
            status=201,
        )

    title = str(body.get("title") or imported.get("title") or "").strip()
    if not title:
        title = "YouTube 敶梁?"
    category = _parse_or_create_category(body.get("category_name"))
    tags = _parse_or_create_tags(body.get("tag_names") or [])
    visibility = str(body.get("visibility") or VideoAsset.VISIBILITY_PRIVATE).strip().lower()
    status = str(body.get("status") or VideoAsset.STATUS_READY).strip().lower()
    if visibility not in {x for x, _ in VideoAsset.VISIBILITY_CHOICES}:
        return _err("INVALID_VISIBILITY", "Invalid visibility.", status=400)
    if status not in {x for x, _ in VideoAsset.STATUS_CHOICES}:
        return _err("INVALID_STATUS", "Invalid status.", status=400)

    duration_seconds = int(imported.get("duration_seconds") or 0)
    owner = _resolve_owner(request)
    video = VideoAsset.objects.create(
        title=title,
        description=str(body.get("description") or "").strip(),
        category=category,
        file_path=str(imported.get("file_path") or "").strip(),
        thumbnail_path=str(imported.get("thumbnail_path") or "").strip(),
        duration_seconds=max(0, duration_seconds),
        width=imported.get("width"),
        height=imported.get("height"),
        fps=imported.get("fps"),
        video_bitrate_kbps=imported.get("video_bitrate_kbps"),
        metadata_json=imported.get("metadata_json") or {},
        owner=owner,
        visibility=visibility,
        status=status,
    )
    if tags:
        video.tags.set(tags)
    video = VideoAsset.objects.select_related("category").prefetch_related("tags").get(id=video.id)
    return _ok({"video": _as_video_dict(video), "import": imported}, status=201)


@require_POST
@require_node("videolearning", api=True)
def api_video_update(request: HttpRequest, video_id: int) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)

    if "title" in body:
        title = str(body.get("title") or "").strip()
        if not title:
            return _err("TITLE_REQUIRED", "title is required.", status=400)
        video.title = title
    if "description" in body:
        video.description = str(body.get("description") or "").strip()
    if "file_path" in body:
        file_path = str(body.get("file_path") or "").strip()
        if not file_path:
            return _err("FILE_PATH_REQUIRED", "file_path is required.", status=400)
        video.file_path = file_path
    if "thumbnail_path" in body:
        thumb_input = str(body.get("thumbnail_path") or "").strip()
        thumb_local = _download_thumbnail_url_to_media(thumb_input, seed=str(video.id))
        video.thumbnail_path = thumb_local or thumb_input
    if "duration_seconds" in body:
        try:
            video.duration_seconds = max(0, int(body.get("duration_seconds") or 0))
        except Exception:
            return _err("INVALID_DURATION", "duration_seconds must be integer.", status=400)
    if "width" in body:
        video.width = int(body.get("width")) if body.get("width") is not None else None
    if "height" in body:
        video.height = int(body.get("height")) if body.get("height") is not None else None
    if "fps" in body:
        video.fps = float(body.get("fps")) if body.get("fps") is not None else None
    if "video_bitrate_kbps" in body:
        video.video_bitrate_kbps = (
            int(body.get("video_bitrate_kbps")) if body.get("video_bitrate_kbps") is not None else None
        )
    if "metadata_json" in body:
        md = body.get("metadata_json")
        if md is not None and not isinstance(md, dict):
            return _err("INVALID_METADATA_JSON", "metadata_json must be object.", status=400)
        video.metadata_json = md or {}
    if "visibility" in body:
        visibility = str(body.get("visibility") or "").strip().lower()
        if visibility not in {x for x, _ in VideoAsset.VISIBILITY_CHOICES}:
            return _err("INVALID_VISIBILITY", "Invalid visibility.", status=400)
        video.visibility = visibility
    if "status" in body:
        status = str(body.get("status") or "").strip().lower()
        if status not in {x for x, _ in VideoAsset.STATUS_CHOICES}:
            return _err("INVALID_STATUS", "Invalid status.", status=400)
        video.status = status
    if "category_name" in body:
        video.category = _parse_or_create_category(body.get("category_name"))

    video.save()
    if "tag_names" in body:
        video.tags.set(_parse_or_create_tags(body.get("tag_names") or []))

    video = VideoAsset.objects.select_related("category").prefetch_related("tags").get(id=video.id)
    return _ok({"video": _as_video_dict(video)})


@require_POST
@require_node("videolearning", api=True)
def api_video_delete(request: HttpRequest, video_id: int) -> JsonResponse:
    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)

    request_owner = _resolve_owner(request)
    login_user = resolve_effective_user_id(request).lower()
    env_name = str(getattr(settings, "ENV_NAME", "EXT") or "EXT").strip().upper()
    user = getattr(request, "user", None)
    is_superuser = bool(user and getattr(user, "is_superuser", False))
    is_staff = bool(user and getattr(user, "is_staff", False))
    is_int_bypass_user = env_name == "INT" and login_user == "h121356578"
    is_admin = is_superuser or is_staff or is_int_bypass_user
    if not is_admin and request_owner != str(video.owner or "").strip():
        return _err("FORBIDDEN", "You can only delete your own videos.", status=403)

    abs_path = _resolve_media_abs_path(video.file_path)
    file_deleted = False
    file_message = ""
    if abs_path is None:
        file_message = "File path is outside MEDIA_ROOT; skipped file deletion."
    elif abs_path.exists():
        try:
            abs_path.unlink()
            file_deleted = True
        except Exception:
            return _err("FILE_DELETE_FAILED", "Failed to delete physical file.", status=500)
    else:
        file_message = "Physical file not found; deleted DB record only."

    deleted = {"id": video.id, "title": video.title, "file_deleted": file_deleted, "file_message": file_message}
    video.delete()
    return _ok({"deleted": deleted})


@require_POST
@require_node("videolearning", api=True)
def api_transcript_upload(request: HttpRequest, video_id: int) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)

    fmt = str(body.get("format") or "").strip().lower()
    content = str(body.get("content") or "")
    if not fmt:
        return _err("FORMAT_REQUIRED", "format is required.", status=400)
    if not content.strip():
        return _err("TRANSCRIPT_EMPTY", "Transcript is empty.", status=400)

    try:
        cues = _parse_transcript_by_format(fmt, content)
    except TranscriptParseError as ex:
        return _err("TRANSCRIPT_PARSE_ERROR", str(ex), status=400)

    source_type = str(body.get("source_type") or VideoTranscript.SOURCE_UPLOAD).strip().lower()
    if source_type not in {x for x, _ in VideoTranscript.SOURCE_CHOICES}:
        return _err("INVALID_SOURCE_TYPE", "Invalid source_type.", status=400)
    language = str(body.get("language") or "zh-Hant").strip() or "zh-Hant"

    transcript = VideoTranscript.objects.create(
        video_id=video.id,
        source_type=source_type,
        format=fmt,
        language=language,
        content=content.strip(),
        cues_json=cues,
    )
    return _ok({"transcript": _as_transcript_dict(transcript)}, status=201)


@require_POST
@require_node("videolearning", api=True)
def api_chapter_generate(request: HttpRequest, video_id: int) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)

    transcript_id = body.get("transcript_id")
    transcript_qs = VideoTranscript.objects.filter(video_id=video.id)
    if transcript_id is not None:
        try:
            transcript_id = int(transcript_id)
        except Exception:
            return _err("INVALID_TRANSCRIPT_ID", "transcript_id must be integer.", status=400)
        transcript_qs = transcript_qs.filter(id=transcript_id)
    transcript = transcript_qs.order_by("-updated_at", "-id").first()
    if not transcript:
        return _err("TRANSCRIPT_NOT_FOUND", "Transcript not found for this video.", status=404)

    try:
        interval_seconds = int(body.get("interval_seconds") or 180)
        max_chars_per_chapter = int(body.get("max_chars_per_chapter") or 300)
        chapters = generate_chapters_rule_based(
            transcript.cues_json or [],
            interval_seconds=interval_seconds,
            max_chars_per_chapter=max_chars_per_chapter,
        )
    except (ValueError, TranscriptParseError) as ex:
        return _err("CHAPTER_GENERATION_ERROR", str(ex), status=400)

    VideoChapter.objects.filter(video_id=video.id).delete()
    created: list[VideoChapter] = []
    for c in chapters:
        created.append(
            VideoChapter.objects.create(
                video_id=video.id,
                transcript_id=transcript.id,
                title=str(c.get("title") or "").strip() or f"Chapter {c['order_index']}",
                summary=str(c.get("summary") or "").strip(),
                start_seconds=int(c["start_seconds"]),
                end_seconds=int(c["end_seconds"]),
                order_index=int(c["order_index"]),
            )
        )

    return _ok({"chapters": [_as_chapter_dict(c) for c in created]})


@require_GET
@require_node("videolearning", api=True)
def api_chapter_list(request: HttpRequest, video_id: int) -> JsonResponse:
    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)
    chapters = VideoChapter.objects.filter(video_id=video.id).order_by("order_index", "id")
    return _ok({"chapters": [_as_chapter_dict(c) for c in chapters]})


@require_node("videolearning", api=True)
def api_health(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "ok": True,
            "data": {"service": "videolearning", "status": "healthy"},
            "error": None,
        },
        status=200,
    )


@require_GET
@require_node("videolearning", api=True)
def api_playlist_list(request: HttpRequest) -> JsonResponse:
    playlists = VideoPlaylist.objects.prefetch_related("items__video__tags").all()[:100]
    return _ok({"playlists": [_as_playlist_dict(p) for p in playlists]})


@require_GET
@require_node("videolearning", api=True)
def api_playlist_detail(request: HttpRequest, playlist_id: int) -> JsonResponse:
    playlist = VideoPlaylist.objects.prefetch_related("items__video__tags").filter(id=playlist_id).first()
    if not playlist:
        return _err("PLAYLIST_NOT_FOUND", "Playlist not found.", status=404)
    return _ok({"playlist": _as_playlist_dict(playlist)})


@require_POST
@require_node("videolearning", api=True)
def api_playlist_create(request: HttpRequest) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    title = str(body.get("title") or "").strip()
    if not title:
        return _err("TITLE_REQUIRED", "title is required.", status=400)

    visibility = str(body.get("visibility") or VideoPlaylist.VISIBILITY_PRIVATE).strip().lower()
    if visibility not in {x for x, _ in VideoPlaylist.VISIBILITY_CHOICES}:
        return _err("INVALID_VISIBILITY", "Invalid visibility.", status=400)

    owner = _resolve_owner(request)

    playlist = VideoPlaylist.objects.create(
        title=title,
        description=str(body.get("description") or "").strip(),
        owner=owner,
        visibility=visibility,
    )
    playlist = VideoPlaylist.objects.get(id=playlist.id)
    return _ok({"playlist": _as_playlist_dict(playlist)}, status=201)


@require_POST
@require_node("videolearning", api=True)
def api_playlist_add_video(request: HttpRequest, playlist_id: int) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    playlist = VideoPlaylist.objects.filter(id=playlist_id).first()
    if not playlist:
        return _err("PLAYLIST_NOT_FOUND", "Playlist not found.", status=404)

    try:
        video_id = int(body.get("video_id"))
    except Exception:
        return _err("VIDEO_ID_REQUIRED", "video_id is required.", status=400)

    video = VideoAsset.objects.filter(id=video_id).first()
    if not video:
        return _err("VIDEO_NOT_FOUND", "Video not found.", status=404)

    if VideoPlaylistItem.objects.filter(playlist_id=playlist.id, video_id=video.id).exists():
        return _err("VIDEO_ALREADY_IN_PLAYLIST", "Video already in playlist.", status=400)

    max_idx = (
        VideoPlaylistItem.objects.filter(playlist_id=playlist.id)
        .order_by("-order_index")
        .values_list("order_index", flat=True)
        .first()
    )
    next_idx = 1 if max_idx is None else int(max_idx) + 1
    VideoPlaylistItem.objects.create(
        playlist_id=playlist.id,
        video_id=video.id,
        order_index=next_idx,
    )
    playlist = VideoPlaylist.objects.get(id=playlist.id)
    return _ok({"playlist": _as_playlist_dict(playlist)})


@require_POST
@require_node("videolearning", api=True)
def api_playlist_reorder(request: HttpRequest, playlist_id: int) -> JsonResponse:
    body = _read_json(request)
    if body is None:
        return _err("INVALID_JSON", "Request body must be valid JSON.", status=400)

    playlist = VideoPlaylist.objects.filter(id=playlist_id).first()
    if not playlist:
        return _err("PLAYLIST_NOT_FOUND", "Playlist not found.", status=404)

    item_ids = body.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        return _err("INVALID_ITEM_IDS", "item_ids must be a non-empty list.", status=400)

    items = list(VideoPlaylistItem.objects.filter(playlist_id=playlist.id).order_by("order_index", "id"))
    if len(items) != len(item_ids):
        return _err("ITEM_COUNT_MISMATCH", "item_ids length mismatch.", status=400)

    existing_ids = {i.id for i in items}
    try:
        new_ids = [int(x) for x in item_ids]
    except Exception:
        return _err("INVALID_ITEM_IDS", "item_ids must be integer list.", status=400)

    if set(new_ids) != existing_ids:
        return _err("INVALID_ITEM_IDS", "item_ids must match existing playlist items.", status=400)

    # Two-phase reorder to avoid unique collisions on (playlist_id, order_index).
    with transaction.atomic():
        for idx, item_id in enumerate(new_ids, start=1):
            VideoPlaylistItem.objects.filter(id=item_id, playlist_id=playlist.id).update(
                order_index=1000000 + idx
            )
        for idx, item_id in enumerate(new_ids, start=1):
            VideoPlaylistItem.objects.filter(id=item_id, playlist_id=playlist.id).update(
                order_index=idx
            )

    playlist = VideoPlaylist.objects.get(id=playlist.id)
    return _ok({"playlist": _as_playlist_dict(playlist)})
