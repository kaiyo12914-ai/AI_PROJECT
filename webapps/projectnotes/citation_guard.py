from __future__ import annotations

import re
from typing import Dict, List


def _safe_text(v: object) -> str:
    return "" if v is None else str(v).strip()


def ensure_sentence_citations(answer: str, citations: List[Dict[str, object]]) -> str:
    text = _safe_text(answer)
    if not text or not citations:
        return text

    refs = []
    for c in citations:
        r = _safe_text(c.get("ref"))
        if not r:
            continue
        tag = r if r.startswith("[") else f"[{r}]"
        if tag not in refs:
            refs.append(tag)
    if not refs:
        return text

    normalized = re.sub(r"\n+", " ", text)
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?])", normalized) if _safe_text(p)]
    if not parts:
        return text

    out: List[str] = []
    ref_idx = 0
    for p in parts:
        if re.search(r"\[C\d+\]", p, flags=re.IGNORECASE):
            out.append(p)
            continue
        tag = refs[min(ref_idx, len(refs) - 1)]
        out.append(f"{p} {tag}")
        if ref_idx < len(refs) - 1:
            ref_idx += 1
    return "\n".join(out)


def _extract_version_markers(text: str) -> List[str]:
    t = _safe_text(text)
    if not t:
        return []
    markers = []
    markers.extend(re.findall(r"\bv\d+\b", t, flags=re.IGNORECASE))
    markers.extend(re.findall(r"版本\s*[:：]?\s*([A-Za-z0-9_\-\.]+)", t))
    out: List[str] = []
    for m in markers:
        x = _safe_text(m).lower()
        if x and x not in out:
            out.append(x)
    return out


def detect_citation_conflicts(citations: List[Dict[str, object]]) -> List[str]:
    if not citations:
        return []

    groups: Dict[str, Dict[str, object]] = {}
    for c in citations:
        title = _safe_text(c.get("source_title"))
        if not title:
            continue
        norm = re.sub(r"\(\s*v\d+\s*\)", "", title, flags=re.IGNORECASE)
        norm = re.sub(r"版本\s*[:：]?\s*[A-Za-z0-9_\-\.]+", "", norm)
        norm = re.sub(r"\s+", "", norm).lower()
        if not norm:
            continue

        markers = _extract_version_markers(title)
        g = groups.setdefault(norm, {"title": title, "versions": set(), "count": 0})
        g["count"] = int(g.get("count", 0)) + 1
        for m in markers:
            g["versions"].add(m)

    warnings: List[str] = []
    for g in groups.values():
        versions = list(g.get("versions") or [])
        if len(versions) >= 2:
            warnings.append(f"偵測到同主題多版本來源：{g['title']}（版本：{', '.join(sorted(versions))}），請留意版本差異。")

    return warnings[:3]
