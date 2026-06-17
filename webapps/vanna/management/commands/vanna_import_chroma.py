from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from webapps.vanna.models import (
    DataSource,
    ExampleEmbedding,
    SchemaEmbedding,
    SchemaObject,
    TrainingExample,
    VannaTrainingSync,
    TrainingDocumentation,
    DocumentationEmbedding,
)


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_collection_items(path: Path) -> dict[str, list[dict[str, Any]]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          c.name AS collection_name,
          e.id AS row_id,
          e.embedding_id,
          m.key,
          m.string_value,
          m.int_value,
          m.float_value,
          m.bool_value
        FROM embeddings e
        JOIN segments s ON s.id = e.segment_id
        JOIN collections c ON c.id = s.collection
        LEFT JOIN embedding_metadata m ON m.id = e.id
        WHERE s.scope = 'METADATA'
        ORDER BY c.name, e.id, m.key
        """
    )
    grouped: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in cur.fetchall():
        key = (row["collection_name"], int(row["row_id"]), row["embedding_id"])
        item = grouped.setdefault(
            key,
            {
                "collection": row["collection_name"],
                "row_id": int(row["row_id"]),
                "embedding_id": row["embedding_id"],
                "metadata": {},
            },
        )
        meta_key = row["key"]
        if not meta_key:
            continue
        value = row["string_value"]
        if value is None:
            value = row["int_value"]
        if value is None:
            value = row["float_value"]
        if value is None:
            value = row["bool_value"]
        item["metadata"][meta_key] = value

    conn.close()
    out: dict[str, list[dict[str, Any]]] = {"ddl": [], "documentation": [], "sql": []}
    for item in grouped.values():
        collection = item["collection"]
        if collection in out:
            out[collection].append(item)
    return out


def _parse_ddl_name(ddl_text: str) -> tuple[str, str, str]:
    text = ddl_text or ""
    patterns = [
        (r"(?is)\bCREATE\s+MATERIALIZED\s+VIEW\s+([\"A-Za-z0-9_.$@]+)", "materialized_view"),
        (r"(?is)\bCREATE\s+VIEW\s+([\"A-Za-z0-9_.$@]+)", "view"),
        (r"(?is)\bCREATE\s+TABLE\s+([\"A-Za-z0-9_.$@]+)", "table"),
    ]
    for pattern, object_type in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        raw_name = match.group(1).strip().strip('"')
        raw_name = raw_name.split("@", 1)[0]
        if "." in raw_name:
            schema_name, object_name = raw_name.rsplit(".", 1)
        else:
            schema_name, object_name = "LEGACY", raw_name
        return schema_name.strip('"').upper(), object_name.strip('"').upper(), object_type
    return "LEGACY", f"UNKNOWN_{_sha256(text)[:12].upper()}", "table"


def _extract_json_doc(doc: str) -> dict[str, Any] | None:
    try:
        data = json.loads(doc)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


class Command(BaseCommand):
    help = "Import legacy Vanna Chroma SQLite training data into NL2SQL PostgreSQL tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(Path(__file__).resolve().parents[4] / "chroma 1.sqlite3"),
            help="Path to legacy Chroma sqlite3 file.",
        )
        parser.add_argument("--data-source", default="legacy_vanna_chroma")
        parser.add_argument("--name", default="Legacy Vanna Chroma")
        parser.add_argument("--clear", action="store_true", help="Clear this imported data source before import.")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Chroma sqlite file not found: {path}")

        data_source, _ = DataSource.objects.update_or_create(
            code=options["data_source"],
            defaults={
                "name": options["name"],
                "db_type": "oracle",
                "db_profile": "ERP_MPC",
                "default_schema": "LEGACY",
                "enabled": True,
                "execute_enabled": False,
                "config_json": {"source": str(path), "source_type": "legacy_vanna_chroma"},
            },
        )

        if options["clear"]:
            data_source.schema_objects.all().delete()
            data_source.training_examples.all().delete()
            data_source.vanna_training_syncs.all().delete()
            data_source.example_embeddings.all().delete()
            TrainingDocumentation.objects.filter(data_source=data_source).delete()

        collections = _parse_collection_items(path)

        ddl_created = 0
        ddl_updated = 0
        doc_created = 0
        doc_skipped = 0
        sql_created = 0
        sql_skipped = 0

        for item in collections["ddl"]:
            ddl_text = _safe_text(item["metadata"].get("chroma:document"))
            if not ddl_text:
                continue
            schema_name, object_name, object_type = _parse_ddl_name(ddl_text)
            schema_obj, created = SchemaObject.objects.update_or_create(
                data_source=data_source,
                schema_name=schema_name,
                object_name=object_name,
                defaults={
                    "object_type": object_type,
                    "description": f"Imported from legacy Vanna Chroma row {item['row_id']}",
                    "columns_json": [],
                    "ddl_text": ddl_text,
                    "is_enabled": True,
                },
            )
            content_hash = _sha256(ddl_text)
            SchemaEmbedding.objects.update_or_create(
                schema_object=schema_obj,
                chunk_type="ddl",
                content_hash=content_hash,
                defaults={
                    "chunk_text": ddl_text,
                    "embedding": None,
                    "embedding_model": "legacy_chroma_384_not_imported",
                    "embedding_dimension": 384,
                },
            )
            VannaTrainingSync.objects.update_or_create(
                data_source=data_source,
                sync_type="ddl",
                source_object_id=schema_obj.id,
                content_hash=content_hash,
                defaults={
                    "vanna_training_id": item["embedding_id"],
                    "sync_status": "synced",
                    "error_message": "",
                },
            )
            ddl_created += 1 if created else 0
            ddl_updated += 0 if created else 1

        for item in collections["documentation"]:
            doc_content = _safe_text(item["metadata"].get("chroma:document"))
            if not doc_content:
                doc_skipped += 1
                continue
            topic = _safe_text(item["metadata"].get("Topic"))
            content = f"{topic}\n{doc_content}".strip() if topic and topic not in doc_content[:20] else doc_content
            
            # 解析為 title 與 documentation
            lines = content.split("\n", 1)
            if len(lines) == 2 and len(lines[0]) < 100:
                title = lines[0].strip()
                doc_text = lines[1].strip()
            else:
                title = ""
                doc_text = content.strip()

            doc_obj, created = TrainingDocumentation.objects.update_or_create(
                data_source=data_source,
                title=title,
                documentation=doc_text,
                defaults={
                    "created_by": "legacy_vanna_chroma_import",
                },
            )
            content_hash = _sha256(content)
            DocumentationEmbedding.objects.update_or_create(
                training_documentation=doc_obj,
                data_source=data_source,
                content_hash=content_hash,
                defaults={
                    "title": title,
                    "documentation_text": doc_text,
                    "embedding": None,
                    "embedding_model": "legacy_chroma_384_not_imported",
                    "embedding_dimension": 384,
                },
            )
            VannaTrainingSync.objects.update_or_create(
                data_source=data_source,
                sync_type="documentation",
                source_object_id=doc_obj.id,
                content_hash=content_hash,
                defaults={
                    "vanna_training_id": item["embedding_id"],
                    "sync_status": "synced",
                    "error_message": "",
                },
            )
            doc_created += 1 if created else 0
            doc_skipped += 0 if created else 1

        for item in collections["sql"]:
            doc = _safe_text(item["metadata"].get("chroma:document"))
            payload = _extract_json_doc(doc)
            if not payload:
                sql_skipped += 1
                continue
            question = _safe_text(payload.get("question"))
            sql_text = _safe_text(payload.get("sql"))
            if not question or not sql_text:
                sql_skipped += 1
                continue
            tags = []
            topic = _safe_text(item["metadata"].get("Topic"))
            if topic:
                tags.append(topic)
            existing = TrainingExample.objects.filter(
                data_source=data_source,
                question=question,
                sql_text=sql_text,
            ).first()
            if existing:
                training_example = existing
                sql_skipped += 1
            else:
                training_example = TrainingExample.objects.create(
                    data_source=data_source,
                    question=question,
                    sql_text=sql_text,
                    dialect="oracle",
                    tags_json=tags,
                    review_status="approved",
                    created_by="legacy_vanna_chroma_import",
                )
                sql_created += 1

            content_hash = _sha256(f"{question}\n{sql_text}")
            ExampleEmbedding.objects.update_or_create(
                training_example=training_example,
                data_source=data_source,
                content_hash=content_hash,
                defaults={
                    "question_text": question,
                    "sql_text": sql_text,
                    "embedding": None,
                    "embedding_model": "legacy_chroma_384_not_imported",
                    "embedding_dimension": 384,
                },
            )
            VannaTrainingSync.objects.update_or_create(
                data_source=data_source,
                sync_type="example",
                source_object_id=training_example.id,
                content_hash=content_hash,
                defaults={
                    "vanna_training_id": item["embedding_id"],
                    "sync_status": "synced",
                    "error_message": "",
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                json.dumps(
                    {
                        "data_source": data_source.code,
                        "ddl_created": ddl_created,
                        "ddl_updated": ddl_updated,
                        "documentation_created": doc_created,
                        "documentation_skipped": doc_skipped,
                        "sql_examples_created": sql_created,
                        "sql_examples_skipped": sql_skipped,
                    },
                    ensure_ascii=False,
                )
            )
        )


# ./venv/Scripts/python.exe manage.py vanna_import_chroma --path "./chroma 1.sqlite3" --clear
