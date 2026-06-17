from __future__ import annotations

import json
from django.core.management.base import BaseCommand
from django.db import transaction
from webapps.vanna.models import (
    SchemaObject,
    SchemaEmbedding,
    TrainingDocumentation,
    DocumentationEmbedding,
    VannaTrainingSync,
)


class Command(BaseCommand):
    help = "Migrate Vanna documentation chunks from SchemaEmbedding to dedicated TrainingDocumentation and DocumentationEmbedding tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without making any database changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write(self.style.NOTICE(f"Scanning for legacy documentation embeddings... (dry-run={dry_run})"))

        doc_embeddings = SchemaEmbedding.objects.filter(chunk_type="documentation").select_related(
            "schema_object", "schema_object__data_source"
        )
        total_found = doc_embeddings.count()

        if total_found == 0:
            self.stdout.write(self.style.SUCCESS("No legacy documentation embeddings found to migrate."))
            return

        self.stdout.write(self.style.NOTICE(f"Found {total_found} legacy documentation records. Migrating..."))

        migrated_count = 0
        error_count = 0

        # 用於收集遷移後需要被刪除的舊 SchemaObject id 以及 SchemaEmbedding id
        old_emb_ids_to_delete = []

        for emb in doc_embeddings:
            obj = emb.schema_object
            data_source = obj.data_source
            content = emb.chunk_text or ""

            # 解析 title 與 description
            # 格式通常為 "標題\n內容" 或者是只有內容
            lines = content.split("\n", 1)
            if len(lines) == 2 and len(lines[0]) < 100:
                title = lines[0].strip()
                doc_text = lines[1].strip()
            else:
                title = ""
                doc_text = content.strip()

            self.stdout.write(f"  Processing row id={emb.id}: Title='{title}', Source={data_source.code}")

            if not dry_run:
                try:
                    with transaction.atomic():
                        # 1. 建立/更新 TrainingDocumentation 主表記錄
                        doc, created = TrainingDocumentation.objects.update_or_create(
                            data_source=data_source,
                            title=title,
                            documentation=doc_text,
                            defaults={
                                "created_by": "vanna_documentation_migration",
                            },
                        )

                        # 2. 建立/更新 DocumentationEmbedding 向量表記錄
                        DocumentationEmbedding.objects.update_or_create(
                            training_documentation=doc,
                            data_source=data_source,
                            content_hash=emb.content_hash,
                            defaults={
                                "title": title,
                                "documentation_text": doc_text,
                                "embedding": emb.embedding,
                                "embedding_model": emb.embedding_model,
                                "embedding_dimension": emb.embedding_dimension,
                            },
                        )

                        # 3. 移轉 VannaTrainingSync 中的關聯 id
                        VannaTrainingSync.objects.filter(
                            data_source=data_source,
                            sync_type="documentation",
                            content_hash=emb.content_hash,
                        ).update(source_object_id=doc.id)

                    migrated_count += 1
                    old_emb_ids_to_delete.append(emb.id)
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"    Failed to migrate row {emb.id}: {exc}"))
                    error_count += 1
            else:
                migrated_count += 1

        self.stdout.write(self.style.NOTICE(f"Migration phase complete. Migrated: {migrated_count}, Errors: {error_count}"))

        if not dry_run and migrated_count > 0:
            self.stdout.write(self.style.NOTICE("Starting database cleanup of old synthetic objects..."))
            with transaction.atomic():
                # 1. 刪除原有的 SchemaEmbedding 中 chunk_type="documentation" 的記錄
                deleted_embs, _ = SchemaEmbedding.objects.filter(id__in=old_emb_ids_to_delete).delete()

                # 2. 篩選需要清理的舊虛擬 SchemaObject
                # 包括以 "VANNA_DOCUMENTATION_" 或 "VANNA_LEGACY_DOCUMENTATION" 開頭的
                virtual_objects = SchemaObject.objects.filter(
                    object_name__startswith="VANNA_DOCUMENTATION_"
                ) | SchemaObject.objects.filter(object_name="VANNA_LEGACY_DOCUMENTATION")

                virtual_objects_count = virtual_objects.count()
                deleted_objs, _ = virtual_objects.delete()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Database cleanup complete! "
                        f"Deleted {deleted_embs} old embeddings and {deleted_objs} virtual schema objects."
                    )
                )
        elif dry_run:
            self.stdout.write(self.style.NOTICE("[Dry-run] No database changes or cleanup performed."))

        self.stdout.write(self.style.SUCCESS("All tasks finished!"))
