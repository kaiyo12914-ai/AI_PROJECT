from __future__ import annotations

from django.conf import settings
from django.db import models
from pgvector.django import VectorField


def _embedding_dimensions() -> int:
    return int(getattr(settings, "GLOBAL_EMBEDDING_DIMENSION", 1024) or 1024)


class MeetingRecordEmbedding(models.Model):
    doc_id = models.CharField(max_length=128, primary_key=True)
    case_id = models.CharField(max_length=64, blank=True)
    item_no = models.CharField(max_length=64, blank=True)
    case_name = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255, blank=True)
    directive = models.TextField(blank=True)
    status = models.TextField(blank=True)
    dept_name = models.CharField(max_length=128, blank=True)
    dept_code = models.CharField(max_length=64, blank=True)
    source_text = models.TextField()
    record_checksum = models.CharField(max_length=64, db_index=True)
    embedding = VectorField(dimensions=_embedding_dimensions(), null=True, blank=True)
    embedding_model = models.CharField(max_length=160, blank=True, default="")
    embedding_dimension = models.PositiveIntegerField(default=_embedding_dimensions)
    source_updated_at = models.DateField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meetingreply_record_embedding"
        indexes = [
            models.Index(fields=["case_id"]),
            models.Index(fields=["item_no"]),
            models.Index(fields=["dept_code"]),
            models.Index(fields=["source_updated_at"]),
        ]

