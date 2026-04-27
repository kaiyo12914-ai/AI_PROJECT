import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes.views import _build_citation_tail


def test_build_citation_tail_happy_path():
    citations = [
        {"ref": "C1", "confidence": 0.55, "chunk_index": 3, "source_title": "投標須知範本 無人機條款.pdf"},
        {"ref": "C3", "confidence": 0.41, "chunk_index": 8, "source_title": "採購法規彙編.pdf"},
    ]
    out = _build_citation_tail(citations)
    assert "來源依據：" in out
    assert "C1(0.55)#3 『投標須知範本 無人機條款.pdf』#3" in out
    assert "C3(0.41)#8 『採購法規彙編.pdf』#8" in out


def test_build_citation_tail_boundary_empty():
    assert _build_citation_tail([]) == ""


def test_build_citation_tail_error_like_missing_fields():
    citations = [{"chunk_index": "x", "source_title": ""}]
    out = _build_citation_tail(citations)
    assert "來源依據：" in out
    assert "C(--)" in out
    assert "『未知來源』#0" in out
