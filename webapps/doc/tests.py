from django.test import SimpleTestCase

from webapps.doc.views_generate import _normalize_subordinate_unit_short_name
from webapps.doc.views_generate import _sanitize_stage2_facts
from webapps.doc.views_parse import _is_address_like_text
from webapps.doc.views_parse import _is_speed_level_like_text


class SubordinateUnitShortNameTests(SimpleTestCase):
    def test_full_title_converts_to_short_name(self):
        src = "請國防部軍備局生產製造中心第四0一廠依限辦理。"
        out = _normalize_subordinate_unit_short_name(src)
        self.assertEqual(out, "請第四0一廠依限辦理。")

    def test_fullwidth_zero_title_converts_to_short_name(self):
        src = "請國防部軍備局生產製造中心第四０一廠配合執行。"
        out = _normalize_subordinate_unit_short_name(src)
        self.assertEqual(out, "請第四０一廠配合執行。")


class AddressFilteringTests(SimpleTestCase):
    def test_address_marked_as_non_key_point(self):
        self.assertTrue(_is_address_like_text("地址：臺北市中正區忠孝西路1段1號"))
        self.assertTrue(_is_address_like_text("臺北市中正區忠孝西路1段1號"))
        self.assertFalse(_is_address_like_text("本案請於兩週內完成改善計畫。"))
        self.assertTrue(_is_speed_level_like_text("速別：最速件"))
        self.assertTrue(_is_speed_level_like_text("最速件"))
        self.assertFalse(_is_speed_level_like_text("請於兩週內回復辦理情形。"))

    def test_stage2_facts_remove_address_lines(self):
        facts = [
            "來文重點1：請於兩週內完成改善計畫。",
            "附件重點2：地址：臺北市中正區忠孝西路1段1號",
            "附件重點3：高雄市前鎮區中山二路99號",
            "來文重點4：速別：最速件",
            "附件重點5：普通件",
        ]
        out = _sanitize_stage2_facts(facts, incoming_text="")
        self.assertIn("請於兩週內完成改善計畫。", out)
        self.assertNotIn("地址：臺北市中正區忠孝西路1段1號", out)
        self.assertNotIn("高雄市前鎮區中山二路99號", out)
        self.assertNotIn("速別：最速件", out)
        self.assertNotIn("普通件", out)
