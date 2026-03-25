from __future__ import annotations


def normalize_hex(value: str) -> str:
    v = (value or "").strip().lstrip("#")
    if len(v) == 6:
        return f"#{v.upper()}"
    return ""
