from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

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


def _make_media_url(abs_path: Path) -> str:
    rel_from_media = abs_path.relative_to(Path(settings.MEDIA_ROOT))
    rel_url = "/".join(rel_from_media.parts)
    media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    if not media_url.endswith("/"):
        media_url += "/"
    return f"{media_url}{rel_url}"


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


def import_youtube_to_media(youtube_url: str) -> dict:
    url = (youtube_url or "").strip()
    if not url:
        raise YouTubeImportError("youtube_url is required.")
    if not _is_youtube_url(url):
        raise YouTubeImportError("僅支援 YouTube 連結。")

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

        # If ffmpeg is unavailable, use a fallback format that can be downloaded as a single file.
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
            dl_cmd.extend(["--merge-output-format", "mp4"])
            dl_cmd.extend(["--ffmpeg-location", ffmpeg_bin])
        dl_proc = subprocess.run(dl_cmd, capture_output=True, text=True, check=False)
        if dl_proc.returncode != 0:
            raise YouTubeImportError(dl_proc.stderr.strip() or "下載或轉檔失敗。")

        mp4_files = sorted(temp_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if mp4_files:
            source_file = mp4_files[0]
        else:
            all_files = [p for p in temp_dir.glob("*") if p.is_file()]
            if not all_files:
                raise YouTubeImportError("找不到下載結果檔案。")
            source_file = sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]

        source_ext = (source_file.suffix or "").lower()
        if not source_ext:
            source_ext = ".mp4" if ffmpeg_bin else ".bin"

        final_dir = work_root / f"{now.year:04d}" / f"{now.month:02d}"
        final_dir.mkdir(parents=True, exist_ok=True)
        title_hint = _safe_name(str(meta.get("title") or "youtube_video"))
        # Keep real container extension when ffmpeg is unavailable to avoid fake .mp4 files.
        final_ext = ".mp4" if ffmpeg_bin else source_ext
        final_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{title_hint}_{uuid.uuid4().hex[:8]}{final_ext}"
        final_path = final_dir / final_name
        shutil.move(str(source_file), str(final_path))

        return {
            "file_path": _make_media_url(final_path),
            "title": str(meta.get("title") or ""),
            "duration_seconds": int(meta.get("duration") or 0),
            "thumbnail_url": str(meta.get("thumbnail") or ""),
            "source_url": url,
            "ffmpeg_used": bool(ffmpeg_bin),
            "container_ext": final_ext.lstrip("."),
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
            },
        }
    except FileNotFoundError as ex:
        raise YouTubeImportError(f"執行檔不存在：{ex}") from ex
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
