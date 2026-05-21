from __future__ import annotations

import re


def _extract_doc_subject(text: str, compact_spaced_cjk):
    lines = [ln.strip() for ln in (text or "").splitlines()]

    K_SUBJ = "\u4e3b\u65e8"
    STOP_KEYS = [
        "\u8aaa\u660e", "\u9644\u4ef6", "\u53d7\u6587\u8005", "\u767c\u6587\u65e5\u671f", "\u767c\u6587\u5b57\u865f",
        "\u6a94\u865f", "\u4fdd\u5b58\u5e74\u9650", "\u5bc6\u7b49", "\u901f\u5225", "\u6b63\u672c", "\u526f\u672c", "\u6284\u9001",
    ]

    def norm(s: str) -> str:
        s = compact_spaced_cjk((s or "").strip())
        return re.sub(r"[\\s\\u3000]+", "", s)

    def starts_key(s: str, k: str) -> bool:
        x = norm(s)
        return x.startswith(k + "?") or x.startswith(k + ":")

    def after_colon(s: str) -> str:
        x = norm(s)
        if "?" in x:
            return x.split("?", 1)[1]
        if ":" in x:
            return x.split(":", 1)[1]
        return ""

    for i, line in enumerate(lines):
        if not starts_key(line, K_SUBJ):
            continue
        parts = []
        first = after_colon(line).strip()
        if first:
            parts.append(first)
        for j in range(i + 1, len(lines)):
            ln = (lines[j] or "").strip()
            if not ln:
                break
            if any(starts_key(ln, k) for k in STOP_KEYS):
                break
            if re.match(r"^[??????????]+\\s*[?.?:]", ln):
                break
            if re.match(r"^\\d+\\s*[?.?:]", ln):
                break
            if re.match(r"^[\\(?][??????????\\d]+[\\)?]", ln):
                break
            parts.append(norm(ln))

        subj = "".join(parts).strip()
        subj = re.sub(r"\\s+", "", subj)
        subj = re.sub(r"[,???\\s]+$", "", subj)
        for tail in ("\u8acb\u6838\u793a", "\u8acb\u9452\u6838", "\u8acb\u793a"):
            if subj.endswith(tail):
                subj = subj[: -len(tail)].rstrip("?,?? ")
                break
        return subj
    return ""


def _extract_doc_subject_fallback(text: str, compact_spaced_cjk):
    lines = [compact_spaced_cjk(x or "").strip() for x in (text or "").splitlines()]
    if not lines:
        return ""

    k_subject = "\u4e3b\u65e8"
    stop_keys = [
        "\u8aaa\u660e", "\u9644\u4ef6", "\u53d7\u6587\u8005", "\u767c\u6587\u65e5\u671f", "\u767c\u6587\u5b57\u865f",
        "\u6a94\u865f", "\u4fdd\u5b58\u5e74\u9650", "\u5bc6\u7b49", "\u901f\u5225", "\u6b63\u672c", "\u526f\u672c", "\u6284\u9001",
    ]

    def _starts_with_key(s: str, key: str) -> bool:
        t = re.sub(r"[\\s\\u3000]+", "", s or "")
        return t.startswith(key + "?") or t.startswith(key + ":")

    for i, ln in enumerate(lines):
        nln = re.sub(r"[\\s\\u3000]+", "", ln or "")
        if not (nln.startswith(k_subject + "?") or nln.startswith(k_subject + ":")):
            continue
        first = nln.split("?", 1)[1] if "?" in nln else (nln.split(":", 1)[1] if ":" in nln else "")
        parts = [first] if first else []
        for j in range(i + 1, len(lines)):
            n = re.sub(r"[\\s\\u3000]+", "", (lines[j] or ""))
            if not n:
                break
            if any(n.startswith(k + "?") or n.startswith(k + ":") for k in stop_keys):
                break
            if re.match(r"^[??????????]+\\s*[?.?:]", n):
                break
            if re.match(r"^\\d+\\s*[?.?:]", n):
                break
            if re.match(r"^[\\(?][??????????\\d]+[\\)?]", n):
                break
            parts.append(n)
        subj = "".join(parts).strip()
        subj = re.sub(r"[,???\\s]+$", "", subj)
        if subj:
            return subj
    return ""
