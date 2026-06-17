from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.management import call_command
from django.db import connection
from webapps.vanna.models import DataSource, FailedQueryRecord, TrainingExample, ExampleEmbedding, QueryLog
from webapps.vanna.management.commands.autofix_failed_queries import (
    _detect_column_for_variable,
    _extract_tables_from_sql,
    _lookup_column_metadata
)

# Patch require_node decorator to allow view/command testing
require_node_patcher = patch("webapps.portal.decorators.require_node", lambda *args, **kwargs: lambda f: f)
require_node_patcher.start()

class AutofixFailedQueriesTestCase(TestCase):
    def setUp(self):
        # 建立 DataSource
        self.ds = DataSource.objects.create(
            code="test_ds_autofix",
            name="Autofix Data Source",
            db_type="postgresql",
            default_schema="public",
            enabled=True
        )

        # 動態建立測試用 data_dictionary 實體表
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.data_dictionary (
                    id serial PRIMARY KEY,
                    table_name varchar(100),
                    column_name varchar(100),
                    data_type varchar(50)
                );
            """)
            cursor.execute("TRUNCATE TABLE public.data_dictionary RESTART IDENTITY;")
            
            # 寫入欄位元資料
            cursor.execute(
                "INSERT INTO public.data_dictionary (table_name, column_name, data_type) VALUES (%s, %s, %s)",
                ["CT_EMPLOY", "DEPTNO", "VARCHAR2"]
            )
            cursor.execute(
                "INSERT INTO public.data_dictionary (table_name, column_name, data_type) VALUES (%s, %s, %s)",
                ["CT_EMPLOY", "EMPNO", "VARCHAR2"]
            )

        # 清空測試庫中的現有記錄以避免測試干擾
        FailedQueryRecord.objects.all().delete()
        QueryLog.objects.all().delete()

        # 建立一筆 QueryLog 作為 FailedQueryRecord 的關聯
        self.ql = QueryLog.objects.create(
            data_source=self.ds,
            question="[人事] 查詢指定服務單位中尚未加入人員索引且服務狀況為在職的人員名單",
            generated_sql="SELECT emp.empno FROM ct_employ emp WHERE emp.deptno like :as_deptno",
            execution_status="failed"
        )

        # 建立 FailedQueryRecord
        self.record = FailedQueryRecord.objects.create(
            query_log=self.ql,
            question="[人事] 查詢指定服務單位中尚未加入人員索引且服務狀況為在職的人員名單",
            failed_sql="SELECT emp.empno FROM ct_employ emp WHERE emp.deptno like :as_deptno",
            error_message="Column deptno has invalid value",
            data_source_code="test_ds_autofix",
            status="pending"
        )

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS public.data_dictionary;")

    def test_regex_helpers(self):
        # 1. 測試變數所屬欄位偵測
        sql1 = "SELECT emp.empno FROM ct_employ emp WHERE emp.deptno = :as_deptno"
        self.assertEqual(_detect_column_for_variable(sql1, "as_deptno"), "deptno")

        sql2 = "SELECT * FROM ct_employ WHERE :as_empno = empno"
        self.assertEqual(_detect_column_for_variable(sql2, "as_empno"), "empno")

        # 猜測模式 fallback
        self.assertEqual(_detect_column_for_variable("SELECT * FROM ct_employ", "as_deptno"), "deptno")

        # 2. 測試 Table 提取
        sql3 = "SELECT * FROM ct_employ emp, aa_pers_index pers WHERE emp.empno=pers.empno"
        tables = _extract_tables_from_sql(sql3)
        self.assertIn("CT_EMPLOY", tables)
        self.assertIn("AA_PERS_INDEX", tables)

        # 3. 測試欄位 Metadata 查閱
        meta = _lookup_column_metadata("deptno", ["CT_EMPLOY"])
        self.assertIsNotNone(meta)
        if meta:
            self.assertEqual(meta[0], "CT_EMPLOY")
            self.assertEqual(meta[1], "VARCHAR2")

    @patch("webapps.database.db_factory.db_query_one")
    @patch("webapps.llm.llm_factory.get_chat_model")
    def test_command_dry_run(self, mock_get_chat_model, mock_db_query_one):
        # Mock LLM
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="[人事] 查詢部門為 01 的在職人員名單")
        mock_get_chat_model.return_value = mock_model

        # Mock db_query_one
        mock_db_query_one.return_value = ("01",)

        # 執行 dry-run
        call_command("autofix_failed_queries", dry_run=True, limit=1)

        # 驗證資料表內容沒有被修改
        r = FailedQueryRecord.objects.get(id=self.record.id)
        self.assertEqual(r.status, "pending")
        self.assertEqual(r.failed_sql, "SELECT emp.empno FROM ct_employ emp WHERE emp.deptno like :as_deptno")
        self.assertEqual(TrainingExample.objects.filter(data_source=self.ds).count(), 0)

    @patch("webapps.database.db_factory.db_query_one")
    @patch("webapps.llm.llm_factory.get_chat_model")
    def test_command_execution_only_update(self, mock_get_chat_model, mock_db_query_one):
        # Mock LLM
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="[人事] 查詢部門為 01 的在職人員名單")
        mock_get_chat_model.return_value = mock_model

        # Mock db_query_one
        mock_db_query_one.return_value = ("01",)

        # 執行 command，不帶 auto-approve
        call_command("autofix_failed_queries", limit=1)

        # 驗證 FailedQueryRecord 被就地更新，且狀態依然為 pending
        r = FailedQueryRecord.objects.get(id=self.record.id)
        self.assertEqual(r.status, "pending")
        self.assertEqual(r.failed_sql, "SELECT emp.empno FROM ct_employ emp WHERE emp.deptno like '01'")
        self.assertEqual(r.question, "[人事] 查詢部門為 01 的在職人員名單")

    @patch("webapps.vanna.sql_guard.validate_sql", return_value=(True, ""))
    @patch("webapps.database.db_factory.db_query_one")
    @patch("webapps.llm.llm_factory.get_chat_model")
    def test_command_execution_auto_approve(self, mock_get_chat_model, mock_db_query_one, mock_validate_sql):
        # Mock LLM
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="[人事] 查詢部門為 01 的在職人員名單")
        mock_get_chat_model.return_value = mock_model

        # Mock db_query_one
        mock_db_query_one.return_value = ("01",)

        # 執行 command，帶 auto-approve
        call_command("autofix_failed_queries", auto_approve=True, limit=1)

        # 驗證 FailedQueryRecord 被轉移並刪除
        self.assertFalse(FailedQueryRecord.objects.filter(id=self.record.id).exists())

        # 驗證 TrainingExample 被建立
        te = TrainingExample.objects.filter(data_source=self.ds).first()
        self.assertIsNotNone(te)
        if te:
            self.assertEqual(te.question, "[人事] 查詢部門為 01 的在職人員名單")
            self.assertEqual(te.sql_text, "SELECT emp.empno FROM ct_employ emp WHERE emp.deptno like '01'")
            self.assertEqual(te.review_status, "approved")

    @patch("webapps.database.db_factory.db_query_one")
    @patch("webapps.llm.llm_factory.get_chat_model")
    def test_command_execution_profile_override(self, mock_get_chat_model, mock_db_query_one):
        # Mock LLM
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="[人事] 查詢部門為 01 的在職人員名單")
        mock_get_chat_model.return_value = mock_model

        # Mock db_query_one
        mock_db_query_one.return_value = ("01",)

        # 執行 command，並指定 profile="custom_override_profile"
        call_command("autofix_failed_queries", profile="custom_override_profile", limit=1)

        # 驗證 db_query_one 呼叫時所傳入的 profile 參數是否為指定的 "custom_override_profile"
        mock_db_query_one.assert_called_with("postgresql", unittest.mock.ANY, profile="custom_override_profile")
