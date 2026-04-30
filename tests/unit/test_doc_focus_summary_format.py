import os
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.doc.views_parse import _build_fixed_incoming_point1, _format_focus_summary_v3


def test_format_focus_summary_v3_uses_positive_incoming_fields_only():
    out = _format_focus_summary_v3(
        sender_org="\u570b\u9632\u90e8",
        recipient_org="\u8ecd\u5099\u5c40",
        doc_date="\u4e2d\u83ef\u6c11\u570b115\u5e742\u67083\u65e5",
        doc_no="\u570b\u901a\u96fb\u6230\u5b57\u7b2c1153601375\u865f",
        doc_subject="\u4ee4\u767c\u570b\u9632\u90e8\u901a\u96fb\u8cc7\u901a\u583111500001\u865f\u4e59\u5247\uff0c\u8acb\u7167\u8fa6\u3002",
        incoming_desc=[
            "\u672c\u4ef6\u5c6c\u300c\u653f\u4ee4\u5ba3\u5c0e\u300d\uff0c\u61c9\u5373\u4e0b\u8f09\u4e26\u9031\u77e5\u5099\u67e5\u3002",
            "\u672c\u4ef6\u5c6c\u4e00\u822c\u516c\u52d9\u8cc7\u8a0a\u3002",
        ],
        incoming_point1="\u4f9d\u570b\u9632\u90e8\u4e2d\u83ef\u6c11\u570b115\u5e742\u67083\u65e5\u570b\u901a\u96fb\u6230\u5b57\u7b2c1153601375\u865f\u4ee4\u8fa6\u7406\u3002",
        attachment_points=["\u9644\u4ef6\u91cd\u9edeA", "\u9644\u4ef6\u91cd\u9edeB"],
        max_incoming_desc=8,
        max_attach=10,
    )

    assert "\u4f86\u6587\u6a5f\u95dc: \u570b\u9632\u90e8" in out
    assert "\u53d7\u6587\u6a5f\u95dc: \u8ecd\u5099\u5c40" in out
    assert "\u767c\u6587\u65e5\u671f: \u4e2d\u83ef\u6c11\u570b115\u5e742\u67083\u65e5" in out
    assert "\u767c\u6587\u5b57\u865f: \u570b\u901a\u96fb\u6230\u5b57\u7b2c1153601375\u865f" in out
    assert "\u4e3b\u65e8: \u4ee4\u767c\u570b\u9632\u90e8\u901a\u96fb\u8cc7\u901a\u583111500001\u865f\u4e59\u5247\uff0c\u8acb\u7167\u8fa6\u3002" in out
    assert "\u8aaa\u660e1: \u672c\u4ef6\u5c6c\u300c\u653f\u4ee4\u5ba3\u5c0e\u300d\uff0c\u61c9\u5373\u4e0b\u8f09\u4e26\u9031\u77e5\u5099\u67e5\u3002" in out
    assert "\u8aaa\u660e2: \u672c\u4ef6\u5c6c\u4e00\u822c\u516c\u52d9\u8cc7\u8a0a\u3002" in out
    assert "\u64ec\u7a3f\u8aaa\u660e\u7b2c\u4e00\u9ede\u56fa\u5b9a\u5f15\u8ff0: \u4f9d\u570b\u9632\u90e8\u4e2d\u83ef\u6c11\u570b115\u5e742\u67083\u65e5\u570b\u901a\u96fb\u6230\u5b57\u7b2c1153601375\u865f\u4ee4\u8fa6\u7406\u3002" in out
    assert "\u4f86\u6587\u91cd\u9ede1:" not in out
    assert "\u9644\u4ef6\u91cd\u9ede1: \u9644\u4ef6\u91cd\u9edeA" in out


def test_build_fixed_incoming_point1_strips_fixed_marker_without_regex_error():
    prefix = "\u3010\u64ec\u7a3f\u8aaa\u660e\u7b2c\u4e00\u9ede\u56fa\u5b9a\u5f15\u8ff0\u3011\uff1a"
    with patch("webapps.doc.views_parse._inject_org_level_point", return_value=prefix + "\u6e2c\u8a66\u53e5"):
        out = _build_fixed_incoming_point1(
            org="x",
            level="y",
            doc_date="z",
            doc_no="n",
            doc_type="t",
            doc_subject="s",
            full_text_for_search="",
        )
    assert out == "\u6e2c\u8a66\u53e5"


def test_build_fixed_incoming_point1_removes_legacy_numeric_prefix():
    legacy = "\u91cd\u9ede1\uff1a\u3010\u64ec\u7a3f\u8aaa\u660e\u7b2c\u4e00\u9ede\u56fa\u5b9a\u5f15\u8ff0\u3011\uff1a\u6e2c\u8a66\u53e5"
    with patch("webapps.doc.views_parse._inject_org_level_point", return_value=legacy):
        out = _build_fixed_incoming_point1(
            org="x",
            level="y",
            doc_date="z",
            doc_no="n",
            doc_type="t",
            doc_subject="s",
            full_text_for_search="",
        )
    assert out == "\u6e2c\u8a66\u53e5"


def test_format_focus_summary_v3_allows_more_than_10_attachment_points():
    attachment_points = [f"A{i}" for i in range(1, 13)]
    out = _format_focus_summary_v3(
        sender_org="X",
        recipient_org="Y",
        doc_date="D",
        doc_no="N",
        doc_subject="S",
        incoming_desc=["d1"],
        incoming_point1="q1",
        attachment_points=attachment_points,
    )
    assert "附件重點10: A10" in out
    assert "附件重點12: A12" in out
