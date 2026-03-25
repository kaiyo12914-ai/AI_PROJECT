from __future__ import annotations

from typing import Any

from webapps.text2pptx.pptx2schema.models.raw import ThemeColorScheme, ThemeFontScheme, ThemeSpec


def _safe_attr(obj: Any, name: str) -> str | None:
    try:
        value = getattr(obj, name, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    except Exception:
        return None


def extract_theme_from_presentation(_presentation: Any) -> ThemeSpec:
    # python-pptx public API has limited theme exposure.
    # Keep schema stable now; xml fallback can enrich later.
    return ThemeSpec(
        font_scheme=ThemeFontScheme(),
        color_scheme=ThemeColorScheme(),
    )
