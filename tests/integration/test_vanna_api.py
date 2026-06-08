from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse


require_node_patcher = patch("webapps.portal.decorators.require_node", lambda *args, **kwargs: lambda f: f)
require_node_patcher.start()


class VannaApiIntegrationTestCase(SimpleTestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client()
        self.page_url = reverse("nl2sql:page")
        self.schema_sync_url = reverse("nl2sql:api_schema_sync")
        self.training_sync_url = reverse("nl2sql:api_training_sync")
        self.training_dataset_url = reverse("nl2sql:api_training_dataset")
        self.generate_url = reverse("nl2sql:api_generate")
        self.execute_url = reverse("nl2sql:api_execute")

    @patch("webapps.vanna.views.is_vanna_admin", return_value=False)
    def test_page_hides_management_panel_for_non_admin(self, _mock_is_admin):
        res = self.client.get(self.page_url)
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertNotIn("數據管理", html)
        self.assertNotIn("Vanna 訓練資料集維護", html)

    @patch("webapps.vanna.views.is_vanna_admin", return_value=True)
    def test_page_shows_management_panel_for_admin(self, _mock_is_admin):
        res = self.client.get(self.page_url)
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")
        self.assertIn("數據管理", html)
        self.assertIn("Vanna 訓練資料集維護", html)

    def test_schema_sync_api_forbidden_for_non_admin(self):
        res = self.client.post(
            self.schema_sync_url,
            data=json.dumps({"code": "legacy_vanna_chroma"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()["ok"])

    def test_training_sync_api_forbidden_for_non_admin(self):
        res = self.client.post(
            self.training_sync_url,
            data=json.dumps({"code": "legacy_vanna_chroma"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()["ok"])

    def test_training_dataset_api_forbidden_for_non_admin(self):
        res = self.client.get(self.training_dataset_url, {"code": "legacy_vanna_chroma"})
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()["ok"])

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    @patch("webapps.vanna.api._training_dataset_payload")
    @patch("webapps.vanna.api._resolve_data_source")
    def test_training_dataset_api_get_success(self, mock_resolve_ds, mock_payload, _mock_is_admin):
        mock_ds = MagicMock()
        mock_resolve_ds.return_value = mock_ds
        mock_payload.return_value = {"summary": {"approved_examples": 1}}

        res = self.client.get(self.training_dataset_url, {"code": "legacy_vanna_chroma"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["summary"]["approved_examples"], 1)

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    @patch("webapps.vanna.api.TrainingExample.objects.create")
    @patch("webapps.vanna.api._resolve_data_source")
    def test_training_dataset_api_post_adds_approved_example(self, mock_resolve_ds, mock_create, _mock_is_admin):
        mock_ds = MagicMock()
        mock_ds.db_type = "oracle"
        mock_resolve_ds.return_value = mock_ds
        mock_example = MagicMock()
        mock_example.id = 88
        mock_example.question = "[人事]205廠 查詢各單位人數"
        mock_example.sql_text = "SELECT * FROM CT_DEPARTMENT"
        mock_example.review_status = "approved"
        mock_create.return_value = mock_example

        res = self.client.post(
            self.training_dataset_url,
            data=json.dumps(
                {
                    "code": "legacy_vanna_chroma",
                    "question": "[人事]205廠 查詢各單位人數",
                    "sql": "SELECT * FROM CT_DEPARTMENT",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["id"], 88)
        self.assertEqual(mock_create.call_args.kwargs["review_status"], "approved")

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    @patch("webapps.vanna.api._resolve_data_source")
    def test_training_dataset_api_post_blocks_unsafe_sql(self, mock_resolve_ds, _mock_is_admin):
        mock_ds = MagicMock()
        mock_ds.db_type = "oracle"
        mock_resolve_ds.return_value = mock_ds

        res = self.client.post(
            self.training_dataset_url,
            data=json.dumps(
                {
                    "code": "legacy_vanna_chroma",
                    "question": "刪除資料",
                    "sql": "DELETE FROM CT_DEPARTMENT",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.json()["ok"])

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    @patch("webapps.vanna.api.SchemaEmbedding.objects.update_or_create")
    @patch("webapps.vanna.api.SchemaObject.objects.update_or_create")
    @patch("webapps.vanna.api._resolve_data_source")
    def test_training_dataset_api_post_adds_ddl(
        self,
        mock_resolve_ds,
        mock_schema_update,
        mock_embedding_update,
        _mock_is_admin,
    ):
        mock_ds = MagicMock()
        mock_ds.default_schema = "LEGACY"
        mock_resolve_ds.return_value = mock_ds
        mock_schema_obj = MagicMock()
        mock_schema_obj.id = 91
        mock_schema_obj.schema_name = "LEGACY"
        mock_schema_obj.object_name = "CT_EMPLOYEE"
        mock_schema_obj.object_type = "table"
        mock_schema_update.return_value = (mock_schema_obj, True)
        mock_embedding_update.return_value = (MagicMock(), True)

        res = self.client.post(
            self.training_dataset_url,
            data=json.dumps(
                {
                    "code": "legacy_vanna_chroma",
                    "training_type": "ddl",
                    "ddl": "CREATE TABLE CT_EMPLOYEE (EMPNO VARCHAR2(20))",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["training_type"], "ddl")
        self.assertEqual(mock_schema_update.call_args.kwargs["object_name"], "CT_EMPLOYEE")

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    @patch("webapps.vanna.api.SchemaEmbedding.objects.update_or_create")
    @patch("webapps.vanna.api.SchemaObject.objects.update_or_create")
    @patch("webapps.vanna.api._resolve_data_source")
    def test_training_dataset_api_post_adds_documentation(
        self,
        mock_resolve_ds,
        mock_schema_update,
        mock_embedding_update,
        _mock_is_admin,
    ):
        mock_ds = MagicMock()
        mock_ds.default_schema = "LEGACY"
        mock_resolve_ds.return_value = mock_ds
        mock_doc_obj = MagicMock()
        mock_doc_obj.object_name = "VANNA_DOCUMENTATION_ABC"
        mock_schema_update.return_value = (mock_doc_obj, True)
        mock_doc_embedding = MagicMock()
        mock_doc_embedding.id = 92
        mock_embedding_update.return_value = (mock_doc_embedding, True)

        res = self.client.post(
            self.training_dataset_url,
            data=json.dumps(
                {
                    "code": "legacy_vanna_chroma",
                    "training_type": "documentation",
                    "title": "在職狀態",
                    "documentation": "status = ACTIVE 代表在職。",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["training_type"], "documentation")
        self.assertIn("在職狀態", data["result"]["documentation"])

    @patch("webapps.vanna.api.generate_sql")
    @patch("webapps.vanna.api._resolve_data_source")
    def test_generate_api_success(self, mock_resolve_ds, mock_generate_sql):
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_ds.db_type = "oracle"
        mock_resolve_ds.return_value = mock_ds

        from webapps.vanna.vanna_adapter import GenerateSqlResult

        mock_generate_sql.return_value = GenerateSqlResult(
            sql="SELECT * FROM CT_EMPLOY",
            prompt="Dummy Prompt",
            context_summary={
                "tables": [{"schema": "LEGACY", "name": "CT_EMPLOY"}],
                "examples": 0,
                "vendor_available": True,
                "vendor_version": "2.0.0",
                "guard_status": "passed",
                "guard_message": "",
            },
            query_log_id=123,
            latency_ms=150,
        )

        res = self.client.post(
            self.generate_url,
            data=json.dumps({"code": "legacy_vanna_chroma", "question": "查詢人事資料"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["sql"], "SELECT * FROM CT_EMPLOY")
        self.assertEqual(data["result"]["query_log_id"], 123)
        self.assertIn("execution_policy", data["result"])

    @patch("webapps.vanna.sql_guard.validate_sql")
    @patch("webapps.vanna.models.QueryLog.objects.get")
    def test_execute_api_blocked_by_guard(self, mock_qlog_get, mock_validate_sql):
        mock_validate_sql.return_value = (False, "SQL contains forbidden operation: 'DROP'")
        mock_qlog = MagicMock()
        mock_qlog.cleaned_sql = "DROP TABLE users"
        mock_qlog.generated_sql = "DROP TABLE users"
        mock_qlog.data_source.db_type = "oracle"
        mock_qlog.data_source.enabled = True
        mock_qlog_get.return_value = mock_qlog

        res = self.client.post(
            self.execute_url,
            data=json.dumps({"query_log_id": 999}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        data = res.json()
        self.assertFalse(data["ok"])
        self.assertIn("blocked by SQL Guard", data["error"])
        self.assertEqual(mock_qlog.guard_status, "blocked")

    @override_settings(ENV_NAME="EXT")
    @patch("webapps.vanna.models.QueryLog.objects.get")
    def test_execute_api_postgresql_blocked_metadata_only(self, mock_qlog_get):
        mock_qlog = MagicMock()
        mock_qlog.cleaned_sql = "SELECT id, name, status FROM nl2sql_data_source"
        mock_qlog.generated_sql = "SELECT id, name, status FROM nl2sql_data_source"
        mock_qlog.data_source.db_type = "postgresql"
        mock_qlog.data_source.enabled = True
        mock_qlog_get.return_value = mock_qlog

        res = self.client.post(
            self.execute_url,
            data=json.dumps({"query_log_id": 123}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)
        data = res.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["policy"]["mode"], "metadata_store_only")
        self.assertEqual(mock_qlog.execution_status, "blocked_metadata_store_only")

    @override_settings(ENV_NAME="EXT")
    @patch("webapps.vanna.models.QueryLog.objects.get")
    def test_execute_api_oracle_ext_returns_sql_only(self, mock_qlog_get):
        mock_qlog = MagicMock()
        mock_qlog.cleaned_sql = "SELECT * FROM CT_EMPLOY"
        mock_qlog.generated_sql = "SELECT * FROM CT_EMPLOY"
        mock_qlog.data_source.db_type = "oracle"
        mock_qlog.data_source.enabled = True
        mock_qlog_get.return_value = mock_qlog

        res = self.client.post(
            self.execute_url,
            data=json.dumps({"query_log_id": 123}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["sql_only"])
        self.assertEqual(data["sql"], "SELECT * FROM CT_EMPLOY")
        self.assertEqual(data["policy"]["mode"], "sql_only_ext")
        self.assertEqual(mock_qlog.execution_status, "not_executed_ext_sql_only")

    @override_settings(ENV_NAME="INT")
    @patch("webapps.database.db_factory.db_connect")
    @patch("webapps.vanna.models.QueryLog.objects.get")
    def test_execute_api_oracle_int_executes(self, mock_qlog_get, mock_db_connect):
        mock_cur = MagicMock()
        mock_cur.description = [("EMPNO",), ("NAME",)]
        mock_cur.fetchall.return_value = [("001", "Alice")]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_db_connect.return_value = mock_conn

        mock_qlog = MagicMock()
        mock_qlog.cleaned_sql = "SELECT EMPNO, NAME FROM CT_EMPLOY"
        mock_qlog.generated_sql = "SELECT EMPNO, NAME FROM CT_EMPLOY"
        mock_qlog.data_source.db_type = "oracle"
        mock_qlog.data_source.enabled = True
        mock_qlog.data_source.db_profile = ""
        mock_qlog.latency_ms = 0
        mock_qlog_get.return_value = mock_qlog

        res = self.client.post(
            self.execute_url,
            data=json.dumps({"query_log_id": 123}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["sql_only"])
        self.assertEqual(data["columns"], ["EMPNO", "NAME"])
        self.assertEqual(data["rows"], [["001", "Alice"]])
        self.assertEqual(data["policy"]["mode"], "oracle_execute")
        self.assertEqual(mock_qlog.execution_status, "success")
        self.assertEqual(mock_qlog.row_count, 1)
