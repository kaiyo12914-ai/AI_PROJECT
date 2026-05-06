from __future__ import annotations

import time
from typing import Any, Dict, List

from webapps.projectnotes.models import Project, Conversation as PNConversation, Message as PNMessage
from webapps.projectnotes.views import _get_embedding, _query_tokens, _looks_noisy_content, _keyword_score, _query_match_score, _content_quality_score
from webapps.projectnotes.retrieval_policy import build_sparse_terms, is_definition_query, generic_source_penalty, definition_chunk_boost
from webapps.projectnotes.models import DocumentChunk
from django.db.models import Q
from pgvector.django import L2Distance
from webapps.projectnotes.context_builder import ProjectNotesContextBuilder, build_citation_tail
from webapps.projectnotes.query_rewrite import rewrite_query_for_retrieval

def query_projectnotes_rag(
    project_id: int,
    query: str,
    history_messages: List[Dict[str, Any]],
    model_type: str,
    temperature: float,
    timeout_sec: int,
    system_prompt: str,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    retrieval_query = rewrite_query_for_retrieval(query)
    query_vector = _get_embedding(retrieval_query or query)

    qs = DocumentChunk.objects.filter(
        document_version__document__source__project_id=project_id
    ).select_related("document_version__document__source")

    tokens = _query_tokens(retrieval_query or query)
    top_chunks_dense = list(qs.annotate(distance=L2Distance("embedding", query_vector)).order_by("distance")[:40])
    sparse_terms = build_sparse_terms(tokens, max_terms=6)
    top_chunks_sparse: List[DocumentChunk] = []
    if sparse_terms:
        sparse_q = Q()
        for term in sparse_terms:
            sparse_q |= Q(content__icontains=term)
        top_chunks_sparse = list(qs.filter(sparse_q).order_by("id")[:40])

    top_chunks: List[DocumentChunk] = []
    seen_chunk_ids = set()
    for c in top_chunks_dense + top_chunks_sparse:
        cid = int(getattr(c, "id", 0) or 0)
        if cid <= 0 or cid in seen_chunk_ids:
            continue
        seen_chunk_ids.add(cid)
        top_chunks.append(c)
        if len(top_chunks) >= 60:
            break

    def_query = is_definition_query(retrieval_query or query)
    ranked: List[Dict[str, Any]] = []
    max_kscore = 0.0
    for c in top_chunks:
        content = getattr(c, "content", "") or ""
        if not content:
            continue
        noisy = _looks_noisy_content(content)
        kscore = _keyword_score(tokens, content)
        source_title = getattr(c.document_version.document, "title", "") or ""
        match_score = _query_match_score(tokens, content)
        quality_score = _content_quality_score(content)
        generic_penalty = generic_source_penalty(query, source_title, content)
        def_boost = definition_chunk_boost(content) if def_query else 0.0
        if kscore > max_kscore:
            max_kscore = kscore
        score = (kscore * 1.6) + (match_score * 1.2) + (quality_score * 0.6)
        score += (0.20 if not noisy else -0.35)
        score += def_boost
        score -= generic_penalty
        ranked.append(
            {
                "score": score,
                "chunk": c,
                "excerpt": content,
                "source_title": source_title,
                "noisy": noisy,
                "kscore": kscore,
                "match_score": match_score,
                "quality_score": quality_score,
                "generic_penalty": generic_penalty,
            }
        )

    from webapps.projectnotes.retrieval_policy import rerank_candidates
    final_candidates = rerank_candidates(query, ranked, top_k=5)

    citations = []
    for idx, item in enumerate(final_candidates, start=1):
        c = item["chunk"]
        title = item["source_title"] or f"source_{c.document_version.document.source_id}"
        src_path = getattr(c.document_version.document, "path", "") or ""
        is_http = src_path.startswith("http://") or src_path.startswith("https://")
        citations.append(
            {
                "ref": f"C{idx}",
                "source_id": c.document_version.document.source_id,
                "source_title": title,
                "chunk_index": c.chunk_index,
                "confidence": max(0.5, min(0.95, item.get("rerank_score", 0.0))),
                "source_url": src_path if is_http else "",
                "excerpt": item["excerpt"],
            }
        )

    history_msgs = []
    for m in history_messages:
        history_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    builder = ProjectNotesContextBuilder(query, citations, history_msgs)
    llm_payload = builder.synthesize_answer("")
    llm_answer = llm_payload.get("answer", "")
    
    if not llm_answer:
        llm_answer = "無法從知識庫中找到相關資訊來回答您的問題。"

    citation_tail = build_citation_tail(citations)
    if citation_tail and citations:
        llm_answer += "\n\n" + citation_tail

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "answer": llm_answer,
        "latency_ms": latency_ms,
        "citations": citations
    }
