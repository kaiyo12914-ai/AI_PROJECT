from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from django.db import transaction

from webapps.database.db_factory import db_connect
from webapps.meetingreply.models import MeetingRecordEmbedding
from webapps.meetingreply.services.embedding_service import (
    embed_texts,
    embedding_enabled,
    embedding_model_name,
    expected_dimension,
)


@dataclass
class SourceRecord:
    doc_id: str
    case_id: str
    item_no: str
    case_name: str
    title: str
    directive: str
    status: str
    dept_name: str
    dept_code: str
    source_updated_at: date | None

    @property
    def source_text(self) -> str:
        return (
            f"會議名稱：{self.case_name}\n"
            f"標題：{self.title}\n"
            f"指裁示內容：{self.directive}\n"
            f"辦理情形/擬答：{self.status}\n"
            f"主辦單位：{self.dept_name}\n"
            f"案號：{self.case_id}\n"
            f"項次：{self.item_no}"
        ).strip()

    @property
    def checksum(self) -> str:
        payload = "|||".join(
            [
                self.doc_id,
                self.case_id,
                self.item_no,
                self.case_name,
                self.title,
                self.directive,
                self.status,
                self.dept_name,
                self.dept_code,
                self.source_updated_at.isoformat() if self.source_updated_at else "",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_source_records(limit: int = 0) -> list[SourceRecord]:
    conn = db_connect("postgresql")
    cur = conn.cursor()
    sql = (
        "SELECT doc_id, case_id, item_no, case_name, title, directive, status, dept_name, dept_code, updated_at "
        "FROM public.meeting_records "
        "ORDER BY updated_at DESC NULLS LAST, doc_id ASC"
    )
    params = ()
    if limit > 0:
        sql += " LIMIT %s"
        params = (int(limit),)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        SourceRecord(
            doc_id=str(row[0] or "").strip(),
            case_id=str(row[1] or "").strip(),
            item_no=str(row[2] or "").strip(),
            case_name=str(row[3] or "").strip(),
            title=str(row[4] or "").strip(),
            directive=str(row[5] or "").strip(),
            status=str(row[6] or "").strip(),
            dept_name=str(row[7] or "").strip(),
            dept_code=str(row[8] or "").strip(),
            source_updated_at=row[9],
        )
        for row in rows
        if str(row[0] or "").strip()
    ]


def rebuild_record_embeddings(*, limit: int = 0, delete_missing: bool = False) -> dict[str, int]:
    records = fetch_source_records(limit=limit)
    existing = {
        item.doc_id: item
        for item in MeetingRecordEmbedding.objects.filter(doc_id__in=[r.doc_id for r in records])
    }

    pending_records: list[SourceRecord] = []
    for record in records:
        current = existing.get(record.doc_id)
        if current and current.record_checksum == record.checksum and current.embedding is not None:
            continue
        pending_records.append(record)

    model_name = embedding_model_name() if embedding_enabled() else ""
    dim = expected_dimension()

    to_upsert: list[MeetingRecordEmbedding] = []
    batch_size = 32
    for start in range(0, len(pending_records), batch_size):
        batch = pending_records[start : start + batch_size]
        embeddings = embed_texts([r.source_text for r in batch]) if embedding_enabled() else []
        for index, record in enumerate(batch):
            vector = embeddings[index] if embedding_enabled() else None
            to_upsert.append(
                MeetingRecordEmbedding(
                    doc_id=record.doc_id,
                    case_id=record.case_id,
                    item_no=record.item_no,
                    case_name=record.case_name,
                    title=record.title,
                    directive=record.directive,
                    status=record.status,
                    dept_name=record.dept_name,
                    dept_code=record.dept_code,
                    source_text=record.source_text,
                    record_checksum=record.checksum,
                    embedding=vector,
                    embedding_model=model_name,
                    embedding_dimension=(len(vector) if vector else dim),
                    source_updated_at=record.source_updated_at,
                )
            )

    with transaction.atomic():
        if to_upsert:
            MeetingRecordEmbedding.objects.bulk_create(
                to_upsert,
                update_conflicts=True,
                unique_fields=["doc_id"],
                update_fields=[
                    "case_id",
                    "item_no",
                    "case_name",
                    "title",
                    "directive",
                    "status",
                    "dept_name",
                    "dept_code",
                    "source_text",
                    "record_checksum",
                    "embedding",
                    "embedding_model",
                    "embedding_dimension",
                    "source_updated_at",
                    "synced_at",
                ],
            )
        deleted = 0
        if delete_missing and limit <= 0:
            source_ids = {r.doc_id for r in records}
            deleted, _ = MeetingRecordEmbedding.objects.exclude(doc_id__in=source_ids).delete()

    return {
        "source_records": len(records),
        "updated_records": len(to_upsert),
        "deleted_records": deleted,
    }
