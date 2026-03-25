from __future__ import annotations


def normalize_font_name(name: str) -> str:
    return str(name or "").strip()
