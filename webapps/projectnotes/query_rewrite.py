from __future__ import annotations

import re
from typing import List


def _safe_text(v: object) -> str:
    return "" if v is None else str(v).strip()


def _dedup_keep_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        k = _safe_text(item)
        if not k:
            continue
        low = k.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(k)
    return out


def _extract_core_term(query: str) -> str:
    q = _safe_text(query)
    if not q:
        return ""

    m = re.search(r"(?:何謂|是什麼|是什麽|定義|what is|define)\s*[:：]?\s*(.{1,60})$", q, flags=re.IGNORECASE)
    if m:
        return re.sub(r"[?？。!！]+$", "", m.group(1)).strip()

    m2 = re.search(r"^(.{1,60}?)\s*(?:是什麼|是什麽)$", q)
    if m2:
        return re.sub(r"[?？。!！]+$", "", m2.group(1)).strip()

    return ""


def _is_definition_query(query: str) -> bool:
    q = _safe_text(query).lower()
    if not q:
        return False
    hints = ("何謂", "是什麼", "是什麽", "定義", "what is", "define", "definition")
    return any(h in q for h in hints)


def rewrite_query_for_retrieval(query: str) -> str:
    q = _safe_text(query)
    if not q:
        return ""

    # remove polite/opening fillers but keep core meaning
    cleaned = q
    for pat in (
        r"^請問[：: ]*",
        r"^請教[：: ]*",
        r"^想請問[：: ]*",
        r"^可否說明[：: ]*",
        r"^麻煩說明[：: ]*",
    ):
        cleaned = re.sub(pat, "", cleaned)

    core = _extract_core_term(cleaned)
    is_def = _is_definition_query(cleaned)

    synonyms_map = {
        "巨額採購": ["查核金額", "採購金額門檻", "採購法", "定義"],
        "限制性招標": ["招標方式", "採購法", "適用條件"],
        "最有利標": ["評選", "決標", "採購法"],
        "驗收": ["履約", "採購契約", "驗收程序"],
    }

    terms: List[str] = [cleaned]
    if core:
        terms.append(core)

    if is_def:
        terms.extend(["定義", "係指", "是指", "法規條文"])

    for key, exps in synonyms_map.items():
        if key in cleaned or (core and key in core):
            terms.extend(exps)

    # Keep concise query string for embedding + lexical scoring
    rewritten = " ".join(_dedup_keep_order(terms))
    rewritten = re.sub(r"\s+", " ", rewritten).strip()
    return rewritten[:240]