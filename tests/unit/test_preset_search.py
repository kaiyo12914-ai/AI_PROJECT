from __future__ import annotations

import json
from unittest.mock import patch
from django.test import Client, TestCase
from django.urls import reverse
from webapps.vanna.models import DataSource, TrainingExample, ExampleEmbedding


class PresetSearchTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.ds, _ = DataSource.objects.get_or_create(
            code="preset_search_test_ds",
            defaults={
                "name": "Preset Search Test DS",
                "db_type": "oracle",
                "default_schema": "LEGACY",
                "enabled": True
            }
        )
        self.url = reverse("nl2sql:api_preset_search")

        # Create approved training examples
        self.ex1 = TrainingExample.objects.create(
            data_source=self.ds,
            question="What is the employee count of MPC?",
            sql_text="SELECT COUNT(*) FROM CT_EMPLOYEE;",
            dialect="oracle",
            review_status="approved",
        )
        self.ex2 = TrainingExample.objects.create(
            data_source=self.ds,
            question="List department names and budget",
            sql_text="SELECT DEPT_NAME FROM CT_DEPARTMENT;",
            dialect="oracle",
            review_status="approved",
        )
        # One not approved to verify it is filtered out
        self.ex3 = TrainingExample.objects.create(
            data_source=self.ds,
            question="Draft question about budget",
            sql_text="SELECT 1;",
            dialect="oracle",
            review_status="draft",
        )

        # Create ExampleEmbedding
        ExampleEmbedding.objects.create(
            training_example=self.ex1,
            data_source=self.ds,
            question_text=self.ex1.question,
            sql_text=self.ex1.sql_text,
            embedding=[0.1] * 1024,
            embedding_dimension=1024,
        )
        ExampleEmbedding.objects.create(
            training_example=self.ex2,
            data_source=self.ds,
            question_text=self.ex2.question,
            sql_text=self.ex2.sql_text,
            embedding=[0.2] * 1024,
            embedding_dimension=1024,
        )

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.llm.embedding_factory.get_shared_embedding_model")
    @patch("webapps.llm.embedding_factory.expected_embedding_dimension")
    def test_preset_search_with_keyword_vector_match(self, mock_expected_dim, mock_get_emb_model, mock_can_access, mock_is_auth):
        mock_can_access.return_value = True
        mock_is_auth.return_value = True
        mock_expected_dim.return_value = 1024

        class MockEmbeddingModel:
            def embed_query(self, text):
                # Return vector close to ex1 embedding
                return [0.1] * 1024

        mock_get_emb_model.return_value = MockEmbeddingModel()

        res = self.client.get(self.url, {"keyword": "employee count", "code": "preset_search_test_ds"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertIn("What is the employee count of MPC?", data["questions"])
        # ex3 should NOT be in the results (draft status)
        self.assertNotIn("Draft question about budget", data["questions"])

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.llm.embedding_factory.get_shared_embedding_model")
    def test_preset_search_with_keyword_sql_fallback(self, mock_get_emb_model, mock_can_access, mock_is_auth):
        mock_can_access.return_value = True
        mock_is_auth.return_value = True
        mock_get_emb_model.return_value = None

        # When embedding model fails or is None, it falls back to SQL query lookup
        res = self.client.get(self.url, {"keyword": "department", "code": "preset_search_test_ds"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertIn("List department names and budget", data["questions"])
        self.assertNotIn("What is the employee count of MPC?", data["questions"])

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    def test_preset_search_empty_keyword(self, mock_can_access, mock_is_auth):
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        res = self.client.get(self.url, {"keyword": "", "code": "preset_search_test_ds"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        # Should return approved examples
        self.assertEqual(len(data["questions"]), 2)
        self.assertIn("What is the employee count of MPC?", data["questions"])
        self.assertIn("List department names and budget", data["questions"])
