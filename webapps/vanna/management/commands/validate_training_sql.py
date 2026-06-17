from __future__ import annotations

import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone
from webapps.database.db_factory import db_query_all
from webapps.vanna.models import DataSource
from webapps.vanna.sql_guard import validate_sql

class Command(BaseCommand):
    help = "Validate executability of SQL statements in public.nl2sql_training_example1 and update review_status."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of examples to validate (0 for unlimited).",
        )
        parser.add_argument(
            "--pending-only",
            action="store_true",
            help="Only validate records with empty or 'draft' review_status.",
        )
        parser.add_argument(
            "--id",
            type=int,
            default=0,
            help="Validate a single record by its ID.",
        )
        parser.add_argument(
            "--profile",
            type=str,
            default="",
            help="Override the DB profile used to execute queries (e.g. ERP_MPC, ERP_202).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force validation of all records, including those already marked OK.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        pending_only = options["pending_only"]
        single_id = options["id"]
        override_profile = options["profile"]
        force = options["force"]

        self.stdout.write(self.style.NOTICE("Checking table public.nl2sql_training_example1 existence..."))
        
        # Verify table existence
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'nl2sql_training_example1'
                );
            """)
            if not cursor.fetchone()[0]:
                raise CommandError("Table 'public.nl2sql_training_example1' does not exist in the database.")

        # Build query
        query = "SELECT id, sql_text, data_source_id, question, review_status FROM public.nl2sql_training_example1"
        conditions = []
        params = []

        if single_id > 0:
            conditions.append("id = %s")
            params.append(single_id)
        else:
            if pending_only:
                conditions.append("(review_status IS NULL OR review_status = '' OR review_status = 'draft')")
            elif not force:
                conditions.append("(review_status IS NULL OR review_status <> 'OK')")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id ASC"

        if limit > 0:
            query += " LIMIT %s"
            params.append(limit)

        self.stdout.write(self.style.NOTICE("Fetching training examples..."))
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not records:
            self.stdout.write(self.style.SUCCESS("No records found to validate."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(records)} records to validate."))

        # Cache DataSources
        data_sources = {ds.id: ds for ds in DataSource.objects.all()}

        ok_count = 0
        not_ok_count = 0

        for record in records:
            rec_id = record["id"]
            sql = record["sql_text"]
            ds_id = record["data_source_id"]
            question = record["question"] or ""
            current_status = record["review_status"] or ""

            self.stdout.write(self.style.NOTICE(f"Validating Record ID={rec_id}..."))
            
            if not sql:
                self.stdout.write(self.style.WARNING(f"  Record ID={rec_id} has empty sql_text. Marking NOT OK."))
                self.update_status(rec_id, "NOT OK")
                not_ok_count += 1
                continue

            if not ds_id:
                self.stdout.write(self.style.WARNING(f"  Record ID={rec_id} has no data_source_id. Marking NOT OK."))
                self.update_status(rec_id, "NOT OK")
                not_ok_count += 1
                continue

            if ds_id not in data_sources:
                self.stdout.write(self.style.WARNING(f"  Record ID={rec_id} data_source_id={ds_id} not found in DataSource. Marking NOT OK."))
                self.update_status(rec_id, "NOT OK")
                not_ok_count += 1
                continue

            ds = data_sources[ds_id]
            profile_to_use = override_profile if override_profile else ds.db_profile
            self.stdout.write(self.style.NOTICE(f"  Data Source: {ds.code} ({ds.db_type}), Profile: {profile_to_use or '(none)'}"))

            # SQL Guard security check
            is_safe, guard_err = validate_sql(sql)
            if not is_safe:
                self.stdout.write(self.style.ERROR(f"  Record ID={rec_id} blocked by SQL Guard: {guard_err}. Marking NOT OK."))
                self.update_status(rec_id, "NOT OK")
                not_ok_count += 1
                continue

            # Process Oracle SQL suffix semicolon
            run_sql = sql.strip()
            if ds.db_type == "oracle":
                run_sql = run_sql.rstrip(";").strip()

            # Execute
            try:
                # Limit 1 to optimize
                rows = db_query_all(ds.db_type, run_sql, profile=profile_to_use, limit=1)
                if rows and len(rows) > 0:
                    self.stdout.write(self.style.SUCCESS(f"  Record ID={rec_id} validated successfully (returned {len(rows)} rows)."))
                    self.update_status(rec_id, "OK")
                    ok_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  Record ID={rec_id} executed without error but returned 0 rows. Marking NOT OK."))
                    self.update_status(rec_id, "NOT OK")
                    not_ok_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Record ID={rec_id} failed with error: {e}. Marking NOT OK."))
                self.update_status(rec_id, "NOT OK")
                not_ok_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Validation Completed. Total={len(records)}, OK={ok_count}, NOT OK={not_ok_count}."
        ))

    def update_status(self, record_id: int, status: str):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.nl2sql_training_example1 SET review_status = %s, updated_at = %s WHERE id = %s",
                [status, timezone.now(), record_id]
            )



# 驗證計畫
# 自動化測試
# 執行以下指令驗證單元測試是否通過：

# powershell

# venv/Scripts/pytest tests/unit/test_validate_training_sql.py
# 手動驗證方式
# 在開發/測試環境建立 dummy 資料來源與 nl2sql_training_example1 資料表。
# 填入測試 SQL 資料。
# 執行 python manage.py validate_training_sql，觀察終端機輸出與資料庫資料更新是否正確。
# python manage.py validate_training_sql --pending-only --limit 5 --profile ERP_MPC
