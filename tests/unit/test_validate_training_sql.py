from __future__ import annotations

from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from django.db import connection
from webapps.vanna.models import DataSource

class ValidateTrainingSqlTestCase(TestCase):
    def setUp(self):
        # Create DataSource
        self.ds = DataSource.objects.create(
            code="test_ds_val",
            name="Val Data Source",
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
            # 1. OK case: valid query, returns data
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status) VALUES (%s, %s, %s, %s)",
                ["Query 1", "SELECT 1;", self.ds.id, "draft"]
            )
            # 2. NOT OK case: valid query, returns no data
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status) VALUES (%s, %s, %s, %s)",
                ["Query 2", "SELECT 0;", self.ds.id, "draft"]
            )
            # 3. NOT OK case: syntax error or execution failure
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status) VALUES (%s, %s, %s, %s)",
                ["Query 3", "SELECT error;", self.ds.id, "draft"]
            )
            # 4. NOT OK case: SQL Guard blocked (DML)
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status) VALUES (%s, %s, %s, %s)",
                ["Query 4", "INSERT INTO test_table VALUES (1);", self.ds.id, "draft"]
            )
            # 5. NOT OK case: invalid data_source_id
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status) VALUES (%s, %s, %s, %s)",
                ["Query 5", "SELECT 1;", 9999, "draft"]
            )
            # 6. OK case already validated: should be skipped by default, but processed under --force
            cursor.execute(
                "INSERT INTO public.nl2sql_training_example1 (question, sql_text, data_source_id, review_status) VALUES (%s, %s, %s, %s)",
                ["Query 6", "SELECT error;", self.ds.id, "OK"]
            )

    def tearDown(self):
        # Drop table
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS public.nl2sql_training_example1;")

    @patch("webapps.vanna.management.commands.validate_training_sql.db_query_all")
    def test_validate_training_sql_command(self, mock_db_query):
        def side_effect(db_type, sql, *args, **kwargs):
            if "SELECT 1" in sql:
                return [(1,)]
            elif "SELECT 0" in sql:
                return []
            elif "SELECT error" in sql:
                raise RuntimeError("DB execution failed simulated error")
            return []

        mock_db_query.side_effect = side_effect

        # Run command
        call_command("validate_training_sql")

        # Verify results in database (Record 6 should remain OK because it was skipped by default)
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, review_status FROM public.nl2sql_training_example1 ORDER BY id ASC;")
            results = cursor.fetchall()
            
        expected_statuses = {
            1: "OK",       # SELECT 1 -> returned data, no error
            2: "NOT OK",   # SELECT 0 -> no data
            3: "NOT OK",   # SELECT error -> threw exception
            4: "NOT OK",   # INSERT INTO -> blocked by SQL Guard
            5: "NOT OK",   # invalid datasource id
            6: "OK",       # Already OK -> skipped by default
        }
        
        for rec_id, status in results:
            self.assertEqual(status, expected_statuses[rec_id], f"Record ID {rec_id} expected {expected_statuses[rec_id]}, got {status}")

    @patch("webapps.vanna.management.commands.validate_training_sql.db_query_all")
    def test_validate_training_sql_command_force(self, mock_db_query):
        def side_effect(db_type, sql, *args, **kwargs):
            if "SELECT 1" in sql:
                return [(1,)]
            elif "SELECT 0" in sql:
                return []
            elif "SELECT error" in sql:
                raise RuntimeError("DB execution failed simulated error")
            return []

        mock_db_query.side_effect = side_effect

        # Run command with --force
        call_command("validate_training_sql", force=True)

        # Verify results in database (Record 6 should be updated to NOT OK under --force)
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, review_status FROM public.nl2sql_training_example1 ORDER BY id ASC;")
            results = cursor.fetchall()
            
        expected_statuses = {
            1: "OK",
            2: "NOT OK",
            3: "NOT OK",
            4: "NOT OK",
            5: "NOT OK",
            6: "NOT OK",   # Force re-validation -> updated to NOT OK because SELECT error raises exception
        }
        
        for rec_id, status in results:
            self.assertEqual(status, expected_statuses[rec_id], f"Record ID {rec_id} expected {expected_statuses[rec_id]}, got {status}")

    @patch("webapps.vanna.management.commands.validate_training_sql.db_query_all")
    def test_validate_training_sql_command_with_profile(self, mock_db_query):
        captured_profiles = []
        def side_effect(db_type, sql, *args, **kwargs):
            captured_profiles.append(kwargs.get("profile"))
            return [(1,)]

        mock_db_query.side_effect = side_effect

        # Run command overriding profile to "ERP_202"
        call_command("validate_training_sql", profile="ERP_202")

        # Check that we invoked db_query_all with the profile "ERP_202"
        self.assertIn("ERP_202", captured_profiles)

