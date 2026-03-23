#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from google import genai
except Exception:
    print(
        json.dumps(
            {"ok": False, "error": "Missing dependency: pip install google-genai"},
            ensure_ascii=False,
        )
    )
    raise SystemExit(1)


def _fail(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    raise SystemExit(code)


def _extract_image_bytes(response: object) -> bytes | None:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if not inline_data:
                continue
            data = getattr(inline_data, "data", None)
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
    return None


def main() -> int:
    raw = (sys.stdin.read() or "").strip()
    if not raw:
        _fail("No input received from stdin")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"Invalid JSON input: {exc}")

    prompt = str(payload.get("prompt") or "").strip()
    output_path = str(payload.get("output_path") or "").strip()
    size = str(payload.get("size") or "1024x1024").strip()
    timeout_sec = int(payload.get("timeout_sec") or 30)

    if not prompt:
        _fail("Missing required field: prompt")
    if not output_path:
        _fail("Missing required field: output_path")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        _fail("Missing GEMINI_API_KEY or GOOGLE_API_KEY")

    model_name = os.getenv("GOOGLE_IMAGE_MODEL", "gemini-2.5-flash-image-preview")
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        client = genai.Client(api_key=api_key)
        config = {"response_modalities": ["TEXT", "IMAGE"], "image_config": {"size": size}}
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
        except Exception:
            # Some SDK/model combinations may not accept image_config fields.
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"response_modalities": ["TEXT", "IMAGE"]},
            )
        image_bytes = _extract_image_bytes(response)
        if not image_bytes:
            _fail("No image data returned by model")
        out_file.write_bytes(image_bytes)
        print(json.dumps({"ok": True, "image_path": str(out_file)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        _fail(f"Google image generation failed: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
