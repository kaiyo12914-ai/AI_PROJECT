from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def _setup_django(project_root: Path) -> None:
    root = str(project_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
    import django

    django.setup()


def _check_google_provider() -> Dict[str, Any]:
    try:
        from webapps.img_gen.img_factory import get_image_model  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": f"provider factory unavailable: {exc}"}

    try:
        model = get_image_model()
    except Exception as exc:
        return {"ok": False, "error": f"provider init failed: {exc}"}

    if model is None:
        return {"ok": False, "error": "provider returned None"}

    has_generate = hasattr(model, "generate_image")
    return {
        "ok": True,
        "provider_type": type(model).__name__,
        "supports_generate_image": bool(has_generate),
        "callable": bool(callable(model)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe text2pptx image generation pipeline.")
    parser.add_argument("--prompt", default="A clean corporate teamwork illustration", help="Image prompt")
    parser.add_argument("--mode", default="mock", choices=["mock", "google", "off"], help="Image generation mode")
    parser.add_argument("--aspect-ratio", default="16:9", help="Aspect ratio (1:1, 4:3, 3:2, 16:9, 9:16)")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    parser.add_argument("--timeout-sec", type=int, default=30, help="Provider timeout in seconds")
    parser.add_argument("--output-dir", default="", help="Optional output directory")
    parser.add_argument(
        "--dry-run-provider",
        action="store_true",
        help="Only initialize/check google provider without generating an image",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    _setup_django(project_root)

    if args.dry_run_provider:
        if args.mode != "google":
            print(json.dumps({"ok": False, "error": "--dry-run-provider requires --mode google"}, ensure_ascii=False))
            return 2
        print(json.dumps(_check_google_provider(), ensure_ascii=False))
        return 0

    from webapps.text2pptx.image_service import ImageGenError, generate_image

    try:
        result = generate_image(
            prompt=args.prompt,
            aspect_ratio=args.aspect_ratio,
            mode=args.mode,
            seed=args.seed,
            timeout_sec=args.timeout_sec,
            output_dir=args.output_dir or None,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ImageGenError as exc:
        payload = {"ok": False, "code": exc.code, "retryable": exc.retryable, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False))
        return 3
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
