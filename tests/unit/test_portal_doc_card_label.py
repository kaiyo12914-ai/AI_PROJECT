from pathlib import Path


def test_portal_doc_card_label_is_not_mojibake():
    path = Path(r"h:\AI\AI_TOOLS\webapps\portal\templates\portal\index.html")
    text = path.read_text(encoding="utf-8")

    assert 'title="公文解析"' in text
    assert 'subtitle="來文附件查詢 / 公文內容解析"' in text
    assert 'title="????"' not in text
