import re
from typing import List, Dict, Any, Optional

from webapps.llm.llm_factory import get_chat_model
from webapps.projectnotes.api_helpers import safe_text, to_int
from webapps.projectnotes.lang_guard import prefer_traditional_chinese, is_zh_dominant
from webapps.projectnotes.citation_guard import ensure_sentence_citations, detect_citation_conflicts

class ProjectNotesContextBuilder:
    """
    Assembles prompt context from retrieved chunks, conversation history, and user question.
    Provides methods for synthesizing the final answer using LLMs.
    """

    def __init__(self, question: str, citations: List[Dict[str, Any]], conversation_history: Optional[List[Dict[str, str]]] = None):
        self.question = question
        self.citations = citations
        self.conversation_history = conversation_history or []
        self.max_citations = 4

    def _llm_to_text(self, resp: Any) -> str:
        if resp is None:
            return ""
        content = getattr(resp, "content", resp)
        if isinstance(content, tuple):
            content = content[0]
        if isinstance(content, str):
            c_stripped = content.strip()
            if (c_stripped.startswith("('") or c_stripped.startswith('("')) and c_stripped.endswith(")"):
                import ast
                try:
                    parsed = ast.literal_eval(c_stripped)
                    if isinstance(parsed, tuple):
                        content = parsed[0]
                except Exception:
                    pass
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict) and "text" in p:
                    parts.append(str(p["text"]))
            content = "".join(parts)
        return safe_text(content)

    def _clean_evidence_for_llm(self, text: str) -> str:
        t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        bad_patterns = [
            r"lorem ipsum",
            r"reallygreatsite",
            r"\bwww\.[a-z0-9.-]+\.[a-z]{2,}\b",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            r"\+?\d[\d\-\s]{7,}\d",
            r"\bshape_id\b|\bbbox\b|\bplaceholder\b|\bparagraphs\b|\bruns\b|\bstyle\b",
        ]
        out: List[str] = []
        for raw in t.split("\n"):
            line = safe_text(raw)
            if not line:
                continue
            low = line.lower()
            if re.match(r"^\s*Page\s*\d+\s*$", line):
                continue
            if any(re.search(p, low, flags=re.IGNORECASE) for p in bad_patterns):
                continue
            if re.search(r"[{}\[\]<>]", line) and len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", line)) < 10:
                continue
            out.append(line)
        return "\n".join(out).strip()

    def _post_clean_llm_answer(self, text: str) -> str:
        t = safe_text(text)
        if not t:
            return ""
        lines: List[str] = []
        for raw in t.split("\n"):
            line = safe_text(raw)
            if not line:
                continue
            low = line.lower()
            if "lorem ipsum" in low or "reallygreatsite" in low:
                continue
            if re.search(r"\bwww\.[a-z0-9.-]+\.[a-z]{2,}\b", low):
                continue
            if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line):
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _select_citations(self) -> List[Dict[str, Any]]:
        # Take the top N most confident citations that have valid excerpts
        if not self.citations:
            return []
        
        # fallback: keep the top confident citations but clean excerpt
        fallback = sorted(self.citations, key=lambda x: float(x.get("confidence") or 0.0), reverse=True)[:self.max_citations]
        out = []
        for c in fallback:
            excerpt = self._clean_evidence_for_llm(safe_text(c.get("excerpt")))
            if not excerpt:
                continue
            item = dict(c)
            item["_excerpt_clean"] = excerpt
            out.append(item)
        return out

    def build_evidence_text(self) -> str:
        selected = self._select_citations()
        if not selected:
            return ""
        ev_lines: List[str] = []
        for c in selected:
            ref = safe_text(c.get("ref")) or "C"
            title = safe_text(c.get("source_title"))
            idx = to_int(c.get("chunk_index"), 0)
            excerpt = safe_text(c.get("_excerpt_clean"))
            if len(excerpt) > 400:
                excerpt = excerpt[:400].rstrip() + "..."
            if not excerpt:
                continue
            ev_lines.append(f"[{ref}] {title}#{idx}\n{excerpt}")
        return "\n\n".join(ev_lines)

    def synthesize_answer(self, rule_answer: str) -> Dict[str, Any]:
        if not self.citations:
            return {"answer": safe_text(rule_answer), "prompt": "", "warnings": []}
            
        evidence_text = self.build_evidence_text()
        if not evidence_text:
            return {"answer": safe_text(rule_answer), "prompt": "", "warnings": []}
            
        history_text = ""
        if self.conversation_history:
            history_lines = ["\n過往對話紀錄："]
            # Limit to last 3 turns
            for msg in self.conversation_history[-6:]:
                role = "使用者" if msg.get("role") == "user" else "助裡"
                history_lines.append(f"{role}: {msg.get('content')}")
            history_text = "\n".join(history_lines)

        prompt = f"""
\u4f60\u662f\u516c\u6587\u8207\u77e5\u8b58\u6574\u5408\u52a9\u7406\u3002\u8acb\u4f9d\u64da\u4e0b\u65b9 evidence \u56de\u7b54\uff0c\u4e14\u5fc5\u9808\u9075\u5b88\uff1a
1. \u50c5\u80fd\u4f7f\u7528 evidence \u5167\u5bb9\u4f5c\u7b54\uff0c\u4e0d\u53ef\u81ea\u884c\u88dc\u5145\u672a\u63d0\u4f9b\u7684\u4e8b\u5be6\u3002
2. \u56de\u7b54\u8a9e\u8a00\u4e00\u5f8b\u4f7f\u7528\u7e41\u9ad4\u4e2d\u6587\u3002
3. \u56de\u7b54\u683c\u5f0f\u63a1\u4e00\u554f\u4e00\u7b54\uff0c\u5167\u5bb9\u76f4\u63a5\u3001\u6e05\u695a\u3002
4. \u82e5 evidence \u4e0d\u8db3\u4ee5\u5b8c\u6574\u56de\u7b54\uff0c\u8acb\u660e\u78ba\u8aaa\u660e\u4e0d\u8db3\u8655\uff0c\u907f\u514d\u81c6\u6e2c\u3002
5. \u82e5\u5f15\u7528\u8b49\u64da\uff0c\u8acb\u5728\u53e5\u672b\u4ee5 [C1] \u9019\u7a2e\u683c\u5f0f\u6a19\u793a\u3002{history_text}

\u554f\u984c\uff1a
{self.question}

evidence\uff1a
{evidence_text}
""".strip()

        def _rewrite_to_traditional_chinese(llm_obj: Any, text: str) -> str:
            raw = safe_text(text)
            if not raw:
                return ""
            rewrite_prompt = f"""
隢?銝??批捆?孵神?箇?擃葉??靽???嚗????冽?閮? [C1]?C2]??
撠????臭????雿擗?餈啗?隞亦?擃葉???整€?
隢頛詨?孵神敺摰對?銝?憿?隤芣???

?批捆嚗?
{raw}
""".strip()
            try:
                out2 = llm_obj.invoke(rewrite_prompt)
                return self._post_clean_llm_answer(self._llm_to_text(out2))
            except Exception:
                return ""

        try:
            llm = get_chat_model(temperature=0.1, timeout=90)
            out = llm.invoke(prompt)
            txt = self._post_clean_llm_answer(self._llm_to_text(out))
            if not is_zh_dominant(txt):
                rewritten = _rewrite_to_traditional_chinese(llm, txt)
                if rewritten:
                    txt = rewritten
            fallback_zh = safe_text(rule_answer)
            if fallback_zh and not is_zh_dominant(fallback_zh):
                rewritten_fb = _rewrite_to_traditional_chinese(llm, fallback_zh)
                if rewritten_fb:
                    fallback_zh = rewritten_fb
            final_txt = prefer_traditional_chinese(txt, fallback_zh)
            final_txt = ensure_sentence_citations(final_txt, self.citations)
            warnings = detect_citation_conflicts(self.citations)
            return {"answer": final_txt, "prompt": prompt, "warnings": warnings}
        except Exception:
            fallback_txt = ensure_sentence_citations(safe_text(rule_answer), self.citations)
            warnings = detect_citation_conflicts(self.citations)
            return {"answer": fallback_txt, "prompt": prompt, "warnings": warnings}


def build_answer_from_evidence(query: str, evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "\u76ee\u524d\u5728\u5df2\u9078\u4f86\u6e90\u4e2d\u627e\u4e0d\u5230\u53ef\u7528\u8b49\u64da\u3002"
    lines = [f"\u4f9d\u64da\u5df2\u9078\u4f86\u6e90\uff0c\u91dd\u5c0d\u300c{query}\u300d\u6574\u7406\u5982\u4e0b\uff1a"]
    for i, ev in enumerate(evidence[:3], start=1):
        src = safe_text(ev.get("source_title"))
        if not src:
            src = f"\u4f86\u6e90{i}"
        lines.append(f"{i}. \u5df2\u53c3\u8003\uff1a{src}")
    lines.append("\u8a73\u7d30 CHUNK \u53c3\u8003\u8acb\u53c3\u8003\u4e0b\u65b9\u300cCHUNK \u67e5\u8a62\u7d00\u9304\u300d\u5340\u584a\u3002")
    return "\n".join(lines)


def build_citation_tail(citations: List[Dict[str, Any]]) -> str:
    if not citations:
        return ""
    parts: List[str] = []
    for c in citations:
        ref = safe_text(c.get("ref")) or "C"
        conf_raw = c.get("confidence")
        try:
            conf = f"{float(conf_raw):.2f}"
        except Exception:
            conf = "--"
        chunk = to_int(c.get("chunk_index"), 0)
        title = safe_text(c.get("source_title")) or "\u672a\u77e5\u4f86\u6e90"
        parts.append(f"{ref}({conf})#{chunk} 『{title}』#{chunk}")
    return "來源依據：" + "、".join(parts)
