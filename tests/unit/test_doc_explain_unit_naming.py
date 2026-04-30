import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.doc.views_generate import _normalize_explain_unit_names_by_point


def test_explain_point1_uses_full_name_point2_plus_use_short_name():
    src = (
        "一、請第401廠依來文事項辦理。\n"
        "二、請國防部軍備局生產製造中心第401廠於期限內回報。\n"
        "三、請國防部軍備局生製中心第205廠配合執行。"
    )
    out = _normalize_explain_unit_names_by_point(src)
    lines = [x.strip() for x in out.splitlines() if x.strip()]

    assert lines[0].startswith("一、請國防部軍備局生產製造中心第401廠")
    assert "國防部軍備局生產製造中心第401廠" not in lines[1]
    assert "國防部軍備局生製中心第205廠" not in lines[2]
    assert "二、請第401廠" in lines[1]
    assert "三、請第205廠" in lines[2]
