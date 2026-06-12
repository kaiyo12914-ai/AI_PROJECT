from unittest import mock
from django.test import TestCase

from webapps.vanna.models import DataSource
from webapps.vanna.vanna_adapter import generate_sql, GenerateSqlResult


class TestVannaRelatedQuestions(TestCase):
    def setUp(self):
        # 建立一個測試用的 DataSource 實體（不連實體 DB）
        self.data_source = DataSource.objects.create(
            code="test_ds",
            name="Test Data Source",
            db_type="oracle",
            db_profile="ERP_MPC",
            default_schema="LEGACY",
            enabled=True
        )

    def tearDown(self):
        self.data_source.delete()

    @mock.patch("webapps.vanna.vanna_adapter.ensure_vanna_vendor_loaded")
    @mock.patch("webapps.vanna.vanna_adapter.retrieve_context")
    @mock.patch("webapps.vanna.vanna_adapter.get_chat_model")
    @mock.patch("webapps.vanna.vanna_adapter.validate_sql")
    def test_generate_sql_includes_related_questions_in_context_summary(
        self, mock_validate_sql, mock_get_chat_model, mock_retrieve_context, mock_ensure_loaded
    ):
        # 1. 模擬 retrieve_context 回傳 10 個 Approved SQL 範例
        mock_retrieve_context.return_value = {
            "tables": [],
            "schema_chunks": [],
            "examples": [
                {"question": "問題 1", "sql": "SELECT 1 FROM DUAL"},
                {"question": "問題 2", "sql": "SELECT 2 FROM DUAL"},
                {"question": "問題 3", "sql": "SELECT 3 FROM DUAL"},
                {"question": "問題 4", "sql": "SELECT 4 FROM DUAL"},
                {"question": "問題 5", "sql": "SELECT 5 FROM DUAL"},
                {"question": "問題 6", "sql": "SELECT 6 FROM DUAL"},
                {"question": "問題 7", "sql": "SELECT 7 FROM DUAL"},
                {"question": "問題 8", "sql": "SELECT 8 FROM DUAL"},
                {"question": "問題 9", "sql": "SELECT 9 FROM DUAL"},
                {"question": "問題 10", "sql": "SELECT 10 FROM DUAL"},
            ]
        }

        # 2. 模擬 LLM chat model 的 invoke 方法，回傳模擬 of SQL
        mock_llm = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = "SELECT * FROM CT_EMPLOYEE"
        mock_llm.invoke.return_value = mock_response
        mock_get_chat_model.return_value = mock_llm

        # 3. 模擬 SQL Guard 通過
        mock_validate_sql.return_value = (True, "")

        # 4. 模擬 vanna vendor 載入成功
        mock_runtime = mock.MagicMock()
        mock_runtime.available = True
        mock_runtime.version = "2.0.0"
        mock_runtime.error = ""
        mock_ensure_loaded.return_value = mock_runtime

        # 5. 執行被測試的 generate_sql
        result = generate_sql(self.data_source, "[人事]MPC 查詢在職人員數量", user_id="F1234567")

        # 6. 驗證
        self.assertIsInstance(result, GenerateSqlResult)
        self.assertIn("related_questions", result.context_summary)
        
        related_qs = result.context_summary["related_questions"]
        self.assertEqual(len(related_qs), 10)
        self.assertEqual(related_qs[0], "問題 1")
        self.assertEqual(related_qs[9], "問題 10")

        # 驗證資料庫中的 QueryLog 是否也有被建立
        from webapps.vanna.models import QueryLog
        qlog = QueryLog.objects.get(id=result.query_log_id)
        self.assertEqual(qlog.question, "[人事]MPC 查詢在職人員數量")
        qlog.delete()
