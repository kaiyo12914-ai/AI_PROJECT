from __future__ import annotations

import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from webapps.llm.llm_factory import get_embedding_model
from webapps.vanna.models import DataSource, SchemaEmbedding, ExampleEmbedding


class Command(BaseCommand):
    help = "Batch calculate and save embeddings for SchemaEmbedding and ExampleEmbedding using get_embedding_model()."

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
            embeddings_impl = get_embedding_model()
        except Exception as exc:
            raise CommandError(f"Failed to get embedding model: {exc}")

        # Try to find model name
        model_name = "unknown"
        for attr in ("model", "model_name", "deployment_name", "model_id"):
            if hasattr(embeddings_impl, attr):
                model_name = str(getattr(embeddings_impl, attr))
                break

        self.stdout.write(self.style.SUCCESS(f"Using embedding model: {model_name}"))

        # Process SchemaEmbedding
        schema_embeddings = SchemaEmbedding.objects.filter(
            schema_object__data_source=ds,
            embedding__isnull=True
        )
        se_count = schema_embeddings.count()
        self.stdout.write(self.style.NOTICE(f"Found {se_count} SchemaEmbedding records with empty embeddings."))

        if se_count > 0:
            self._process_schema_embeddings(schema_embeddings, embeddings_impl, model_name, batch_size)

        # Process ExampleEmbedding
        example_embeddings = ExampleEmbedding.objects.filter(
            data_source=ds,
            embedding__isnull=True
        )
        ee_count = example_embeddings.count()
        self.stdout.write(self.style.NOTICE(f"Found {ee_count} ExampleEmbedding records with empty embeddings."))

        if ee_count > 0:
            self._process_example_embeddings(example_embeddings, embeddings_impl, model_name, batch_size)

        self.stdout.write(self.style.SUCCESS("All pending embeddings processed successfully!"))

    def _process_schema_embeddings(self, queryset, embeddings_impl, model_name, batch_size):
        items = list(queryset)
        total = len(items)
        self.stdout.write("Embedding SchemaEmbeddings...")

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            texts = [item.chunk_text for item in batch]
            self.stdout.write(f"  Processing SchemaEmbedding batch {i // batch_size + 1} ({len(batch)} items)...")
            try:
                vectors = embeddings_impl.embed_documents(texts)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Embedding calculation failed: {exc}"))
                continue

            with transaction.atomic():
                for item, vector in zip(batch, vectors):
                    item.embedding = vector
                    item.embedding_model = model_name
                    item.embedding_dimension = len(vector)
                    item.save()

    def _process_example_embeddings(self, queryset, embeddings_impl, model_name, batch_size):
        items = list(queryset)
        total = len(items)
        self.stdout.write("Embedding ExampleEmbeddings...")

        for i in range(0, total, batch_size):
            batch = items[i:i + batch_size]
            # Vanna embedding for question-SQL examples focuses primarily on question_text
            texts = [item.question_text for item in batch]
            self.stdout.write(f"  Processing ExampleEmbedding batch {i // batch_size + 1} ({len(batch)} items)...")
            try:
                vectors = embeddings_impl.embed_documents(texts)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  Embedding calculation failed: {exc}"))
                continue

            with transaction.atomic():
                for item, vector in zip(batch, vectors):
                    item.embedding = vector
                    item.embedding_model = model_name
                    item.embedding_dimension = len(vector)
                    item.save()
