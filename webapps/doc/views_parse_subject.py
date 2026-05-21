from __future__ import annotations

import re
from typing import Callable


SUBJECT_KEY = "主旨"
STOP_KEYS = [
    "說明", "附件", "受文者", "發文日期", "發文字號",
    "檔號", "保存年限", "密等", "速別", "正本", "副本", "抄送",
]


def _norm_line(s: str, compact_spaced_cjk: Callable[[str], str]) -> str:
    s = compact_spaced_cjk((s or "").strip())
    return re.sub(r"[\s\u3000]+", "", s)


def _starts_with_key(s: str, key: str, compact_spaced_cjk: Callable[[str], str]) -> bool:
    x = _norm_line(s, compact_spaced_cjk)
    return x.startswith(key + "：") or x.startswith(key + ":")


def _after_colon(s: str, compact_spaced_cjk: Callable[[str], str]) -> str:
    x = _norm_line(s, compact_spaced_cjk)
    if "：" in x:
        return x.split("：", 1)[1]
    if ":" in x:
        return x.split(":", 1)[1]
    return ""


def _is_list_start(line: str) -> bool:
    if re.match(r"^[一二三四五六七八九十]+\s*[、.．:]", line):
        return True
    if re.match(r"^\d+\s*[、.．:]", line):
        return True
    if re.match(r"^[\(（][一二三四五六七八九十\d]+[\)）]", line):
        return True
    return False


def _trim_subject_tail(subj: str) -> str:
    subj = re.sub(r"\s+", "", subj)
    subj = re.sub(r"[,，。．\s]+$", "", subj)
    for tail in ("請核示", "請鑒核", "請示"):
        if subj.endswith(tail):
            subj = subj[: -len(tail)].rstrip("，,。． ")
            break
    return subj


def _extract_doc_subject(text: str, compact_spaced_cjk: Callable[[str], str]) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for i, line in enumerate(lines):
        if not _starts_with_key(line, SUBJECT_KEY, compact_spaced_cjk):
            continue

        parts = []
        first = _after_colon(line, compact_spaced_cjk).strip()
        if first:
            parts.append(first)

        for j in range(i + 1, len(lines)):
            ln = (lines[j] or "").strip()
            if not ln:
                break
            if any(_starts_with_key(ln, k, compact_spaced_cjk) for k in STOP_KEYS):
                break
            if _is_list_start(ln):
                break
            parts.append(_norm_line(ln, compact_spaced_cjk))

        return _trim_subject_tail("".join(parts).strip())
    return ""


def _extract_doc_subject_fallback(text: str, compact_spaced_cjk: Callable[[str], str]) -> str:
    lines = [compact_spaced_cjk(x or "").strip() for x in (text or "").splitlines()]
    if not lines:
        return ""

    for i, ln in enumerate(lines):
        nln = re.sub(r"[\s\u3000]+", "", ln or "")
        if not (nln.startswith(SUBJECT_KEY + "：") or nln.startswith(SUBJECT_KEY + ":")):
            continue

        first = nln.split("：", 1)[1] if "：" in nln else (nln.split(":", 1)[1] if ":" in nln else "")
        parts = [first] if first else []

        for j in range(i + 1, len(lines)):
            n = re.sub(r"[\s\u3000]+", "", (lines[j] or ""))
            if not n:
                break
            if any(n.startswith(k + "：") or n.startswith(k + ":") for k in STOP_KEYS):
                break
            if _is_list_start(n):
                break
            parts.append(n)

        subj = _trim_subject_tail("".join(parts).strip())
        if subj:
            return subj
    return ""
