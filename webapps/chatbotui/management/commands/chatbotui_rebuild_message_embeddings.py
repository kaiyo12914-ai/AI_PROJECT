from __future__ import annotations

from typing import Any, Iterable, List

from django.core.management.base import BaseCommand

from webapps.chatbotui.repository import ChatbotUIRepository
from webapps.chatbotui.service import ChatbotUIService, safe_text


class Command(BaseCommand):
    help = "Rebuild chatbotui_message_embedding from existing chatbotui_message rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--conversation-id",
            dest="conversation_id",
            default="",
            help="Only rebuild one conversation id. Default: all active conversations.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum messages to process (0 means no limit).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Batch size per DB query. Default: 200.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only count rows, do not write embeddings.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        repo = ChatbotUIRepository()
        svc = ChatbotUIService(repo)
        svc.ensure_schema()

        conversation_id = safe_text(options.get("conversation_id"))
        limit = int(options.get("limit") or 0)
        batch_size = int(options.get("batch_size") or 200)
        dry_run = bool(options.get("dry_run"))

        if batch_size < 1:
            batch_size = 1
        if batch_size > 2000:
            batch_size = 2000

        conv_ids = self._resolve_conversation_ids(repo, conversation_id)
        if not conv_ids:
            self.stdout.write("No conversations found.")
            return

        self.stdout.write(
            f"Start rebuilding embeddings: conversations={len(conv_ids)} "
            f"batch_size={batch_size} limit={limit or 'ALL'} dry_run={dry_run}"
        )

        processed = 0
        built = 0
        skipped = 0

        for cid in conv_ids:
            offset = 0
            while True:
                rows = repo.query_all(
                    """
                    SELECT m.id, m.role, m.content
                    FROM chatbotui_message m
                    LEFT JOIN chatbotui_message_embedding e ON e.message_id = m.id
                    WHERE m.conversation_id = %s
                      AND e.message_id IS NULL
                    ORDER BY m.id ASC
                    LIMIT %s OFFSET %s
                    """,
                    [cid, batch_size, offset],
                    profile=repo.profile,
                )
                if not rows:
                    break

                for row in rows:
                    mid, role, content = self._parse_message_row(row)
                    if mid <= 0 or not content:
                        skipped += 1
                        continue
                    processed += 1
                    if not dry_run:
                        svc._store_message_embedding(cid, mid, role, content)
                        built += 1
                    if limit > 0 and processed >= limit:
                        self.stdout.write(
                            f"Reached limit={limit}. processed={processed} built={built} skipped={skipped}"
                        )
                        return

                offset += len(rows)

        self.stdout.write(f"Done. processed={processed} built={built} skipped={skipped} dry_run={dry_run}")

    @staticmethod
    def _resolve_conversation_ids(repo: ChatbotUIRepository, conversation_id: str) -> List[str]:
        if conversation_id:
            return [conversation_id]
        rows = repo.query_all(
            """
            SELECT id
            FROM chatbotui_conversation
            WHERE is_archived = FALSE
            ORDER BY updated_at DESC, id DESC
            """,
            profile=repo.profile,
        )
        out: List[str] = []
        for row in rows:
            if isinstance(row, dict):
                cid = safe_text(row.get("id"))
            elif isinstance(row, (list, tuple)):
                cid = safe_text(row[0] if row else "")
            else:
                cid = safe_text(getattr(row, "id", ""))
            if cid:
                out.append(cid)
        return out

    @staticmethod
    def _parse_message_row(row: Any) -> tuple[int, str, str]:
        if isinstance(row, dict):
            mid = int(row.get("id") or 0)
            role = safe_text(row.get("role"))
            content = safe_text(row.get("content"))
            return mid, role, content
        if isinstance(row, (list, tuple)):
            mid = int(row[0] or 0) if len(row) > 0 else 0
            role = safe_text(row[1] if len(row) > 1 else "")
            content = safe_text(row[2] if len(row) > 2 else "")
            return mid, role, content
        return (
            int(getattr(row, "id", 0) or 0),
            safe_text(getattr(row, "role", "")),
            safe_text(getattr(row, "content", "")),
        )


# 全量補建（所有未建 embedding 的訊息）
#H:\AI\AI_TOOLS\venv\Scripts\python.exe H:\AI\AI_TOOLS\manage.py chatbotui_rebuild_message_embeddings

