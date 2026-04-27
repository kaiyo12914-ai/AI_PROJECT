import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.projectnotes.views import _build_answer_from_evidence


def test_build_answer_from_evidence_happy_no_chunk_excerpt():
    evidence = [
        {"source_title": "採購辦法.pdf", "excerpt": "這是很長的 CHUNK 內容，不應直接顯示在對話框中。"},
        {"source_title": "作業規範.txt", "excerpt": "第二段參考內容。"},
    ]

    out = _build_answer_from_evidence("什麼是巨額採購", evidence)

    assert "已參考：採購辦法.pdf" in out
    assert "已參考：作業規範.txt" in out
    assert "CHUNK 內容" not in out
    assert "詳細 CHUNK 參考請參考下方" in out


def test_build_answer_from_evidence_boundary_empty_evidence():
    out = _build_answer_from_evidence("測試問題", [])
    assert "找不到可用證據" in out


def test_build_answer_from_evidence_error_like_missing_source_title():
    evidence = [{"excerpt": "只有片段沒有來源"}]
    out = _build_answer_from_evidence("測試問題", evidence)
    assert "已參考：來源1" in out
