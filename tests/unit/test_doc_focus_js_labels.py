from pathlib import Path


def test_doc_focus_js_supports_new_chinese_labels():
    path = Path(__file__).resolve().parents[2] / "webapps/doc/static/doc/js/doc_index_editor.js"
    text = path.read_text(encoding="utf-8")

    assert r"\u4f86\u6587\u6a5f\u95dc" in text
    assert r"\u53d7\u6587\u6a5f\u95dc" in text
    assert r"\u767c\u6587\u65e5\u671f" in text
    assert r"\u767c\u6587\u5b57\u865f" in text
    assert r"\u8aaa\u660e" in text
    assert r"\u4f86\u6587\u91cd\u9ede" in text
    assert r"\u64ec\u7a3f\u8aaa\u660e\u7b2c\u4e00\u9ede\u56fa\u5b9a\u5f15\u8ff0" in text
    assert r"\u9644\u4ef6\u91cd\u9ede" in text


def test_doc_focus_js_has_no_mojibake_placeholders_in_focus_parser():
    path = Path(__file__).resolve().parents[2] / "webapps/doc/static/doc/js/doc_index_editor.js"
    text = path.read_text(encoding="utf-8")

    assert "function parseFocusSummaryItems" in text
    assert "function selectedFocusItemsText" in text
    assert "${x.label}\\uFF1A${x.text}" in text
    assert "???" not in text[text.index("function extractFocusSummaryHeader"):text.index("function syncDocTypeSelectors")]


def test_doc_focus_js_keeps_error_message_on_parse_failure():
    path = Path(__file__).resolve().parents[2] / "webapps/doc/static/doc/js/doc_index_editor.js"
    text = path.read_text(encoding="utf-8")
    assert "resetFocusPick({ clearOutputs: false })" in text


def test_doc_focus_js_stage2_facts_preserves_fixed_quote_marker():
    path = Path(__file__).resolve().parents[2] / "webapps/doc/static/doc/js/doc_index_editor.js"
    text = path.read_text(encoding="utf-8")
    assert r"\u3010\u64ec\u7a3f\u8aaa\u660e\u7b2c\u4e00\u9ede\u56fa\u5b9a\u5f15\u8ff0\u3011\uFF1A${text}" in text
