from __future__ import annotations

import hashlib
import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from webapps.vanna.models import DataSource, TrainingExample, ExampleEmbedding, QueryLog, FailedQueryRecord

def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

class Command(BaseCommand):
    help = "Classify records in public.nl2sql_training_example1 based on review_status ('OK' -> TrainingExample/ExampleEmbedding, 'NOT OK' -> FailedQueryRecord)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be classified without making any database changes.",
        )
        parser.add_argument(
            "--embed",
            action="store_true",
            help="Calculate and save vector embeddings for OK records immediately.",
        )
        parser.add_argument(
            "--keep-records",
            action="store_true",
            help="Do not delete processed records from public.nl2sql_training_example1 table.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        embed = options["embed"]
        keep_records = options["keep_records"]

        self.stdout.write(self.style.NOTICE("Checking public.nl2sql_training_example1 table existence..."))
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

        self.stdout.write(self.style.NOTICE("Fetching OK/NOT OK records from public.nl2sql_training_example1..."))
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, question, sql_text, dialect, data_source_id, review_status, created_by 
                FROM public.nl2sql_training_example1 
                WHERE review_status IN ('OK', 'NOT OK')
                ORDER BY id ASC;
            """)
            columns = [col[0] for col in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not records:
            self.stdout.write(self.style.SUCCESS("No records with review_status 'OK' or 'NOT OK' found to classify."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(records)} records to process."))

        # Initialize embedding model if needed
        embeddings_impl = None
        model_name = ""
        if embed and not dry_run:
            self.stdout.write(self.style.NOTICE("Initializing shared embedding model for --embed..."))
            try:
                from webapps.llm.embedding_factory import get_shared_embedding_model, get_shared_embedding_model_name
                embeddings_impl = get_shared_embedding_model()
                model_name = get_shared_embedding_model_name()
                self.stdout.write(self.style.SUCCESS(f"Embedding model loaded: {model_name}"))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Could not load embedding model: {exc}. Will fallback to Null embeddings."))
                embeddings_impl = None

        # Cache DataSources
        data_sources = {ds.id: ds for ds in DataSource.objects.all()}

        ok_processed = 0
        not_ok_processed = 0
        skipped = 0

        for r in records:
            rec_id = r["id"]
            question = r["question"] or ""
            sql_text = r["sql_text"] or ""
            dialect = r["dialect"] or ""
            ds_id = r["data_source_id"]
            status = r["review_status"]
            created_by = r["created_by"] or ""

            if not ds_id:
                self.stdout.write(self.style.WARNING(f"Record ID={rec_id} has no data_source_id. Skipping."))
                skipped += 1
                continue

            if ds_id not in data_sources:
                self.stdout.write(self.style.WARNING(f"Record ID={rec_id} has invalid data_source_id {ds_id}. Skipping."))
                skipped += 1
                continue

            ds = data_sources[ds_id]

            if status == "OK":
                self.stdout.write(self.style.NOTICE(f"Record ID={rec_id} [OK] -> Transferring to TrainingExample..."))
                if not dry_run:
                    try:
                        with transaction.atomic():
                            # 1. Create TrainingExample (prevent duplicate)
                            ex, created = TrainingExample.objects.get_or_create(
                                data_source=ds,
                                question=question,
                                sql_text=sql_text,
                                defaults={
                                    "dialect": dialect or ("oracle" if ds.db_type == "oracle" else "postgresql"),
                                    "review_status": "approved",
                                    "created_by": created_by,
                                }
                            )
                            if not created:
                                self.stdout.write(f"  TrainingExample already exists (ID={ex.id}).")

                            # 2. Calculate/Save Embedding
                            content_hash = _content_hash(f"{question}\n{sql_text}")
                            vector = None
                            emb_model = ""
                            emb_dim = 0
                            
                            if embeddings_impl:
                                try:
                                    vectors = embeddings_impl.embed_documents([question])
                                    if vectors and len(vectors) > 0:
                                        vector = vectors[0]
                                        emb_model = model_name
                                        emb_dim = len(vector)
                                except Exception as exc:
                                    self.stdout.write(self.style.WARNING(f"  Embedding calculation failed for ID={rec_id}: {exc}"))

                            # update or create embedding record
                            ExampleEmbedding.objects.update_or_create(
                                training_example=ex,
                                data_source=ds,
                                defaults={
                                    "question_text": question,
                                    "sql_text": sql_text,
                                    "content_hash": content_hash,
                                    "embedding": vector,
                                    "embedding_model": emb_model,
                                    "embedding_dimension": emb_dim or 1024,
                                }
                            )

                            # 3. Remove from nl2sql_training_example1
                            if not keep_records:
                                with connection.cursor() as del_cursor:
                                    del_cursor.execute("DELETE FROM public.nl2sql_training_example1 WHERE id = %s", [rec_id])
                        
                        ok_processed += 1
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f"  Failed to transfer Record ID={rec_id}: {exc}"))
                        skipped += 1
                else:
                    ok_processed += 1

            elif status == "NOT OK":
                self.stdout.write(self.style.NOTICE(f"Record ID={rec_id} [NOT OK] -> Transferring to FailedQueryRecord..."))
                if not dry_run:
                    try:
                        with transaction.atomic():
                            # 1. Create dummy QueryLog
                            qlog = QueryLog.objects.create(
                                data_source=ds,
                                user_id=created_by,
                                question=question,
                                generated_sql=sql_text,
                                cleaned_sql=sql_text,
                                final_sql=sql_text,
                                execution_status="failed",
                                error_message="Manually marked as NOT OK from public.nl2sql_training_example1",
                            )

                            # 2. Create FailedQueryRecord
                            FailedQueryRecord.objects.create(
                                query_log=qlog,
                                question=question,
                                failed_sql=sql_text,
                                error_message="Manually marked as NOT OK from public.nl2sql_training_example1",
                                data_source_code=ds.code,
                                status="pending",
                            )

                            # 3. Remove from nl2sql_training_example1
                            if not keep_records:
                                with connection.cursor() as del_cursor:
                                    del_cursor.execute("DELETE FROM public.nl2sql_training_example1 WHERE id = %s", [rec_id])
                        
                        not_ok_processed += 1
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f"  Failed to transfer Record ID={rec_id}: {exc}"))
                        skipped += 1
                else:
                    not_ok_processed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Classification completed. (Dry-run={dry_run}) "
            f"Processed: OK={ok_processed}, NOT OK={not_ok_processed}, Skipped={skipped}."
        ))
