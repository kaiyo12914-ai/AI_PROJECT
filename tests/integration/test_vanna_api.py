from __future__ import annotations

from unittest.mock import patch
# 必須在載入任何 Django 與 app api 模組前啟動 require_node 裝飾器的 Mock
require_node_patcher = patch("webapps.portal.decorators.require_node", lambda *args, **kwargs: lambda f: f)
require_node_patcher.start()

import json
from unittest.mock import MagicMock
from django.test import SimpleTestCase, Client
from django.urls import reverse


class VannaApiIntegrationTestCase(SimpleTestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client()
        self.generate_url = reverse("nl2sql:api_generate")
        self.execute_url = reverse("nl2sql:api_execute")

    @patch("webapps.vanna.api.generate_sql")
    @patch("webapps.vanna.api._resolve_data_source")
    def test_generate_api_success(self, mock_resolve_ds, mock_generate_sql):
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_ds.db_type = "postgresql"
        mock_resolve_ds.return_value = mock_ds

        from webapps.vanna.vanna_adapter import GenerateSqlResult
        mock_generate_sql.return_value = GenerateSqlResult(
            sql="SELECT * FROM mock_table",
            prompt="Dummy Prompt",
            context_summary={
                "tables": [{"schema": "public", "name": "mock_table"}],
                "examples": 0,
                "vendor_available": True,
                "vendor_version": "2.0.0",
                "guard_status": "passed",
                "guard_message": ""
            },
            query_log_id=123,
            latency_ms=150
        )

        payload = {
            "code": "test_ds",
            "question": "查詢所有 mock_table 資料"
        }
        res = self.client.post(
            self.generate_url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["sql"], "SELECT * FROM mock_table")
        self.assertEqual(data["result"]["query_log_id"], 123)

    @patch("webapps.vanna.sql_guard.validate_sql")
    @patch("webapps.vanna.models.QueryLog.objects.get")
    def test_generate_api_blocked_by_guard(self, mock_qlog_get, mock_validate_sql):
        # 測試當 SQL Guard 判斷為不安全時
        mock_validate_sql.return_value = (False, "SQL contains forbidden operation: 'DROP'")
        
        # 模擬 QueryLog 實體
        mock_qlog = MagicMock()
        mock_qlog.cleaned_sql = "DROP TABLE users"
        mock_qlog.generated_sql = "DROP TABLE users"
        mock_qlog.data_source.db_type = "postgresql"
        mock_qlog.data_source.enabled = True
        mock_qlog_get.return_value = mock_qlog

        payload = {
            "query_log_id": 999
        }
        res = self.client.post(
            self.execute_url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 403)
        data = res.json()
        self.assertFalse(data["ok"])
        self.assertIn("blocked by SQL Guard", data["error"])

        # 驗證日誌狀態被設為 blocked
        self.assertEqual(mock_qlog.guard_status, "blocked")

    @patch("django.db.connection.cursor")
    @patch("webapps.vanna.models.QueryLog.objects.get")
    def test_execute_api_postgresql_success(self, mock_qlog_get, mock_cursor):
        # 模擬資料庫 cursor 執行結果
        mock_cur = MagicMock()
        mock_cur.description = [("id",), ("name",), ("status",)]
        mock_cur.fetchall.return_value = [
            (1, "A", "ACTIVE"),
            (2, "B", "PENDING")
        ]
        mock_cursor.return_value.__enter__.return_value = mock_cur

        mock_qlog = MagicMock()
        mock_qlog.cleaned_sql = "SELECT id, name, status FROM mock_table"
        mock_qlog.generated_sql = "SELECT id, name, status FROM mock_table"
        mock_qlog.data_source.db_type = "postgresql"
        mock_qlog.data_source.enabled = True
        mock_qlog_get.return_value = mock_qlog

        payload = {
            "query_log_id": 123
        }
        res = self.client.post(
            self.execute_url,
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["columns"], ["id", "name", "status"])
        self.assertEqual(data["rows"], [[1, "A", "ACTIVE"], [2, "B", "PENDING"]])
        self.assertFalse(data["is_mock"])

        # 驗證日誌狀態更新為 success
        self.assertEqual(mock_qlog.execution_status, "success")
        self.assertEqual(mock_qlog.row_count, 2)
