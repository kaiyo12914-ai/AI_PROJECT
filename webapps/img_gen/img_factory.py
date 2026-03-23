from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, Dict, List

from django.conf import settings


class CommandImageModel:
    """Command-based image provider adapter.

    Provider contract:
    - stdin: JSON payload
    - stdout: JSON payload
    """

    def __init__(self, command: str, *, name: str = "primary"):
        raw = str(command or "").strip()
        if not raw:
            raise ValueError("image provider command is empty")
        argv = shlex.split(raw, posix=False)
        if not argv:
            raise ValueError("image provider command could not be parsed")
        self._raw = raw
        self._argv = argv
        self.name = name

    def generate_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        timeout_sec: int = 30,
        output_path: str | None = None,
        size: str | None = None,
    ) -> Dict[str, Any]:
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "timeout_sec": timeout_sec,
            "output_path": output_path,
            "size": size,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        proc = subprocess.run(
            self._argv,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_sec)),
            check=False,
            shell=False,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode != 0:
            err = stderr or stdout or "provider returned non-zero exit code"
            raise RuntimeError(f"[{self.name}] image provider command failed ({proc.returncode}): {err}")
        if not stdout:
            raise RuntimeError(f"[{self.name}] image provider command returned empty stdout")

        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"[{self.name}] provider stdout is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"[{self.name}] provider result must be a JSON object")
        return parsed


class FallbackImageModel:
    """Try providers in order until one succeeds with `ok=true`."""

    def __init__(self, providers: List[CommandImageModel]):
        if not providers:
            raise ValueError("providers are required")
        self._providers = providers

    def generate_image(self, **kwargs: Any) -> Dict[str, Any]:
        errors: List[str] = []
        for provider in self._providers:
            try:
                result = provider.generate_image(**kwargs)
            except Exception as exc:
                errors.append(str(exc))
                continue
            ok = result.get("ok")
            if ok is False:
                err = str(result.get("error") or "provider returned ok=false")
                errors.append(f"[{provider.name}] {err}")
                continue
            if ok is True or ok is None:
                return result
            errors.append(f"[{provider.name}] invalid ok flag: {ok!r}")
        raise RuntimeError("All image providers failed: " + " | ".join(errors))


def get_image_model() -> FallbackImageModel | CommandImageModel:
    primary_cmd = str(getattr(settings, "TEXT2PPTX_IMAGE_PROVIDER_CMD", "") or "").strip()
    fallback_cmd = str(getattr(settings, "TEXT2PPTX_IMAGE_PROVIDER_FALLBACK_CMD", "") or "").strip()

    providers: List[CommandImageModel] = []
    if primary_cmd:
        providers.append(CommandImageModel(primary_cmd, name="primary"))
    if fallback_cmd:
        providers.append(CommandImageModel(fallback_cmd, name="fallback"))

    if not providers:
        raise RuntimeError(
            "No image provider configured. Set TEXT2PPTX_IMAGE_PROVIDER_CMD "
            "(and optional TEXT2PPTX_IMAGE_PROVIDER_FALLBACK_CMD)."
        )
    if len(providers) == 1:
        return providers[0]
    return FallbackImageModel(providers)

