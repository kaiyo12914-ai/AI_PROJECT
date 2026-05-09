from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile


class VideoUploadError(ValueError):
    pass


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".mov", ".m4v"}
DEFAULT_MAX_UPLOAD_MB = 512


def _safe_suffix(name: str) -> str:
    suffix = (Path(name).suffix or "").lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise VideoUploadError("不支援的影片格式。")
    return suffix


def _upload_root() -> Path:
    env_name = str(getattr(settings, "ENV_NAME", "EXT") or "EXT").upper()
    env_key = "int" if env_name == "INT" else "ext"
    return Path(settings.MEDIA_ROOT) / "videolearning" / env_key / "videos"


def _max_upload_bytes() -> int:
    mb = int(getattr(settings, "VIDEOLEARNING_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB) or DEFAULT_MAX_UPLOAD_MB)
    if mb <= 0:
        mb = DEFAULT_MAX_UPLOAD_MB
    return mb * 1024 * 1024


def save_uploaded_video(file_obj: UploadedFile) -> dict:
    if not file_obj:
        raise VideoUploadError("缺少上傳檔案。")

    suffix = _safe_suffix(file_obj.name or "")
    size = int(getattr(file_obj, "size", 0) or 0)
    max_bytes = _max_upload_bytes()
    if size <= 0:
        raise VideoUploadError("上傳檔案為空。")
    if size > max_bytes:
        raise VideoUploadError(f"檔案過大，限制 {max_bytes // (1024 * 1024)}MB。")

    now = datetime.now()
    folder = _upload_root() / f"{now.year:04d}" / f"{now.month:02d}"
    folder.mkdir(parents=True, exist_ok=True)

    file_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:10]}{suffix}"
    abs_path = folder / file_name

    with abs_path.open("wb") as out:
        for chunk in file_obj.chunks():
            out.write(chunk)

    rel_from_media = abs_path.relative_to(Path(settings.MEDIA_ROOT))
    rel_url = "/".join(rel_from_media.parts)
    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    if not media_url.endswith("/"):
        media_url += "/"
    file_path = f"{media_url}{rel_url}"

    return {
        "file_path": file_path,
        "size_bytes": size,
        "original_name": file_obj.name,
    }