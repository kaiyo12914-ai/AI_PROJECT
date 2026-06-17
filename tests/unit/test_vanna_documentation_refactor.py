from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

# Proactively disable require_node decorator during testing
require_node_patcher = patch("webapps.portal.decorators.require_node", lambda *args, **kwargs: lambda f: f)
require_node_patcher.start()

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from webapps.vanna.models import (
    DataSource,
    DocumentationEmbedding,
    SchemaEmbedding,
    SchemaObject,
    TrainingDocumentation,
    VannaTrainingSync,
)
from webapps.vanna.vanna_adapter import retrieve_context


class VannaDocumentationRefactorTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.ds, _ = DataSource.objects.get_or_create(
            code="test_ds",
            defaults={
                "name": "Test Data Source",
                "db_type": "postgresql",
                "default_schema": "public",
                "enabled": True,
            },
        )
        self.url = reverse("nl2sql:api_training_dataset")

    def test_retrieve_context_keyword_fallback(self):
        # Create doc record
        doc = TrainingDocumentation.objects.create(
            data_source=self.ds,
            title="員工薪資表規範",
            documentation="本規範定義員工基本薪資欄位名稱，包括底薪與獎金。",
            created_by="tester",
        )
        # Verify retrieve_context fallback works via keyword search
        ctx = retrieve_context(self.ds, "薪資")
        self.assertIn("schema_chunks", ctx)
        doc_chunks = [c for c in ctx["schema_chunks"] if c["chunk_type"] == "documentation"]
        self.assertEqual(len(doc_chunks), 1)
        self.assertEqual(doc_chunks[0]["name"], "員工薪資表規範")
        self.assertIn("底薪與獎金", doc_chunks[0]["chunk_text"])

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    def test_api_get_documentation(self, _mock_is_admin):
        # Create doc record
        TrainingDocumentation.objects.create(
            data_source=self.ds,
            title="請假流程指南",
            documentation="特休請假需提前三天提出申請。",
            created_by="tester",
        )

        res = self.client.get(self.url, {"code": "test_ds", "all": "true"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        doc_items = data["result"]["documentation_items"]
        self.assertEqual(len(doc_items), 1)
        self.assertEqual(doc_items[0]["name"], "請假流程指南")
        self.assertEqual(doc_items[0]["documentation"], "特休請假需提前三天提出申請。")

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    def test_api_post_documentation(self, _mock_is_admin):
        res = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "code": "test_ds",
                    "training_type": "documentation",
                    "title": "加班申報說明",
                    "documentation": "平日加班上限為四小時。",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["name"], "加班申報說明")

        # Check DB
        doc = TrainingDocumentation.objects.filter(data_source=self.ds, title="加班申報說明").first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.documentation, "平日加班上限為四小時。")
        self.assertTrue(DocumentationEmbedding.objects.filter(training_documentation=doc).exists())

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    def test_api_put_documentation(self, _mock_is_admin):
        doc = TrainingDocumentation.objects.create(
            data_source=self.ds,
            title="舊標題",
            documentation="舊內容描述",
            created_by="tester",
        )
        doc_emb = DocumentationEmbedding.objects.create(
            training_documentation=doc,
            data_source=self.ds,
            title="舊標題",
            documentation_text="舊內容描述",
            embedding=[0.1] * 1024,
            embedding_model="some-model",
            embedding_dimension=1024,
            content_hash="abc123hash",
        )

        res = self.client.generic(
            "PUT",
            self.url,
            json.dumps(
                {
                    "code": "test_ds",
                    "training_type": "documentation",
                    "id": doc.id,
                    "title": "新標題",
                    "documentation": "更新後的新內容描述",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # Check update
        doc.refresh_from_db()
        self.assertEqual(doc.title, "新標題")
        self.assertEqual(doc.documentation, "更新後的新內容描述")

        # Check embedding is reset to None
        doc_emb.refresh_from_db()
        self.assertIsNone(doc_emb.embedding)
        self.assertEqual(doc_emb.title, "新標題")
        self.assertEqual(doc_emb.documentation_text, "更新後的新內容描述")

    @patch("webapps.vanna.api.is_vanna_admin", return_value=True)
    def test_api_delete_documentation(self, _mock_is_admin):
        doc = TrainingDocumentation.objects.create(
            data_source=self.ds,
            title="待刪除文件",
            documentation="這是一份無用文件",
        )
        doc_emb = DocumentationEmbedding.objects.create(
            training_documentation=doc,
            data_source=self.ds,
            title="待刪除文件",
            documentation_text="這是一份無用文件",
            content_hash="deletehash123",
        )
        sync = VannaTrainingSync.objects.create(
            data_source=self.ds,
            sync_type="documentation",
            source_object_id=doc.id,
            content_hash="deletehash123",
            sync_status="synced",
        )

        res = self.client.generic(
            "DELETE",
            self.url,
            json.dumps(
                {
                    "code": "test_ds",
                    "training_type": "documentation",
                    "id": doc.id,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # Check cascade deletions
        self.assertFalse(TrainingDocumentation.objects.filter(id=doc.id).exists())
        self.assertFalse(DocumentationEmbedding.objects.filter(id=doc_emb.id).exists())
        self.assertFalse(VannaTrainingSync.objects.filter(id=sync.id).exists())

    def test_vanna_migrate_documentation_command(self):
        # Setup synthetic legacy document objects
        legacy_obj = SchemaObject.objects.create(
            data_source=self.ds,
            schema_name="LEGACY",
            object_name="VANNA_DOCUMENTATION_MIGRATION_TEST",
            object_type="table",
            ddl_text="",
            is_enabled=True,
        )
        legacy_emb = SchemaEmbedding.objects.create(
            schema_object=legacy_obj,
            chunk_type="documentation",
            chunk_text="遷移標題\n這是遷移的詳細內文說明。",
            embedding=[0.5] * 1024,
            embedding_model="legacy-model",
            embedding_dimension=1024,
            content_hash="legacyhash777",
        )
        sync = VannaTrainingSync.objects.create(
            data_source=self.ds,
            sync_type="documentation",
            source_object_id=legacy_obj.id,
            content_hash="legacyhash777",
            sync_status="synced",
        )

        # Run command
        call_command("vanna_migrate_documentation")

        # Verify legacy cleanup
        self.assertFalse(SchemaObject.objects.filter(id=legacy_obj.id).exists())
        self.assertFalse(SchemaEmbedding.objects.filter(id=legacy_emb.id).exists())

        # Verify new records
        doc = TrainingDocumentation.objects.filter(data_source=self.ds, title="遷移標題").first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.documentation, "這是遷移的詳細內文說明。")

        doc_emb = DocumentationEmbedding.objects.filter(training_documentation=doc).first()
        self.assertIsNotNone(doc_emb)
        embedding_list = list(doc_emb.embedding)
        self.assertEqual(len(embedding_list), 1024)
        self.assertAlmostEqual(embedding_list[0], 0.5, places=5)
        self.assertEqual(doc_emb.embedding_model, "legacy-model")
        self.assertEqual(doc_emb.embedding_dimension, 1024)

        # Verify sync source_object_id update
        sync.refresh_from_db()
        self.assertEqual(sync.source_object_id, doc.id)

    @patch("webapps.vanna.management.commands.nl2sql_embed_schema._get_command_embedding_model")
    @patch("webapps.vanna.management.commands.nl2sql_embed_schema.expected_embedding_dimension", return_value=1024)
    def test_nl2sql_embed_schema_command_for_documentation(self, _mock_dim, mock_get_model):
        doc = TrainingDocumentation.objects.create(
            data_source=self.ds,
            title="批次計算文件",
            documentation="批次計算測試說明。",
        )
        doc_emb = DocumentationEmbedding.objects.create(
            training_documentation=doc,
            data_source=self.ds,
            title="批次計算文件",
            documentation_text="批次計算測試說明。",
            embedding=None,
            content_hash="batchhash888",
        )

        # Mock embedding model
        mock_model_impl = MagicMock()
        mock_model_impl.embed_documents.return_value = [[0.9] * 1024]
        mock_get_model.return_value = (mock_model_impl, "mock-embedder-v2")

        # Call command
        call_command("nl2sql_embed_schema", data_source="test_ds")

        # Check embedding calculation results
        doc_emb.refresh_from_db()
        embedding_list = list(doc_emb.embedding)
        self.assertEqual(len(embedding_list), 1024)
        self.assertAlmostEqual(embedding_list[0], 0.9, places=5)
        self.assertEqual(doc_emb.embedding_model, "mock-embedder-v2")
        self.assertEqual(doc_emb.embedding_dimension, 1024)
