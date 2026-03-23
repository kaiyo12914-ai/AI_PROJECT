from __future__ import annotations

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict

from django.conf import settings

logger = logging.getLogger(__name__)

# Tiny 1x1 PNG (transparent), used by mock mode.
_MOCK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAusB9Y0A3L8AAAAASUVORK5CYII="
)

_VALID_MODES = {"mock", "google", "off"}
_VALID_ASPECT_RATIOS = {"1:1", "4:3", "3:2", "16:9", "9:16"}
_SIZE_BY_RATIO = {
    "1:1": "1024x1024",
    "4:3": "1536x1152",
    "3:2": "1536x1024",
    "16:9": "1536x864",
    "9:16": "864x1536",
}


class ImageGenError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _default_output_dir() -> Path:
    configured = getattr(settings, "TEXT2PPTX_IMAGE_DIR", "")
    if configured:
        return Path(str(configured))
    root = getattr(settings, "MEDIA_ROOT", "")
    return Path(root) / "generated_images" / "text2pptx"


def _normalize_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower() or "mock"
    if value not in _VALID_MODES:
        raise ImageGenError("IMG_E_CONFIG", f"Unsupported image mode: {value}", retryable=False)
    return value


def _normalize_aspect_ratio(aspect_ratio: str | None) -> str:
    value = str(aspect_ratio or "").strip() or "16:9"
    if value not in _VALID_ASPECT_RATIOS:
        return "16:9"
    return value


def _build_cache_key(prompt: str, aspect_ratio: str, seed: int | None) -> str:
    raw = f"{prompt}|{aspect_ratio}|{seed if seed is not None else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _size_for_aspect_ratio(aspect_ratio: str) -> str:
    return _SIZE_BY_RATIO.get(aspect_ratio, _SIZE_BY_RATIO["16:9"])


def _decode_base64_payload(value: str) -> bytes | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "," in raw and raw.lower().startswith("data:image/"):
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        return None


def _extract_generated_bytes(result: Any) -> bytes | None:
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if not isinstance(result, dict):
        return None
    for key in ("image_bytes", "bytes"):
        value = result.get(key)
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    for key in ("image_base64", "base64", "b64_json", "b64"):
        value = result.get(key)
        if value:
            decoded = _decode_base64_payload(str(value))
            if decoded:
                return decoded
    return None


def _extract_local_path(result: Any) -> str | None:
    if isinstance(result, str):
        return result.strip() or None
    if isinstance(result, dict):
        for key in ("local_path", "image_path", "path", "file"):
            value = result.get(key)
            if value:
                return str(value).strip() or None
    return None


def _call_google_provider(
    *,
    prompt: str,
    aspect_ratio: str,
    seed: int | None,
    timeout_sec: int,
    output_path: str,
    size: str,
) -> Any:
    try:
        from webapps.img_gen.img_factory import get_image_model  # type: ignore
    except Exception as exc:
        raise ImageGenError(
            "IMG_E_PROVIDER",
            "Image provider factory is unavailable.",
            retryable=False,
        ) from exc

    try:
        model = get_image_model()
    except Exception as exc:
        raise ImageGenError("IMG_E_PROVIDER", str(exc), retryable=True) from exc

    if model is None:
        raise ImageGenError("IMG_E_PROVIDER", "Image provider was not created.", retryable=True)

    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "seed": seed,
        "timeout_sec": timeout_sec,
        "output_path": output_path,
        "size": size,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    if hasattr(model, "generate_image"):
        return model.generate_image(**payload)
    if callable(model):
        return model(**payload)
    raise ImageGenError("IMG_E_PROVIDER", "Unsupported image provider interface.", retryable=False)


def generate_image(
    prompt: str,
    aspect_ratio: str = "16:9",
    mode: str = "mock",
    seed: int | None = None,
    timeout_sec: int = 30,
    output_dir: str | os.PathLike[str] | None = None,
) -> Dict[str, Any]:
    prompt_text = str(prompt or "").strip()
    if not prompt_text:
        raise ImageGenError("IMG_E_INPUT", "Image prompt is empty.", retryable=False)

    mode_value = _normalize_mode(mode)
    ratio_value = _normalize_aspect_ratio(aspect_ratio)
    out_dir = Path(output_dir) if output_dir else _default_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_key = _build_cache_key(prompt_text, ratio_value, seed)
    out_path = out_dir / f"{cache_key}.png"
    if out_path.exists():
        return {
            "ok": True,
            "local_path": str(out_path),
            "provider": mode_value,
            "meta": {"cached": True, "aspect_ratio": ratio_value, "seed": seed},
        }

    if mode_value == "off":
        raise ImageGenError("IMG_E_DISABLED", "Image mode is disabled.", retryable=False)

    if mode_value == "mock":
        out_path.write_bytes(base64.b64decode(_MOCK_PNG_B64))
        return {
            "ok": True,
            "local_path": str(out_path),
            "provider": "mock",
            "meta": {"cached": False, "aspect_ratio": ratio_value, "seed": seed},
        }

    try:
        result = _call_google_provider(
            prompt=prompt_text,
            aspect_ratio=ratio_value,
            seed=seed,
            timeout_sec=int(timeout_sec),
            output_path=str(out_path),
            size=_size_for_aspect_ratio(ratio_value),
        )
    except ImageGenError:
        raise
    except TimeoutError as exc:
        raise ImageGenError("IMG_E_TIMEOUT", str(exc), retryable=True) from exc
    except Exception as exc:
        raise ImageGenError("IMG_E_PROVIDER", str(exc), retryable=True) from exc

    if isinstance(result, dict) and result.get("ok") is False:
        raise ImageGenError(
            "IMG_E_PROVIDER",
            str(result.get("error") or "Provider returned ok=false."),
            retryable=True,
        )

    local_path = _extract_local_path(result)
    if local_path and os.path.isfile(local_path):
        return {
            "ok": True,
            "local_path": local_path,
            "provider": "google",
            "meta": {"cached": False, "aspect_ratio": ratio_value, "seed": seed},
        }

    if isinstance(result, dict) and result.get("ok") is True and out_path.is_file():
        return {
            "ok": True,
            "local_path": str(out_path),
            "provider": "google",
            "meta": {"cached": False, "aspect_ratio": ratio_value, "seed": seed},
        }

    data = _extract_generated_bytes(result)
    if data:
        out_path.write_bytes(data)
        return {
            "ok": True,
            "local_path": str(out_path),
            "provider": "google",
            "meta": {"cached": False, "aspect_ratio": ratio_value, "seed": seed},
        }

    logger.warning("Unexpected image provider result type: %s", type(result).__name__)
    raise ImageGenError("IMG_E_PROVIDER", "Unsupported image provider result.", retryable=False)
