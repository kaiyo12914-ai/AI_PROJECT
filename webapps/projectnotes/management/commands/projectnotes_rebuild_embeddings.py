import logging
from django.core.management.base import BaseCommand
from webapps.projectnotes.models import DocumentChunk
from webapps.projectnotes.embedding_service import get_embedding

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Rebuild embeddings for ProjectNotes DocumentChunks using real LLM models"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=50, help="Batch size for updates")
        parser.add_argument("--limit", type=int, default=0, help="Limit number of chunks to process (0 = all)")
        parser.add_argument("--project-id", type=int, default=0, help="Only rebuild chunks for specific project_id")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        limit = options["limit"]
        project_id = options["project_id"]

        qs = DocumentChunk.objects.select_related("document_version__document")
        if project_id > 0:
            qs = qs.filter(document_version__document__source__project_id=project_id)
        
        # Order by id to ensure stable chunk processing
        qs = qs.order_by("id")
        
        if limit > 0:
            qs = qs[:limit]

        chunks_to_update = list(qs)
        total = len(chunks_to_update)
        self.stdout.write(f"Starting rebuild of {total} embeddings...")
        
        updated_count = 0
        current_batch = []

        for i, chunk in enumerate(chunks_to_update, 1):
            text = chunk.content
            try:
                emb = get_embedding(text)
                chunk.embedding = emb
                current_batch.append(chunk)
                
                if len(current_batch) >= batch_size:
                    DocumentChunk.objects.bulk_update(current_batch, ["embedding"])
                    updated_count += len(current_batch)
                    self.stdout.write(f"Updated {updated_count}/{total} chunks...")
                    current_batch = []
            except Exception as e:
                self.stderr.write(f"Failed to embed chunk {chunk.id}: {e}")
        
        if current_batch:
            DocumentChunk.objects.bulk_update(current_batch, ["embedding"])
            updated_count += len(current_batch)

        self.stdout.write(self.style.SUCCESS(f"Successfully rebuilt {updated_count} embeddings."))
