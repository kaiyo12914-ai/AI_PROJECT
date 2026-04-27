from __future__ import annotations

import re
from typing import Any, Dict, List


def _safe_text(v: object) -> str:
    return "" if v is None else str(v).strip()


def is_definition_query(query: str) -> bool:
    q = _safe_text(query).lower()
    if not q:
        return False
    hints = (
        "何謂", "是什麼", "定義", "意義", "指的是", "解釋",
        "what is", "define", "definition", "meaning",
    )
    return any(h in q for h in hints)


def definition_chunk_boost(content: str) -> float:
    t = _safe_text(content).lower()
    if not t:
        return 0.0
    hints = ("係指", "是指", "定義", "意指", "指稱", "means", "is defined as", "refers to")
    hit = sum(1 for h in hints if h in t)
    return min(0.30, hit * 0.08)


def generic_source_penalty(query: str, source_title: str, content: str) -> float:
    q = _safe_text(query).lower()
    title = _safe_text(source_title).lower()
    text = _safe_text(content).lower()
    if not title and not text:
        return 0.0

    generic_hints = (
        "通用條款", "一般條款", "契約範本", "契約通則", "common terms",
        "general terms", "standard terms", "template",
    )
    generic_hit = any(h in title for h in generic_hints)
    if not generic_hit:
        return 0.0

    query_allow = ("通用條款", "一般條款", "契約條款", "罰則", "履約", "驗收", "違約")
    if any(h in q for h in query_allow):
        return 0.0

    boilerplate_hits = sum(1 for h in ("本契約", "甲方", "乙方", "雙方", "履約", "違約", "賠償") if h in text)
    return min(0.45, 0.18 + (boilerplate_hits * 0.04))


def build_sparse_terms(tokens: List[str], max_terms: int = 6) -> List[str]:
    """
    Select stable lexical terms for sparse recall.
    Prefer longer tokens and keep deterministic order after ranking.
    """
    if not tokens:
        return []
    uniq = []
    seen = set()
    for t in tokens:
        x = (t or "").strip().lower()
        if len(x) < 2:
            continue
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    uniq.sort(key=lambda s: (-len(s), s))
    return uniq[:max_terms]


def _core_query_term(query: str) -> str:
    q = _safe_text(query)
    if not q:
        return ""
    m = re.search(r"(?:何謂|是什麼|是什麽|定義|what is|define)\s*[:：]?\s*(.{1,60})$", q, flags=re.IGNORECASE)
    if m:
        return re.sub(r"[?？。!！]+$", "", m.group(1)).strip().lower()
    return ""


def rerank_candidates(query: str, ranked: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Rerank after hybrid recall with two goals:
    1) relevance alignment to query intent
    2) suppress single-source domination (diversity)
    """
    if not ranked:
        return []

    q = _safe_text(query).lower()
    core = _core_query_term(query)

    # stage-1: compute relevance-focused rerank score
    stage1: List[Dict[str, Any]] = []
    for item in ranked:
        base = float(item.get("score") or 0.0)
        excerpt = _safe_text(item.get("excerpt")).lower()
        title = _safe_text(item.get("source_title")).lower()
        kscore = float(item.get("kscore") or 0.0)
        match = float(item.get("match_score") or 0.0)
        quality = float(item.get("quality_score") or 0.0)
        generic_penalty = float(item.get("generic_penalty") or 0.0)

        core_boost = 0.0
        if core and (core in excerpt or core in title):
            core_boost += 0.18
        if is_definition_query(q) and any(h in excerpt for h in ("係指", "是指", "定義", "refers to", "means")):
            core_boost += 0.10

        rerank_score = (base * 0.55) + (kscore * 0.20) + (match * 0.20) + (quality * 0.05)
        rerank_score += core_boost
        rerank_score -= (generic_penalty * 0.35)

        x = dict(item)
        x["rerank_score"] = rerank_score
        stage1.append(x)

    stage1.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)

    # stage-2: diversify by source title (MMR-like lightweight pass)
    picked: List[Dict[str, Any]] = []
    source_count: Dict[str, int] = {}
    for item in stage1:
        title = _safe_text(item.get("source_title"))
        used = source_count.get(title, 0)
        score = float(item.get("rerank_score") or 0.0) - (0.08 * used)
        item2 = dict(item)
        item2["rerank_score"] = score
        picked.append(item2)
        source_count[title] = used + 1
        if len(picked) >= max(top_k * 3, 12):
            break

    picked.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)
    return picked[:top_k]
