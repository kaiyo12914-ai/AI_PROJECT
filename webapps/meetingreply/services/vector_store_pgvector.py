from __future__ import annotations

from pgvector.django import CosineDistance

from webapps.meetingreply.models import MeetingRecordEmbedding


def similarity_search(query_embedding: list[float], top_k: int) -> list[dict]:
    rows = (
        MeetingRecordEmbedding.objects.filter(
            embedding__isnull=False,
            embedding_dimension=len(query_embedding),
        )
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance", "-source_updated_at")[: max(1, int(top_k))]
    )
    result: list[dict] = []
    for row in rows:
        result.append(
            {
                "id": row.doc_id,
                "doc_id": row.doc_id,
                "title": row.title,
                "text": row.source_text,
                "dist": float(row.distance),
                "meta": {
                    "case_id": row.case_id,
                    "item_no": row.item_no,
                    "case_name": row.case_name,
                    "title": row.title,
                    "directive": row.directive,
                    "status": row.status,
                    "dept": row.dept_name,
                    "dept_name": row.dept_name,
                    "dept_code": row.dept_code,
                    "updated_at": row.source_updated_at.isoformat() if row.source_updated_at else "",
                    "embedding_model": row.embedding_model,
                },
            }
        )
    return result
