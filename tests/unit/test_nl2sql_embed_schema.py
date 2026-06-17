from __future__ import annotations

from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from webapps.vanna.models import DataSource, SchemaObject, SchemaEmbedding, TrainingExample, ExampleEmbedding

class Nl2SqlEmbedSchemaTestCase(TestCase):
    def setUp(self):
        # Create DataSource
        self.ds = DataSource.objects.create(
            code="test_ds_embed",
            name="Embed Data Source",
            db_type="postgresql",
            default_schema="public",
            enabled=True
        )
        
        # Create SchemaObject and SchemaEmbedding with Null embedding
        self.so = SchemaObject.objects.create(
            data_source=self.ds,
            schema_name="public",
            object_name="test_table",
            object_type="table"
        )
        self.se = SchemaEmbedding.objects.create(
            schema_object=self.so,
            chunk_type="documentation",
            chunk_text="This is a test table",
            embedding=None
        )

        # Create TrainingExample and ExampleEmbedding with Null embedding
        self.te = TrainingExample.objects.create(
            data_source=self.ds,
            question="test question?",
            sql_text="SELECT * FROM test_table;"
        )
        self.ee = ExampleEmbedding.objects.create(
            training_example=self.te,
            data_source=self.ds,
            question_text="test question?",
            sql_text="SELECT * FROM test_table;",
            embedding=None
        )

    @patch("webapps.vanna.management.commands.nl2sql_embed_schema._get_command_embedding_model")
    def test_embed_schema_execution(self, mock_get_model):
        # Mock embedding model
        class MockEmbeddingModel:
            def embed_documents(self, texts):
                # Return dummy vectors of 1024 dimensions
                return [[0.1] * 1024 for _ in texts]

        mock_get_model.return_value = (MockEmbeddingModel(), "mock-embed-model")

        # Run command
        call_command("nl2sql_embed_schema", data_source="test_ds_embed")

        # Refresh from db
        self.se.refresh_from_db()
        self.ee.refresh_from_db()

        # Check embeddings are filled
        self.assertIsNotNone(self.se.embedding)
        self.assertEqual(len(self.se.embedding), 1024)
        self.assertEqual(self.se.embedding_model, "mock-embed-model")

        self.assertIsNotNone(self.ee.embedding)
        self.assertEqual(len(self.ee.embedding), 1024)
        self.assertEqual(self.ee.embedding_model, "mock-embed-model")
