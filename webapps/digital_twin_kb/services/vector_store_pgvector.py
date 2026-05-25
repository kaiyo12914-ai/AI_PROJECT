from django.db import connection
import math

from webapps.digital_twin_kb.models import DocumentChunk


def _sanitize_embedding(values: list[float]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            f = float(v)
        except Exception:
            f = 0.0
        if not math.isfinite(f):
            f = 0.0
        out.append(f)
    return out


def similarity_search(query_embedding: list[float], top_k: int, user_security_level: int, filters: dict | None = None):
    filters = filters or {}
    safe_embedding = _sanitize_embedding(query_embedding)
    params = {
        "embedding": safe_embedding,
        "top_k": int(top_k),
        "security_level": int(user_security_level),
    }
    where = ["security_level <= %(security_level)s"]
    for key in ["twin_level", "isa95_level", "system_type", "topic"]:
        value = filters.get(key)
        if value:
            where.append(f"{key} = %({key})s")
            params[key] = value

    table_name = connection.ops.quote_name(DocumentChunk._meta.db_table)
    sql = f"""
        SELECT
            chunk_id,
            document_id,
            content,
            page_number,
            section_title,
            twin_level,
            isa95_level,
            system_type,
            topic,
            security_level,
            CASE
                WHEN (1 - (embedding <=> %(embedding)s::vector)) = 'NaN'::float8 THEN 0.0
                ELSE (1 - (embedding <=> %(embedding)s::vector))
            END AS similarity
        FROM {table_name}
        WHERE {" AND ".join(where)}
        ORDER BY embedding <=> %(embedding)s::vector
        LIMIT %(top_k)s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def save_chunk_embedding(chunk: DocumentChunk, embedding: list[float]):
    chunk.embedding = embedding
    chunk.save(update_fields=["embedding"])
