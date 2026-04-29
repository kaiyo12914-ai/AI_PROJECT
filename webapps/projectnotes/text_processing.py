from __future__ import annotations

import re
from typing import List, Tuple

from .api_helpers import safe_text


STRUCTURAL_KEYWORDS = (
    "bbox",
    "shape_id",
    "placeholder",
    "paragraphs",
    "runs",
    "style",
    "font_family",
    "font_size",
    "alignment",
    "bullet_type",
    "z_index",
    "text_frame",
    "page_no",
)


def build_chunks(text: str, max_chars: int = 500) -> List[str]:
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def normalize_line_for_dedup(line: str) -> str:
    return re.sub(r"\s+", " ", safe_text(line)).strip(" \uFF0C\u3002\uFF1F\uFF01\uFF1B\uFF1A\u3001\uFF08\uFF09\u300C\u300D\u300E\u300F[]{}<>\"'")


def is_structural_noise_line(line: str) -> bool:
    l = safe_text(line)
    if not l:
        return True
    low = l.lower()
    if any(k in low for k in STRUCTURAL_KEYWORDS):
        return True
    if re.match(r"^\s*(<[^>]+>|</[^>]+>|<\?xml|<!DOCTYPE|@media|body\s*\{|\.?[A-Za-z0-9_-]+\s*\{)", l):
        return True
    if re.match(r"^\s*[\{\}\[\],]+$", l):
        return True
    if re.match(r'^\s*"[^"]+"\s*:\s*', l):
        return True
    if re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*:\s*", l) and ("http" not in low):
        return True
    if re.match(r"^\s*```", l):
        return True
    if re.match(r"^\s*[-=]{3,}\s*$", l):
        return True
    if re.match(r"^\s*[\[\(<].*[\]>\)]\s*$", l) and len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", l)) < 6:
        return True
    readable = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", l))
    symbols = len(re.findall(r"[^ \t\u4e00-\u9fffA-Za-z0-9]", l))
    if readable <= 2 and symbols >= 4:
        return True
    if symbols > readable * 2:
        return True
    return False


def clean_text_line(line: str) -> str:
    l = safe_text(line)
    if not l:
        return ""
    l = re.sub(r"<[^>\n]+>", " ", l)
    l = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", l)
    l = re.sub(r"`{1,3}", "", l)
    l = re.sub(r"^\s{0,3}#{1,6}\s*", "", l)
    l = re.sub(r"^\s*[-*+]\s+", "", l)
    l = re.sub(r"^\s*>\s*", "", l)
    l = re.sub(r"\bC\d+\(\d+(?:\.\d+)?\)", "", l, flags=re.IGNORECASE)
    l = l.replace("{", " ").replace("}", " ").replace("<", " ").replace(">", " ")
    l = l.replace("[", " ").replace("]", " ").replace("`", " ")
    l = re.sub(r"\s*Page\s*(\d+)\s*", r"Page \1 ", l, flags=re.IGNORECASE)
    l = re.sub(r"\s+", " ", l).strip()
    return l


def decoded_text_score(text: str) -> float:
    t = safe_text(text)
    if not t:
        return 0.0
    total = len(t)
    replacement_cnt = t.count("\uFFFD")
    control_cnt = len(re.findall(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", t))
    readable_cnt = len(
        re.findall(r"[\u4e00-\u9fffA-Za-z0-9\s\.,!?:;\"'\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A\uFF08\uFF09\u3010\u3011\u300A\u300B\u3001_/\(\)\[\]\{\}-]", t)
    )
    readable_ratio = readable_cnt / max(1, total)
    mojibake_hits = 0
    for token in ("\uFFFD", "?", "疇", "癟", "矇", "疆", "瞻"):
        mojibake_hits += t.count(token)
    score = readable_ratio
    score -= replacement_cnt * 0.08
    score -= control_cnt * 0.05
    score -= mojibake_hits * 0.02
    if (control_cnt / max(1, total)) > 0.02:
        score -= 0.8
    if total > 6 and readable_cnt < max(2, int(total * 0.2)):
        score -= 0.5
    return max(0.0, min(1.0, score))


def decode_text_bytes_best_effort(raw: bytes) -> Tuple[str, str]:
    if raw is None or len(raw) == 0:
        return "", "utf-8"
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except Exception:
            pass
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except Exception:
            pass

    candidates = ["utf-8", "cp950", "big5", "gb18030", "utf-16-le", "utf-16-be"]
    best_text = ""
    best_enc = ""
    best_score = -1.0
    for enc in candidates:
        try:
            txt = raw.decode(enc)
        except Exception:
            continue
        score = decoded_text_score(txt)
        if score > best_score:
            best_score = score
            best_text = txt
            best_enc = enc
    if best_score < 0.35:
        raise ValueError("unsupported or unreadable text encoding")
    return best_text, (best_enc or "unknown")


def preprocess_rag_text(input_text: str) -> str:
    text = (input_text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"```[\s\S]*?```", "\n", text)
    out_lines: List[str] = []
    seen = set()
    blank_pending = False
    for raw_line in text.split("\n"):
        if is_structural_noise_line(raw_line):
            blank_pending = True
            continue
        cleaned = clean_text_line(raw_line)
        if not cleaned or is_structural_noise_line(cleaned):
            blank_pending = True
            continue
        dedup_key = normalize_line_for_dedup(cleaned)
        if not dedup_key or dedup_key in seen:
            continue
        seen.add(dedup_key)
        if blank_pending and out_lines:
            out_lines.append("")
            blank_pending = False
        out_lines.append(cleaned)

    final_lines: List[str] = []
    for ln in out_lines:
        if ln == "":
            if final_lines and final_lines[-1] != "":
                final_lines.append("")
            continue
        final_lines.append(ln)
    return "\n".join(final_lines).strip()


def looks_mojibake_text(text: str) -> bool:
    t = safe_text(text)
    if not t:
        return False
    compact = re.sub(r"\s+", "", t)
    if not compact:
        return False
    if re.fullmatch(r"[?\uFFFD]+", compact):
        return True
    if "???" in t or "\uFFFD" in t:
        return True
    return False


def clean_label(raw: object, fallback: str, max_len: int = 120) -> str:
    t = safe_text(raw)[:max_len]
    if not t:
        return fallback
    if looks_mojibake_text(t):
        return fallback
    return t

