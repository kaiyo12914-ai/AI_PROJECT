from __future__ import annotations

import json
from unittest.mock import patch
from django.test import Client, TestCase
from django.urls import reverse
from webapps.vanna.models import DataSource, QueryLog, FailedQueryRecord, TrainingExample, ExampleEmbedding, VannaTrainingSync


class FailedQueryOptimizeTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.ds = DataSource.objects.create(
            code="test_ds",
            name="Test Data Source",
            db_type="postgresql",
            default_schema="public",
            enabled=True
        )
        self.url = reverse("nl2sql:api_training_dataset")

        # Create dummy QueryLog
        self.qlog = QueryLog.objects.create(
            data_source=self.ds,
            user_id="test_user",
            question="What is the count?",
            generated_sql="SELECT COUNT(*) FROM test;",
            cleaned_sql="SELECT COUNT(*) FROM test;",
            final_sql="SELECT COUNT(*) FROM test;",
            execution_status="failed",
            error_message="Original error",
        )

        # Create FailedQueryRecord
        self.failed_record = FailedQueryRecord.objects.create(
            query_log=self.qlog,
            question="What is the count?",
            failed_sql="SELECT COUNT(*) FROM test;",
            error_message="Original error",
            data_source_code="test_ds",
            status="pending"
        )

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.vanna.api.is_vanna_admin")
    def test_failed_query_update_pending(self, mock_is_admin, mock_can_access, mock_is_auth):
        mock_is_admin.return_value = True
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        res = self.client.generic(
            "PUT",
            self.url,
            json.dumps({
                "code": "test_ds",
                "training_type": "failed",
                "id": self.failed_record.id,
                "analysis": " RAG table missing",
                "action_taken": "Added DDL table",
                "status": "pending",
                "question": "What is the new count?",
                "sql": "SELECT COUNT(*) FROM test_new;"
            }),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])

        # Verify FailedQueryRecord still exists and updated
        self.failed_record.refresh_from_db()
        self.assertEqual(self.failed_record.status, "pending")
        self.assertEqual(self.failed_record.analysis, "RAG table missing")
        self.assertEqual(self.failed_record.action_taken, "Added DDL table")
        self.assertEqual(self.failed_record.question, "What is the new count?")
        self.assertEqual(self.failed_record.failed_sql, "SELECT COUNT(*) FROM test_new;")

        # TrainingExample should NOT exist
        self.assertFalse(TrainingExample.objects.filter(question="What is the new count?").exists())

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.vanna.api.is_vanna_admin")
    @patch("webapps.llm.embedding_factory.get_shared_embedding_model")
    def test_failed_query_optimize_conversion(self, mock_get_emb_model, mock_is_admin, mock_can_access, mock_is_auth):
        mock_is_admin.return_value = True
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        # Mock embedding model to avoid calling external service
        class MockEmbeddingModel:
            def embed_documents(self, texts):
                return [[0.1] * 1024]
        
        mock_get_emb_model.return_value = MockEmbeddingModel()

        res = self.client.generic(
            "PUT",
            self.url,
            json.dumps({
                "code": "test_ds",
                "training_type": "failed",
                "id": self.failed_record.id,
                "status": "optimized",
                "question": "What is the optimized count?",
                "sql": "SELECT COUNT(*) FROM users;"
            }),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data.get("optimized"))

        # 1. Original FailedQueryRecord should be deleted
        self.assertFalse(FailedQueryRecord.objects.filter(id=self.failed_record.id).exists())

        # 2. TrainingExample should be created
        ex = TrainingExample.objects.get(data_source=self.ds, question="What is the optimized count?")
        self.assertEqual(ex.sql_text, "SELECT COUNT(*) FROM users;")
        self.assertEqual(ex.review_status, "approved")

        # 3. ExampleEmbedding should be created
        emb = ExampleEmbedding.objects.get(training_example=ex, data_source=self.ds)
        self.assertEqual(emb.question_text, "What is the optimized count?")
        self.assertEqual(emb.sql_text, "SELECT COUNT(*) FROM users;")
        self.assertIsNotNone(emb.embedding)
        self.assertEqual(len(emb.embedding), 1024)

        # 4. Sync marker should be deleted if any existed
        self.assertFalse(VannaTrainingSync.objects.filter(data_source=self.ds, sync_type="example", source_object_id=ex.id).exists())

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.vanna.api.is_vanna_admin")
    def test_failed_query_optimize_validation_error(self, mock_is_admin, mock_can_access, mock_is_auth):
        mock_is_admin.return_value = True
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        # Case 1: Empty question
        res = self.client.generic(
            "PUT",
            self.url,
            json.dumps({
                "code": "test_ds",
                "training_type": "failed",
                "id": self.failed_record.id,
                "status": "optimized",
                "question": "",
                "sql": "SELECT 1;"
            }),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 400)

        # Case 2: SQL Guard block (e.g. non-SELECT query)
        res = self.client.generic(
            "PUT",
            self.url,
            json.dumps({
                "code": "test_ds",
                "training_type": "failed",
                "id": self.failed_record.id,
                "status": "optimized",
                "question": "What is the count?",
                "sql": "DROP TABLE users;"
            }),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("blocked by SQL Guard", res.json()["error"])
