from django.db import connection

from webapps.digital_twin_kb.models import DocumentChunk


def similarity_search(query_embedding: list[float], top_k: int, user_security_level: int, filters: dict | None = None):
    filters = filters or {}
    params = {
        "embedding": query_embedding,
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
            1 - (embedding <=> %(embedding)s::vector) AS similarity
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
