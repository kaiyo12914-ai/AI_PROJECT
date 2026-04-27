from __future__ import annotations

from typing import Dict, List, Set, Tuple

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Check projectnotes table indexes and constraints."

    def handle(self, *args, **options):
        expected: Dict[str, List[Tuple[str, ...]]] = {
            "projectnotes_source": [
                ("project_id", "is_enabled"),
                ("project_id", "title"),
            ],
            "projectnotes_chunk": [
                ("source_id", "chunk_index"),
            ],
            "projectnotes_conversation": [
                ("project_id", "updated_at"),
            ],
            "projectnotes_turn": [
                ("conversation_id", "created_at"),
            ],
        }

        with connection.cursor() as cursor:
            introspection = connection.introspection
            tables = set(introspection.table_names(cursor))

            for table, needed in expected.items():
                self.stdout.write(self.style.HTTP_INFO(f"\n[{table}]"))
                if table not in tables:
                    self.stdout.write(self.style.ERROR("  table missing"))
                    continue

                indexed_cols: Set[Tuple[str, ...]] = set()
                if connection.vendor == "sqlite":
                    cursor.execute(f"PRAGMA index_list('{table}')")
                    rows = cursor.fetchall()
                    for r in rows:
                        name = r[1]
                        is_unique = bool(r[2])
                        cursor.execute(f"PRAGMA index_info('{name}')")
                        info = cursor.fetchall()
                        cols = tuple((x[2] or "").replace(" DESC", "").strip() for x in info if x[2])
                        if not cols:
                            continue
                        indexed_cols.add(cols)
                        kind = "UNIQUE" if is_unique else "INDEX"
                        self.stdout.write(f"  - {name}: {kind} {cols}")
                else:
                    constraints = introspection.get_constraints(cursor, table)
                    for name, meta in constraints.items():
                        cols = tuple((c or "").replace(" DESC", "").strip() for c in (meta.get("columns") or []) if c)
                        if not cols:
                            continue
                        if meta.get("index") or meta.get("unique"):
                            indexed_cols.add(cols)
                            kind = "UNIQUE" if meta.get("unique") else "INDEX"
                            self.stdout.write(f"  - {name}: {kind} {cols}")

                for cols in needed:
                    if cols in indexed_cols:
                        self.stdout.write(self.style.SUCCESS(f"  OK: {cols}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"  MISSING: {cols}"))

        self.stdout.write("\nDone.")
