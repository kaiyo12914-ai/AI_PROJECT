from django.core.management.base import BaseCommand

from webapps.digital_twin_kb.models import DocumentChunk
from webapps.digital_twin_kb.services.embedding_service import embed_text


class Command(BaseCommand):
    help = "Rebuild embeddings for digital_twin_kb DocumentChunk records."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100, help="Batch size for bulk_update.")
        parser.add_argument("--limit", type=int, default=0, help="Limit chunks to rebuild (0 = all).")
        parser.add_argument("--document-id", type=int, default=0, help="Only rebuild chunks for a document_id.")
        parser.add_argument("--dry-run", action="store_true", help="Show target count without updating.")

    def handle(self, *args, **options):
        batch_size = max(1, int(options["batch_size"]))
        limit = max(0, int(options["limit"]))
        document_id = max(0, int(options["document_id"]))
        dry_run = bool(options["dry_run"])

        qs = DocumentChunk.objects.all().order_by("chunk_id")
        if document_id > 0:
            qs = qs.filter(document_id=document_id)
        if limit > 0:
            qs = qs[:limit]

        chunks = list(qs)
        total = len(chunks)
        self.stdout.write(f"Target chunks: {total}")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only. No data updated."))
            return

        updated = 0
        failed = 0
        pending = []

        for idx, chunk in enumerate(chunks, start=1):
            try:
                chunk.embedding = embed_text(chunk.content or "")
                pending.append(chunk)
            except Exception as exc:
                failed += 1
                self.stderr.write(f"[FAILED] chunk_id={chunk.chunk_id} error={exc}")

            if len(pending) >= batch_size:
                DocumentChunk.objects.bulk_update(pending, ["embedding"])
                updated += len(pending)
                self.stdout.write(f"Updated {updated}/{total}")
                pending = []

            if idx % 500 == 0:
                self.stdout.write(f"Progress {idx}/{total}")

        if pending:
            DocumentChunk.objects.bulk_update(pending, ["embedding"])
            updated += len(pending)

        self.stdout.write(self.style.SUCCESS(f"Done. updated={updated}, failed={failed}, total={total}"))
