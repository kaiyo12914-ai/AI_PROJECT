import os

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes.views import _decode_text_bytes_best_effort


def test_decode_text_bytes_best_effort_happy_utf8():
    raw = "專案測試資料 UTF-8".encode("utf-8")
    text, enc = _decode_text_bytes_best_effort(raw)
    assert "專案測試資料" in text
    assert enc in {"utf-8", "utf-8-sig"}


def test_decode_text_bytes_best_effort_happy_cp950():
    raw = "中文測試資料".encode("cp950")
    text, enc = _decode_text_bytes_best_effort(raw)
    assert text == "中文測試資料"
    assert enc in {"cp950", "big5"}


def test_decode_text_bytes_best_effort_boundary_empty_bytes():
    text, enc = _decode_text_bytes_best_effort(b"")
    assert text == ""
    assert enc == "utf-8"


def test_decode_text_bytes_best_effort_error_unreadable_binary():
    with pytest.raises(ValueError, match="unsupported or unreadable text encoding"):
        _decode_text_bytes_best_effort(b"\xd8\x1d\x17")
