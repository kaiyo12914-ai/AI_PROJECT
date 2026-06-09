from __future__ import annotations

import json
from unittest.mock import patch
from django.test import Client, TestCase
from django.urls import reverse
from webapps.vanna.models import DataSource, SchemaObject, SchemaEmbedding, TrainingExample, VannaTrainingSync


class VannaTrainingCrudTestCase(TestCase):
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

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.vanna.api.is_vanna_admin")
    def test_get_training_dataset_with_slice_and_all(self, mock_is_admin, mock_can_access, mock_is_auth):
        mock_is_admin.return_value = True
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        # Create 35 training examples
        for i in range(35):
            TrainingExample.objects.create(
                data_source=self.ds,
                question=f"Question {i}",
                sql_text=f"SELECT {i};",
                review_status="approved"
            )

        # GET without all=true -> should slice to 30
        res = self.client.get(self.url, {"code": "test_ds"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["result"]["training_examples"]), 30)

        # GET with all=true -> should return all 35
        res = self.client.get(self.url, {"code": "test_ds", "all": "true"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["result"]["training_examples"]), 35)

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.vanna.api.is_vanna_admin")
    def test_delete_sql_example(self, mock_is_admin, mock_can_access, mock_is_auth):
        mock_is_admin.return_value = True
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        ex = TrainingExample.objects.create(
            data_source=self.ds,
            question="What is the total count?",
            sql_text="SELECT COUNT(*) FROM users;",
            review_status="approved"
        )
        # Create a sync record
        sync = VannaTrainingSync.objects.create(
            data_source=self.ds,
            sync_type="example",
            source_object_id=ex.id,
            sync_status="synced"
        )

        # Delete it
        res = self.client.generic(
            "DELETE",
            self.url,
            json.dumps({"code": "test_ds", "training_type": "sql", "id": ex.id}),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # Verify it's deleted
        self.assertFalse(TrainingExample.objects.filter(id=ex.id).exists())
        self.assertFalse(VannaTrainingSync.objects.filter(id=sync.id).exists())

    @patch("webapps.portal.decorators._is_authenticated_user")
    @patch("webapps.portal.decorators.can_access")
    @patch("webapps.vanna.api.is_vanna_admin")
    def test_update_sql_example(self, mock_is_admin, mock_can_access, mock_is_auth):
        mock_is_admin.return_value = True
        mock_can_access.return_value = True
        mock_is_auth.return_value = True

        ex = TrainingExample.objects.create(
            data_source=self.ds,
            question="What is the count?",
            sql_text="SELECT COUNT(*) FROM users;",
            review_status="approved"
        )
        sync = VannaTrainingSync.objects.create(
            data_source=self.ds,
            sync_type="example",
            source_object_id=ex.id,
            sync_status="synced"
        )

        # Update it
        res = self.client.generic(
            "PUT",
            self.url,
            json.dumps({
                "code": "test_ds",
                "training_type": "sql",
                "id": ex.id,
                "question": "What is the new count?",
                "sql": "SELECT COUNT(*) FROM new_users;"
            }),
            content_type="application/json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # Verify updated values
        ex.refresh_from_db()
        self.assertEqual(ex.question, "What is the new count?")
        self.assertEqual(ex.sql_text, "SELECT COUNT(*) FROM new_users;")
        
        # Verify sync is deleted (needs re-sync)
        self.assertFalse(VannaTrainingSync.objects.filter(id=sync.id).exists())
