import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
import django

django.setup()

from webapps.doc.views_generate import _extract_fixed_quote_from_stage2_facts


def test_extract_fixed_quote_from_stage2_facts_with_bracketed_marker():
    facts = [
        "說明1：其他文字",
        "【擬稿說明第一點固定引述】：遵國防部民國115年2月3日國通電戰字第1153601375號令辦理(如附呈)。",
    ]
    out = _extract_fixed_quote_from_stage2_facts(facts)
    assert out == "遵國防部民國115年2月3日國通電戰字第1153601375號令辦理(如附呈)。"


def test_extract_fixed_quote_from_stage2_facts_with_plain_marker():
    facts = [
        "附件重點1：內容A",
        "擬稿說明第一點固定引述：依核示辦理。",
    ]
    out = _extract_fixed_quote_from_stage2_facts(facts)
    assert out == "依核示辦理。"
