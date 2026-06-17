from __future__ import annotations

from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from django.db import connection
from webapps.vanna.models import DataSource, TrainingExample, ExampleEmbedding, QueryLog, FailedQueryRecord

class ClassifyTrainingSqlTestCase(TestCase):
    def setUp(self):
        # Create DataSource
        self.ds = DataSource.objects.create(
            code="test_ds_cls",
            name="Classify Data Source",
            db_type="postgresql",
            default_schema="public",
            enabled=True
        )

        # Dynamic table creation in test db
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.nl2sql_training_example1 (
                    id serial PRIMARY KEY,
                    question text,
                    sql_text text,
                    dialect varchar,
                    review_status varchar,
                    created_by varchar,
                    created_at timestamp with time zone,
                    updated_at timestamp with time zone,
                    data_source_id bigint
                );
            """)
            # Clean up records if table existed
            cursor.execute("TRUNCATE TABLE public.nl2sql_training_example1 RESTART IDENTITY;")
            
            # Insert mock records
            # 1. OK case: valid query, status OK
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status, created_by) VALUES (%s, %s, %s, %s, %s)",
                ["OK Question", "SELECT 1;", self.ds.id, "OK", "test_user"]
            )
            # 2. NOT OK case: status NOT OK
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status, created_by) VALUES (%s, %s, %s, %s, %s)",
                ["NOT OK Question", "SELECT error;", self.ds.id, "NOT OK", "test_user"]
            )
            # 3. Draft case: should be ignored
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status, created_by) VALUES (%s, %s, %s, %s, %s)",
                ["Draft Question", "SELECT 3;", self.ds.id, "draft", "test_user"]
            )

    def tearDown(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS public.nl2sql_training_example1;")

    def test_classify_dry_run(self):
        # Run command with --dry-run
        call_command("classify_training_sql", dry_run=True)

        # Verify no database change in target models
        self.assertEqual(TrainingExample.objects.filter(data_source=self.ds).count(), 0)
        self.assertEqual(FailedQueryRecord.objects.filter(data_source_code=self.ds.code).count(), 0)

        # Verify nl2sql_training_example1 still has all records
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM public.nl2sql_training_example1;")
            self.assertEqual(cursor.fetchone()[0], 3)

    def test_classify_execution(self):
        # Run command without --dry-run
        call_command("classify_training_sql")

        # Verify TrainingExample created for 'OK' record
        examples = TrainingExample.objects.filter(data_source=self.ds)
        self.assertEqual(examples.count(), 1)
        ex = examples.first()
        self.assertEqual(ex.question, "OK Question")
        self.assertEqual(ex.sql_text, "SELECT 1;")
        self.assertEqual(ex.review_status, "approved")

        # Verify ExampleEmbedding created with Null embedding
        embeddings = ExampleEmbedding.objects.filter(training_example=ex)
        self.assertEqual(embeddings.count(), 1)
        emb = embeddings.first()
        self.assertIsNone(emb.embedding)

        # Verify FailedQueryRecord and QueryLog created for 'NOT OK' record
        failed_records = FailedQueryRecord.objects.filter(data_source_code=self.ds.code)
        self.assertEqual(failed_records.count(), 1)
        fr = failed_records.first()
        self.assertEqual(fr.question, "NOT OK Question")
        self.assertEqual(fr.failed_sql, "SELECT error;")
        self.assertEqual(fr.query_log.execution_status, "failed")

        # Verify nl2sql_training_example1 only has the draft record left
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, review_status FROM public.nl2sql_training_example1;")
            remaining = cursor.fetchall()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][1], "draft")
