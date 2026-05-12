from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings


class YouTubeImportError(ValueError):
    pass


def _is_youtube_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return "youtube.com/" in u or "youtu.be/" in u


def _upload_root() -> Path:
    env_name = str(getattr(settings, "ENV_NAME", "EXT") or "EXT").upper()
    env_key = "int" if env_name == "INT" else "ext"
    return Path(settings.MEDIA_ROOT) / "videolearning" / env_key / "videos"


def _mp3_output_root() -> Path:
    # Requirement: MP3 outputs are fixed to this folder and not managed by DB.
    return Path(r"H:\Mp3")


def _make_media_url(abs_path: Path) -> str:
    rel_from_media = abs_path.relative_to(Path(settings.MEDIA_ROOT))
    rel_url = "/".join(rel_from_media.parts)
    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    if not media_url.endswith("/"):
        media_url += "/"
    return f"{media_url}{rel_url}"


def _thumbnail_root() -> Path:
    env_name = str(getattr(settings, "ENV_NAME", "EXT") or "EXT").upper()
    env_key = "int" if env_name == "INT" else "ext"
    return Path(settings.MEDIA_ROOT) / "videolearning" / env_key / "thumbnails"


def _safe_name(name: str) -> str:
    base = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", (name or "").strip(), flags=re.UNICODE).strip("_")
    return base[:80] or "youtube_video"


def _as_int(v) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except Exception:
        return None


def _as_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _download_thumbnail_to_media(thumbnail_url: str, youtube_id: str, now: datetime) -> str:
    raw = (thumbnail_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""

    ext = Path(parsed.path or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"

    thumb_dir = _thumbnail_root() / f"{now.year:04d}" / f"{now.month:02d}"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", (youtube_id or "").strip()) or uuid.uuid4().hex[:8]
    file_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{safe_id}_{uuid.uuid4().hex[:6]}{ext}"
    abs_path = thumb_dir / file_name

    req = Request(raw, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp, open(abs_path, "wb") as f:
        f.write(resp.read())

    return _make_media_url(abs_path)


def _resolve_yt_dlp_cmd() -> list[str]:
    yt_dlp_bin = str(getattr(settings, "YTDLP_BIN", "yt-dlp") or "yt-dlp").strip()
    if yt_dlp_bin:
        found = shutil.which(yt_dlp_bin)
        if found:
            return [found]
        if Path(yt_dlp_bin).exists():
            return [yt_dlp_bin]

    py = Path(sys.executable)
    if py.exists():
        return [str(py), "-m", "yt_dlp"]
    raise YouTubeImportError("找不到 yt-dlp，請先安裝並設定 YTDLP_BIN。")


def _resolve_ffmpeg_bin() -> str | None:
    ffmpeg_bin = str(getattr(settings, "FFMPEG_BIN", "ffmpeg") or "ffmpeg").strip()
    if ffmpeg_bin:
        found = shutil.which(ffmpeg_bin)
        if found:
            return found
        if Path(ffmpeg_bin).exists():
            return ffmpeg_bin
    return None


def import_youtube_to_media(youtube_url: str, output_format: str = "mp4") -> dict:
    url = (youtube_url or "").strip()
    if not url:
        raise YouTubeImportError("youtube_url is required.")
    if not _is_youtube_url(url):
        raise YouTubeImportError("僅支援 YouTube 連結。")

    fmt = (output_format or "mp4").strip().lower()
    if fmt not in {"mp4", "mp3"}:
        raise YouTubeImportError("output_format must be mp4 or mp3.")

    yt_dlp_cmd = _resolve_yt_dlp_cmd()
    ffmpeg_bin = _resolve_ffmpeg_bin()

    work_root = _upload_root()
    now = datetime.now()
    temp_dir = work_root / "_tmp" / uuid.uuid4().hex[:12]
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        meta_cmd = yt_dlp_cmd + ["--dump-single-json", "--no-playlist", url]
        meta_proc = subprocess.run(meta_cmd, capture_output=True, text=True, check=False)
        if meta_proc.returncode != 0:
            raise YouTubeImportError(meta_proc.stderr.strip() or "讀取 YouTube 影片資訊失敗。")
        try:
            meta = json.loads(meta_proc.stdout or "{}")
        except Exception:
            meta = {}

        if fmt == "mp3":
            if not ffmpeg_bin:
                raise YouTubeImportError("MP3 轉檔需要 ffmpeg，請先安裝並設定 FFMPEG_BIN。")
            dl_cmd = yt_dlp_cmd + [
                "--no-playlist",
                "-f",
                "bestaudio/best",
                "--extract-audio",
                "--audio-format",
                "mp3",
                "--audio-quality",
                "0",
                "--ffmpeg-location",
                ffmpeg_bin,
                "-o",
                str(temp_dir / "%(title).80s_%(id)s.%(ext)s"),
                url,
            ]
        else:
            format_expr = "bv*+ba/b" if ffmpeg_bin else "b[ext=mp4]/b"
            dl_cmd = yt_dlp_cmd + [
                "--no-playlist",
                "-f",
                format_expr,
                "-o",
                str(temp_dir / "%(title).80s_%(id)s.%(ext)s"),
                url,
            ]
            if ffmpeg_bin:
                dl_cmd.extend(["--merge-output-format", "mp4", "--ffmpeg-location", ffmpeg_bin])

        dl_proc = subprocess.run(dl_cmd, capture_output=True, text=True, check=False)
        if dl_proc.returncode != 0:
            raise YouTubeImportError(dl_proc.stderr.strip() or "下載或轉檔失敗。")

        if fmt == "mp3":
            target_files = sorted(temp_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        else:
            target_files = sorted(temp_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)

        if target_files:
            source_file = target_files[0]
        else:
            all_files = [p for p in temp_dir.glob("*") if p.is_file()]
            if not all_files:
                raise YouTubeImportError("找不到下載結果檔案。")
            source_file = sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]

        source_ext = (source_file.suffix or "").lower() or ".bin"

        if fmt == "mp3":
            final_dir = _mp3_output_root()
            final_ext = ".mp3"
        else:
            final_dir = work_root / f"{now.year:04d}" / f"{now.month:02d}"
            final_ext = ".mp4" if ffmpeg_bin else source_ext

        final_dir.mkdir(parents=True, exist_ok=True)
        title_hint = _safe_name(str(meta.get("title") or "youtube_video"))
        final_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{title_hint}_{uuid.uuid4().hex[:8]}{final_ext}"
        final_path = final_dir / final_name
        shutil.move(str(source_file), str(final_path))

        if fmt == "mp3":
            file_path = str(final_path)
        else:
            file_path = _make_media_url(final_path)

        thumb_url = str(meta.get("thumbnail") or "")
        local_thumb_path = ""
        try:
            local_thumb_path = _download_thumbnail_to_media(thumb_url, str(meta.get("id") or ""), now)
        except Exception:
            local_thumb_path = ""

        return {
            "file_path": file_path,
            "title": str(meta.get("title") or ""),
            "duration_seconds": int(meta.get("duration") or 0),
            "thumbnail_url": thumb_url,
            "thumbnail_path": local_thumb_path,
            "source_url": url,
            "ffmpeg_used": bool(ffmpeg_bin),
            "container_ext": final_ext.lstrip("."),
            "output_format": fmt,
            "width": _as_int(meta.get("width")),
            "height": _as_int(meta.get("height")),
            "fps": _as_float(meta.get("fps")),
            "video_bitrate_kbps": _as_int(meta.get("tbr") or meta.get("vbr")),
            "metadata_json": {
                "youtube_id": meta.get("id"),
                "uploader": meta.get("uploader"),
                "webpage_url": meta.get("webpage_url"),
                "format_id": meta.get("format_id"),
                "ext": meta.get("ext"),
                "container_ext": final_ext.lstrip("."),
                "output_format": fmt,
            },
        }
    except FileNotFoundError as ex:
        raise YouTubeImportError(f"執行檔不存在：{ex}") from ex
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
