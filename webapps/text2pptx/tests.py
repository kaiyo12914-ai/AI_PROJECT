from __future__ import annotations

import io
import os
import tempfile
import unicodedata
from urllib.parse import unquote
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from webapps.text2pptx import views


class Text2PptxHelperTests(SimpleTestCase):
    def test_extract_json_object_from_fenced_text(self):
        raw = """```json
        {"main_title":"A","main_subtitle":"B","slides":[]}
        ```"""
        extracted = views._extract_json_object(raw)
        self.assertEqual(extracted, '{"main_title":"A","main_subtitle":"B","slides":[]}')

    def test_normalize_analysis_result_invalid_slide_type_falls_back_to_content(self):
        data = {
            "main_title": "主標",
            "main_subtitle": "副標",
            "slides": [
                {
                    "title": "頁1",
                    "slide_type": "unknown_type",
                    "bullets": ["a", "b"],
                }
            ],
        }
        out = views._normalize_analysis_result(data, source_text="頁1\na\nb")
        self.assertEqual(out["slides"][0]["slide_type"], "content")

    @patch("webapps.text2pptx.views.get_chat_model")
    def test_analyze_text_with_llm_parses_json_with_extra_explanation(self, mock_get_chat_model):
        class DummyLLM:
            def invoke(self, _prompt):
                return (
                    "以下是分析結果：\n"
                    "```json\n"
                    '{"main_title":"T","main_subtitle":"S","slides":[{"title":"A","slide_type":"content","bullets":["x"]}]}\n'
                    "```\n"
                    "結束。"
                )

        mock_get_chat_model.return_value = DummyLLM()
        out = views._analyze_text_with_llm("原文")
        self.assertEqual(out["main_title"], "T")
        self.assertEqual(out["slides"][0]["title"], "A")
        self.assertEqual(out["slides"][0]["slide_type"], "content")

    @patch("webapps.text2pptx.views.get_chat_model")
    def test_analyze_text_with_llm_falls_back_when_non_json(self, mock_get_chat_model):
        class DummyLLM:
            def invoke(self, _prompt):
                return "這是一段沒有 JSON 的回覆"

        mock_get_chat_model.return_value = DummyLLM()
        out = views._analyze_text_with_llm("頁1\n點1\n===\n頁2\n點2")
        self.assertEqual(out["main_title"], views.DEFAULT_MAIN_TITLE)
        self.assertEqual(len(out["slides"]), 2)
        self.assertEqual(out["slides"][0]["title"], "頁1")
        self.assertEqual(out["slides"][0]["slide_type"], "content")

    @patch("webapps.text2pptx.views.get_chat_model")
    def test_analyze_text_with_llm_falls_back_when_incomplete_json(self, mock_get_chat_model):
        class DummyLLM:
            def invoke(self, _prompt):
                return '{"main_title":"X","main_subtitle":"Y","slides":[{"title":"A"'

        mock_get_chat_model.return_value = DummyLLM()
        out = views._analyze_text_with_llm("單頁標題\n重點")
        self.assertEqual(out["main_title"], views.DEFAULT_MAIN_TITLE)
        self.assertEqual(len(out["slides"]), 1)
        self.assertEqual(out["slides"][0]["title"], "單頁標題")

    def test_parse_marked_text_structure_chinese_markers(self):
        text = """[標題投影片] 智慧文件流程優化專案提案
提案單位：資訊處
===
[章節標題] 章節一：現況與目標
本章重點摘要
===
[內容頁] 提案背景
痛點一
痛點二
===
[雙欄必較頁] 成本與時程
左欄：自建成本高、時程長
右欄：採購成本中、時程短
===
[雙欄必較頁] 風險比較
左欄：自建需技術團隊
右欄：採購受供應商排程影響"""
        out = views._parse_marked_text_structure(text)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["main_title"], "智慧文件流程優化專案提案")
        self.assertEqual(out["main_subtitle"], "提案單位：資訊處")
        self.assertEqual(len(out["slides"]), 4)
        self.assertEqual(out["slides"][0]["slide_type"], "section")
        self.assertEqual(out["slides"][1]["slide_type"], "content")
        self.assertEqual(out["slides"][2]["slide_type"], "two_content")
        self.assertEqual(out["slides"][3]["slide_type"], "comparison")

    def test_clear_all_slides_removes_existing_template_slides(self):
        from pptx import Presentation

        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[0])
        prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
        self.assertEqual(len(prs.slides), 2)
        views._clear_all_slides(prs)
        self.assertEqual(len(prs.slides), 0)

    def test_safe_select_template_supports_chinese_filename(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as td:
            fname_nfc = "中心測試.pptx"
            with open(os.path.join(td, fname_nfc), "wb") as f:
                f.write(b"x")
            with patch.object(views, "PPTX_TEMPLATE_DIR", td):
                selected = views._safe_select_template(unicodedata.normalize("NFD", fname_nfc))
            self.assertEqual(selected, os.path.join(td, fname_nfc))

    def test_save_template_bytes_preserves_chinese_filename(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as td:
            with patch.object(views, "PPTX_TEMPLATE_DIR", td):
                saved1 = views._save_template_bytes("中心測試.pptx", b"a")
                saved2 = views._save_template_bytes("中心測試.pptx", b"b")
            self.assertEqual(saved1, "中心測試.pptx")
            self.assertEqual(saved2, "中心測試_1.pptx")
            self.assertTrue(os.path.exists(os.path.join(td, saved1)))
            self.assertTrue(os.path.exists(os.path.join(td, saved2)))

    def test_build_download_filename_avoids_double_extension(self):
        self.assertEqual(views._build_download_filename("測試主題"), "測試主題.pptx")
        self.assertEqual(views._build_download_filename("測試主題.pptx"), "測試主題.pptx")


@override_settings(PORTAL_ACL_ENABLED=False)
class Text2PptxViewTests(SimpleTestCase):
    databases = {"default"}

    def test_generate_rejects_empty_text(self):
        resp = self.client.post("/text2pptx/generate/", {"text": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("請輸入文字內容", resp.json().get("error", ""))

    def test_generate_rejects_too_long_text(self):
        with patch.object(views, "MAX_INPUT_CHARS", 3):
            resp = self.client.post("/text2pptx/generate/", {"text": "1234"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("文字內容超過上限", resp.json().get("error", ""))

    def test_index_lists_chinese_template_filename(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as td:
            with open(os.path.join(td, "中心測試.pptx"), "wb") as f:
                f.write(b"x")
            with patch.object(views, "PPTX_TEMPLATE_DIR", td):
                resp = self.client.get("/text2pptx/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "投影片可引用版面範例")
        self.assertContains(resp, "中心測試.pptx")
        self.assertContains(resp, "預設範本缺失，改用內建")
        self.assertContains(resp, "引用範例並產生 PPTX")
        self.assertContains(resp, "前往範本管理（管理者）")
        self.assertNotContains(resp, "匯入範本（含四種版型審查）")

    def test_index_uses_default_template_when_available(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as td:
            with open(os.path.join(td, "預設範本.pptx"), "wb") as f:
                f.write(b"x")
            with open(os.path.join(td, "中心測試.pptx"), "wb") as f:
                f.write(b"x")
            with patch.object(views, "PPTX_TEMPLATE_DIR", td):
                resp = self.client.get("/text2pptx/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "（預設範本：預設範本.pptx）")

    def test_template_admin_page_renders_import_panel(self):
        resp = self.client.get("/text2pptx/template-admin/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "TEXT → PPTX 範本管理")
        self.assertContains(resp, "匯入範本（含四種版型審查）")

    @patch("webapps.text2pptx.views._audit_template_bytes")
    def test_import_template_rejects_when_required_layout_missing(self, mock_audit):
        mock_audit.return_value = {
            "ok": False,
            "missing": ["章節標題（Section Header）"],
            "found": {},
        }
        f = SimpleUploadedFile(
            "bad_template.pptx",
            b"fake-pptx-content",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        resp = self.client.post("/text2pptx/import-template/", {"template_file": f}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "TEXT → PPTX 範本管理")
        self.assertContains(resp, "匯入失敗，缺少必要版型")

    @patch("webapps.text2pptx.views._save_template_bytes")
    @patch("webapps.text2pptx.views._audit_template_bytes")
    def test_import_template_success_message(self, mock_audit, mock_save):
        mock_audit.return_value = {
            "ok": True,
            "missing": [],
            "found": {
                "cover": "Title Slide",
                "section": "Section Header",
                "content": "Title and Content",
                "two_content": "Two Content",
            },
        }
        mock_save.return_value = "uploaded_ok.pptx"
        f = SimpleUploadedFile(
            "ok_template.pptx",
            b"fake-pptx-content",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        resp = self.client.post("/text2pptx/import-template/", {"template_file": f}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "TEXT → PPTX 範本管理")
        self.assertContains(resp, "匯入成功：uploaded_ok.pptx")

    @patch("webapps.text2pptx.views._analyze_text_with_llm")
    def test_generate_uses_markers_without_calling_llm(self, mock_analyze):
        resp = self.client.post(
            "/text2pptx/generate/",
            {
                "text": "[標題投影片] 封面標題\n副標\n===\n[內容頁] 內容頁\n重點一\n重點二",
                "title": "",
                "template": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        mock_analyze.assert_not_called()

    @patch("webapps.text2pptx.views._analyze_text_with_llm")
    def test_section_slide_keeps_all_bullets(self, mock_analyze):
        mock_analyze.return_value = {
            "main_title": "主標",
            "main_subtitle": "副標",
            "slides": [
                {
                    "title": "章節標題",
                    "slide_type": "section",
                    "bullets": ["重點一", "重點二", "重點三"],
                }
            ],
        }
        resp = self.client.post("/text2pptx/generate/", {"text": "x", "title": "", "template": ""})
        self.assertEqual(resp.status_code, 200)

        from pptx import Presentation

        prs = Presentation(io.BytesIO(resp.content))
        self.assertEqual(len(prs.slides), 2)  # cover + section
        all_text = []
        for sh in prs.slides[1].shapes:
            if getattr(sh, "has_text_frame", False):
                all_text.append((sh.text or "").strip())
        joined = "\n".join(all_text)
        self.assertIn("重點一", joined)
        self.assertIn("重點二", joined)
        self.assertIn("重點三", joined)

    @patch("webapps.text2pptx.views._analyze_text_with_llm")
    def test_generate_supports_multiple_slide_types_and_title_override(self, mock_analyze):
        mock_analyze.return_value = {
            "main_title": "AI 產生主標",
            "main_subtitle": "AI 副標",
            "slides": [
                {
                    "title": "章節標題",
                    "slide_type": "section",
                    "bullets": ["重點摘要"],
                },
                {
                    "title": "雙欄必較頁",
                    "slide_type": "comparison",
                    "left_title": "已完成",
                    "right_title": "待完成",
                    "bullets": [f"項目{i}" for i in range(1, 18)],
                },
                {
                    "title": "一般內容",
                    "slide_type": "content",
                    "bullets": ["A", "B", "C"],
                },
            ],
        }

        resp = self.client.post(
            "/text2pptx/generate/",
            {
                "text": "任意原文",
                "title": "使用者自訂主標",
                "template": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        cd_raw = resp["Content-Disposition"]
        self.assertIn("filename*=", cd_raw)
        encoded_name = cd_raw.split("filename*=UTF-8''", 1)[1]
        self.assertIn("使用者自訂主標.pptx", unquote(encoded_name))

        from pptx import Presentation

        prs = Presentation(io.BytesIO(resp.content))
        # cover(1) + section(1) + comparison(17 bullets => 2 pages) + content(1) = 5
        self.assertEqual(len(prs.slides), 5)
