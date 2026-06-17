from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from webapps.llm.embedding_factory import (
    expected_embedding_dimension,
    get_shared_embedding_model,
    get_shared_embedding_model_name,
)
from webapps.vanna.models import DataSource, SchemaEmbedding, ExampleEmbedding


def _expected_dimension() -> int:
    return expected_embedding_dimension()


def _get_command_embedding_model():
    return get_shared_embedding_model(), get_shared_embedding_model_name()


class Command(BaseCommand):
    help = "Batch calculate and save embeddings for SchemaEmbedding and ExampleEmbedding using the shared embedding factory."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-source",
            default="legacy_vanna_chroma",
            help="Data source code to process.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of records to embed in one batch.",
        )

    def handle(self, *args, **options):
        ds_code = options["data_source"]
        batch_size = options["batch_size"]

        try:
            ds = DataSource.objects.get(code=ds_code)
        except DataSource.DoesNotExist:
            raise CommandError(f"DataSource with code '{ds_code}' does not exist.")

        self.stdout.write(self.style.NOTICE("Initializing embedding model..."))
        try:
            embeddings_impl, model_name = _get_command_embedding_model()
        except Exception as exc:
            raise CommandError(f"Failed to get embedding model: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Using embedding model: {model_name}"))
        self.stdout.write(self.style.NOTICE(f"Expected embedding dimension: {_expected_dimension()}"))

        # Process SchemaEmbedding
        schema_embeddings = SchemaEmbedding.objects.filter(
            schema_object__data_source=ds,
            embedding__isnull=True
        )
        se_count = schema_embeddings.count()
        self.stdout.write(self.style.NOTICE(f"Found {se_count} SchemaEmbedding records with empty embeddings."))

        se_success, se_failed = 0, 0
        if se_count > 0:
            se_success, se_failed = self._process_schema_embeddings(schema_embeddings, embeddings_impl, model_name, batch_size)

        # Process ExampleEmbedding
        example_embeddings = ExampleEmbedding.objects.filter(
            data_source=ds,
            embedding__isnull=True
        )
        ee_count = example_embeddings.count()
        self.stdout.write(self.style.NOTICE(f"Found {ee_count} ExampleEmbedding records with empty embeddings."))

        ee_success, ee_failed = 0, 0
        if ee_count > 0:
            ee_success, ee_failed = self._process_example_embeddings(example_embeddings, embeddings_impl, model_name, batch_size)

        self.stdout.write(self.style.SUCCESS(
            f"All pending embeddings processed successfully!\n"
            f"SchemaEmbeddings: Success={se_success}, Failed={se_failed}\n"
            f"ExampleEmbeddings: Success={ee_success}, Failed={ee_failed}"
        ))

    def _process_schema_embeddings(self, queryset, embeddings_impl, model_name, batch_size):
        items = list(queryset)
        total = len(items)
        self.stdout.write("Embedding SchemaEmbeddings...")
        success_count = 0
        failed_count = 0

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            texts = [item.chunk_text for item in batch]
            self.stdout.write(f"  Processing SchemaEmbedding batch {i // batch_size + 1} ({len(batch)} items)...")
            try:
                vectors = embeddings_impl.embed_documents(texts)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Embedding calculation failed: {exc}"))
                failed_count += len(batch)
                continue

            with transaction.atomic():
                for item, vector in zip(batch, vectors):
                    if len(vector) != _expected_dimension():
                        self.stdout.write(
                            self.style.ERROR(
                                f"  Skip SchemaEmbedding id={item.id}: vector dimension {len(vector)} "
                                f"!= expected {_expected_dimension()}"
                            )
                        )
                        failed_count += 1
                        continue
                    item.embedding = vector
                    item.embedding_model = model_name
                    item.embedding_dimension = len(vector)
                    item.save()
                    success_count += 1
        return success_count, failed_count

    def _process_example_embeddings(self, queryset, embeddings_impl, model_name, batch_size):
        items = list(queryset)
        total = len(items)
        self.stdout.write("Embedding ExampleEmbeddings...")
        success_count = 0
        failed_count = 0

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            # Vanna embedding for question-SQL examples focuses primarily on question_text
            texts = [item.question_text for item in batch]
            self.stdout.write(f"  Processing ExampleEmbedding batch {i // batch_size + 1} ({len(batch)} items)...")
            try:
                vectors = embeddings_impl.embed_documents(texts)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Embedding calculation failed: {exc}"))
                failed_count += len(batch)
                continue

            with transaction.atomic():
                for item, vector in zip(batch, vectors):
                    if len(vector) != _expected_dimension():
                        self.stdout.write(
                            self.style.ERROR(
                                f"  Skip ExampleEmbedding id={item.id}: vector dimension {len(vector)} "
                                f"!= expected {_expected_dimension()}"
                            )
                        )
                        failed_count += 1
                        continue
                    item.embedding = vector
                    item.embedding_model = model_name
                    item.embedding_dimension = len(vector)
                    item.save()
                    success_count += 1
        return success_count, failed_count
