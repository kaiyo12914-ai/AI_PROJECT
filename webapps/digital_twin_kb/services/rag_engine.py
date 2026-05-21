from django.conf import settings

from webapps.digital_twin_kb.models import Document, QALog
from webapps.digital_twin_kb.services.embedding_service import embed_text
from webapps.digital_twin_kb.services.vector_store_pgvector import similarity_search

from .llm_service import NO_DATA_ANSWER, generate_answer


def ask(question: str, asker_type: str, asker_id: str, top_k: int | None, user_security_level: int, filters: dict):
    query_embedding = embed_text(question)
    rows = similarity_search(query_embedding, top_k or settings.DIGITAL_TWIN_KB_TOP_K, user_security_level, filters)
    context = _build_context(rows)
    answer = generate_answer(question, context)
    if not rows:
        answer = NO_DATA_ANSWER
    sources = _build_sources(rows)
    log = QALog.objects.create(
        asker_type=asker_type,
        asker_id=asker_id,
        user_question=question,
        filters=filters or {},
        retrieved_chunks=rows,
        answer=answer,
        cited_sources=sources,
    )
    return {
        "query_id": log.query_id,
        "question": question,
        "answer": answer,
        "sources": sources,
        "retrieved_chunks": rows,
        "similarity_scores": [r["similarity"] for r in rows],
    }


def _build_context(rows: list[dict]) -> str:
    docs = Document.objects.in_bulk([r["document_id"] for r in rows], field_name="document_id")
    parts = []
    for row in rows:
        doc = docs.get(row["document_id"])
        file_name = doc.file_name if doc else f"document:{row['document_id']}"
        parts.append(
            f"[{file_name} chunk:{row['chunk_id']} similarity:{row['similarity']:.4f}]\n"
            f"twin_level={row['twin_level']} isa95_level={row['isa95_level']} system_type={row['system_type']}\n"
            f"{row['content']}"
        )
    return "\n\n---\n\n".join(parts)


def _build_sources(rows: list[dict]) -> list[dict]:
    docs = Document.objects.in_bulk([r["document_id"] for r in rows], field_name="document_id")
    result = []
    for row in rows:
        doc = docs.get(row["document_id"])
        result.append({
            "file_name": doc.file_name if doc else "",
            "page_number": row["page_number"],
            "chunk_id": row["chunk_id"],
            "paragraph": row["section_title"],
            "twin_level": row["twin_level"],
            "isa95_level": row["isa95_level"],
            "system_type": row["system_type"],
            "similarity": row["similarity"],
        })
    return result
