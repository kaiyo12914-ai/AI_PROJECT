from django.core.management.base import BaseCommand

from webapps.meetingreply.services.record_embedding_sync import rebuild_record_embeddings


class Command(BaseCommand):
    help = "Rebuild meetingreply record embeddings from public.meeting_records."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Only process the latest N source records.")
        parser.add_argument(
            "--delete-missing",
            action="store_true",
            help="Delete local embedding rows that no longer exist in public.meeting_records.",
        )

    def handle(self, *args, **options):
        summary = rebuild_record_embeddings(
            limit=max(0, int(options["limit"])),
            delete_missing=bool(options["delete_missing"]),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"source_records={summary['source_records']}, "
                f"updated_records={summary['updated_records']}, "
                f"deleted_records={summary['deleted_records']}"
            )
        )

