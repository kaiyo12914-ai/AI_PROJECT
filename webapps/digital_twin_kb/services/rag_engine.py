from django.conf import settings
import re
import math

from webapps.digital_twin_kb.models import Document, QALog
from webapps.digital_twin_kb.services.embedding_service import embed_text
from webapps.digital_twin_kb.services.vector_store_pgvector import similarity_search

from .llm_service import NO_DATA_ANSWER, generate_answer


def ask(question: str, asker_type: str, asker_id: str, top_k: int | None, user_security_level: int, filters: dict):
    query_embedding = embed_text(question)
    rows = similarity_search(query_embedding, top_k or settings.DIGITAL_TWIN_KB_TOP_K, user_security_level, filters)
    rows = _sanitize_rows_for_json(rows)
    if rows:
        context = _build_context(rows)
        answer = generate_answer(question, context)
    else:
        from .llm_service import generate_general_answer
        answer = generate_general_answer(question)
        # ✅ 使用者要求：當觸發通用智慧回答時，自動將回答存回知識庫，並備註為「AI生成」以實現自進化知識庫
        _save_ai_answer_to_kb(question, answer)

    answer = _strip_noise_source_block(answer)
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
        "sources": [],
        "retrieved_chunks": [],
        "similarity_scores": [r["similarity"] for r in rows],
    }


def _safe_float(v) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    if not math.isfinite(f):
        return 0.0
    return f


def _sanitize_rows_for_json(rows: list[dict]) -> list[dict]:
    cleaned = []
    for row in rows:
        item = dict(row)
        item["similarity"] = _safe_float(item.get("similarity", 0.0))
        cleaned.append(item)
    return cleaned


def _strip_noise_source_block(answer: str) -> str:
    """
    Remove noisy citation blocks like:
    '依據來源 (5 個 Chunks)' and subsequent '#1 ...' list items.
    """
    if not answer:
        return answer

    # Remove section from '依據來源 (N 個 Chunks)' to the next blank-line section or end.
    cleaned = re.sub(
        r"(?:^|\n)\s*依據來源\s*\(\s*\d+\s*個\s*Chunks\s*\)\s*(?:\n|$)(?:[\s\S]*?)(?=(?:\n\s*\n\S)|\Z)",
        "\n",
        answer,
        flags=re.IGNORECASE,
    )

    # Also remove lines beginning with '#<n>' that often follow noisy source dumps.
    cleaned = re.sub(r"^\s*#\d+\s+.*(?:\n[^\n]*)?", "", cleaned, flags=re.MULTILINE)

    return cleaned.strip() or answer.strip()


def _save_ai_answer_to_kb(question: str, answer: str):
    """背景將 AI 通用智慧的高質量答案向量化並回存至知識庫中，備註標記為 AI 生成，供未來檢索"""
    if not answer or "查詢失敗" in answer or "未啟用通用 LLM" in answer or "尚無足夠資料" in answer:
        return
    
    try:
        from webapps.digital_twin_kb.models import Document, DocumentChunk
        from django.db.models import Max
        import logging
        logger = logging.getLogger("django")
        
        import hashlib
        # 計算此對話 Q&A 的 MD5 哈希作為唯一的 checksum，防止重覆儲存，且讓每次不同的 AI 解答在資產庫中顯示為獨立一列
        text_data = f"{question}|||{answer}"
        text_hash = hashlib.md5(text_data.encode("utf-8")).hexdigest()
        checksum = f"ai_gen_checksum_{text_hash}"
        display_name = question[:20].replace("\n", " ") + ("..." if len(question) > 20 else "")

        # 獲取或建立特殊的 AI 生成文檔
        ai_doc, created = Document.objects.get_or_create(
            checksum=checksum,
            defaults={
                "file_name": f"ai_gen_{text_hash[:8]}.txt",
                "original_file_name": f"AI解答: {display_name}",
                "file_type": "txt",
                "file_path": "ai_generated_kb",
                "file_size": len(answer),
                "source": "AI_GENERATED",
                "uploaded_by": "ai_agent",
                "uploaded_by_type": "ai_agent",
                "topic": "AI Generated",
                "security_level": 1,
            }
        )
        
        # 取得下一個 chunk_index
        max_idx = ai_doc.chunks.aggregate(Max("chunk_index"))["chunk_index__max"]
        chunk_index = (max_idx or 0) + 1
        
        # 組裝具有 "(備註：AI 生成)" 標記的內容，提升未來 RAG 檢索匹配度
        content = f"問題：{question}\n\n回答：(備註：AI 生成)\n{answer}"
        embedding = embed_text(content)
        
        DocumentChunk.objects.create(
            document=ai_doc,
            chunk_index=chunk_index,
            content=content,
            page_number=1,
            section_title="AI Generated Knowledge",
            twin_level="",
            isa95_level="",
            system_type="",
            topic="AI Generated",
            security_level=1,
            embedding=embedding,
            token_count=len(content) // 4,
        )
        # 更新 Document 檔案大小
        ai_doc.file_size = len(content)
        ai_doc.save()
        logger.info(f"[AI SELF-EVOLVING KB] Successfully saved AI generated chunk #{chunk_index} for query checksum {checksum[:12]}")
    except Exception as e:
        import logging
        logger = logging.getLogger("django")
        logger.error(f"[AI GENERATED KB SAVE ERROR] {str(e)}")


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
