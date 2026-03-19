# webapps/doc/views_helpers.py
from __future__ import annotations

import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from django.db import connection as dj_connection, transaction
from django.db.models import Q
from django.db.utils import IntegrityError, OperationalError, NotSupportedError

from webapps.doc.models import DocumentTemplate


# ============================================================
# helpers
# ============================================================

def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name, str(int(default))) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def _to_text(x: Any) -> str:
    def _parts_to_text(parts_obj: Any) -> str:
        if not isinstance(parts_obj, list):
            return ""
        parts: List[str] = []
        for item in parts_obj:
            if isinstance(item, str):
                t = item.strip()
                if t:
                    parts.append(t)
                continue
            if isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt.strip())
                    continue
                if item.get("type") == "text":
                    txt2 = item.get("text")
                    if isinstance(txt2, str) and txt2.strip():
                        parts.append(txt2.strip())
        return "\n".join(parts).strip()

    if x is None:
        return ""
    if hasattr(x, "content"):
        c = getattr(x, "content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return _parts_to_text(c)
        return str(c or "")
    if isinstance(x, dict):
        if "content" in x:
            v = x.get("content")
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                return _parts_to_text(v)
            return str(v or "")
        if "text" in x:
            return str(x.get("text") or "")
    return str(x)


def _clean_generated_draft(text: str) -> str:
    s = (text or "").lstrip()
    s = s.lstrip("").lstrip()

    # 去掉模型可能吐出的 tags/說明頭
    s = re.sub(
        r'^\s*[（(][\s\S]{0,600}?\btags\s*:\s*[\s\S]{0,300}?[）)]\s*\r?\n',
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"^\s*[（(]?\s*tags\s*:\s*.*?[）)]?\s*\r?\n",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"^\s*[（(].{0,120}[）)]\s*\r?\n", "", s)
    return s.lstrip()


def _clean_tags(tags: Any) -> List[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        return []
    out: List[str] = []
    seen = set()
    for x in tags:
        s = _safe_str(x).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _infer_tags_from_text(text: str) -> List[str]:
    t = (text or "")
    rules: List[Tuple[str, str]] = [
        ("資訊", "系統|資安|弱點|帳號|權限|伺服器|備份|機房|端點|EDR|SOC|告警|監測|MES|IIoT"),
        ("採購", "採購|招擺|詢價|契約|廠商|決標|開標|比價|規格|驗收|開口|框架"),
        ("主財", "預算|經費|核銷|報支|憑證|請款|撥款|付款|概算|決算"),
        ("品保", "品質|檢驗|首件|不良|異常|RCA|稽核|改善|報廢"),
        ("生產", "產線|稼動|排程|產能|備料|出貨|停線|試量產"),
        ("設施供應", "修繕|空調|電力|消防|水電|工程|設備保養|維護|治具"),
        ("人事", "人力|招募|派遣|約用|教育訓練|考績"),
        ("行政", "會議|公告|制度|流程|總務|庶務|文書"),
        ("研發", "研發|設計|驗證|試驗|專利|新產品"),
        ("計劃", "計畫|專案|里程碑|年度計畫"),
        ("職安衛", "職安|工安|環安|安全衛生|危害|風險"),
        ("測情", "情資|研判|通報|預警|態勢|威脅"),
    ]

    out: List[str] = []
    for tag, pattern in rules:
        if re.search(pattern, t):
            out.append(tag)

    seen = set()
    dedup: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup


# ============================================================
# ✅ doc_type choices helpers
# ============================================================

def _doc_type_choices_dict() -> Dict[str, str]:
    try:
        field = DocumentTemplate._meta.get_field("doc_type")
        return {str(k): str(v) for k, v in (field.choices or [])}
    except Exception:
        return {}


def _valid_doc_types_set() -> set:
    return set(_doc_type_choices_dict().keys())


def _doc_type_label(doc_type: str) -> str:
    return _doc_type_choices_dict().get(doc_type, doc_type)


def _first_subject_line(draft: str) -> str:
    for line in (draft or "").splitlines():
        t = line.strip()
        if not t:
            continue
        m = re.match(r"^主旨[:：]\s*(.+)$", t)
        if m:
            return m.group(1).strip()
    return ""


def _build_seed_title(doc_type: str, draft: str) -> str:
    label = _doc_type_label(doc_type)
    subj = _first_subject_line(draft) or "未命名範例"
    subj = re.sub(r"[。．\.]+$", "", subj).strip()
    if len(subj) > 40:
        subj = subj[:40] + "…"
    return f"{label}—{subj}範例"


def _build_seed_description(doc_type: str, tags: List[str], draft: str) -> str:
    parts = []
    if tags:
        parts.append(" / ".join(tags[:4]))
    subj = _first_subject_line(draft)
    if subj:
        subj = subj.strip()
        if len(subj) > 28:
            subj = subj[:28] + "…"
        parts.append(subj)
    return " / ".join([p for p in parts if p]).strip() or "自動產生範例"


# ============================================================
# ✅ Visibility
# ============================================================

def _templates_visibility_filter(qs, *, user, is_auth: bool):
    if is_auth:
        return qs.filter(Q(scope="public") | Q(scope="personal", owner=user))
    return qs.filter(scope="public")


def _apply_tag_filter(qs, tag: str):
    tag = (tag or "").strip()
    if not tag:
        return qs

    def _py_filter(iterable):
        return [t for t in iterable if tag in (getattr(t, "tags", None) or [])]

    if dj_connection.vendor == "sqlite":
        try:
            qs = qs.order_by("-created_at")
        except Exception:
            qs = qs.order_by("-id")
        return _py_filter(qs)

    try:
        return qs.filter(tags__contains=[tag])
    except (NotSupportedError, OperationalError):
        return _py_filter(qs)


# ============================================================
# ✅ 排版標準化
# ============================================================

_PHRASE_RULES: List[Dict[str, Any]] = [
    {"mode": "replace", "src": "敬請核示。", "dst": "請核示。"},
    {"mode": "replace", "src": "敬請核示", "dst": "請核示"},
    {"mode": "replace", "src": "敬請查照。", "dst": "請查照。"},
    {"mode": "replace", "src": "敬請查照", "dst": "請查照"},
    {"mode": "replace", "src": "敬請鑒核。", "dst": "請鑒核。"},
    {"mode": "replace", "src": "敬請鑒核", "dst": "請鑒核"},
]

def _apply_phrase_rules(text: str) -> str:
    t = text or ""
    for r in _PHRASE_RULES:
        if r["mode"] == "replace":
            t = t.replace(r["src"], r["dst"])
    return t

def _postprocess_official_style(text: str) -> str:
    """
    物理修正規範化的公文排版
    """
    if not text: return ""
    t = _apply_phrase_rules(text)
    lines = t.splitlines()
    out = []
    for line in lines:
        if re.match(r"^\([一二三四五六七八九十]+\)", line.strip()):
            out.append("\n" + line.strip())
        else:
            out.append(line)
    res = "\n".join(out).strip()
    res = re.sub(r"(主旨|說明|擬辦|辦法)[:：]", r"\1：", res)
    return res


# ============================================================
# ✅ 新制 Schema Helpers
# ============================================================

def _normalize_sections(body_sections: Any) -> Dict[str, Any]:
    if isinstance(body_sections, dict):
        return body_sections
    return {}

def _normalize_doc_fields(body_fields: Any) -> Dict[str, Any]:
    return body_fields if isinstance(body_fields, dict) else {}

def _normalize_meta(body_meta: Any) -> Dict[str, Any]:
    return body_meta if isinstance(body_meta, dict) else {}

def _draft_to_sections(doc_type: str, draft_text: str) -> Dict[str, Any]:
    sections = {"subject": "", "explain": "", "action": ""}
    parts = re.split(r"\n\s*(主旨|說明|擬辦|建議|擬辦建議|辦法)\s*[:：]?", "\n" + draft_text)
    current_key = ""
    for part in parts:
        p = part.strip()
        if p in ["主旨"]: current_key = "subject"
        elif p in ["說明"]: current_key = "explain"
        elif p in ["擬辦", "建議", "擬辦建議", "辦法"]: current_key = "action"
        elif current_key:
            sections[current_key] = p
    return sections


def _save_template_with_conflict_policy_v2(
    *, title: str, doc_type: str, description: str, sections: Dict[str, Any],
    doc_fields: Dict[str, Any], meta: Dict[str, Any], tags: List[str],
    scope: str, user, on_conflict: str, schema_ver: int = 2, max_suffix_try: int = 50,
):
    defaults = {
        "doc_type": doc_type, "description": description, "sections": sections,
        "doc_fields": doc_fields, "meta": meta, "schema_ver": schema_ver,
        "tags": tags, "scope": scope, "owner": (user if scope == "personal" else None),
    }
    obj, created = DocumentTemplate.objects.update_or_create(title=title, defaults=defaults)
    return obj, created, obj.title, "saved", "ok"


# ============================================================
# File extractors
# ============================================================

def _extract_text_docx(file_obj) -> str:
    from docx import Document
    doc = Document(file_obj)
    return "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])

def _extract_text_pdf(file_obj) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_obj)
    return "\n\n".join([(p.extract_text() or "").strip() for p in reader.pages])

def _extract_text_by_ext(file_obj, filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".docx": return _extract_text_docx(file_obj)
    if ext == ".pdf": return _extract_text_pdf(file_obj)
    return ""


# ============================================================
# parse_focus prompt helpers
# ============================================================

def _build_attach_focus_prompt(combined_text: str, extra_hint: str = "") -> str:
    hint = (extra_hint or "").strip()
    hint_block = f"\n補充限制：{hint}\n" if hint else "\n"
    return (
        "請將以下附件內容整理為 20 個關鍵重點。\n"
        "輸出規則：\n"
        "1. 僅輸出重點條列，每行一點。\n"
        "2. 每行格式固定：重點N：內容。\n"
        "3. 禁止輸出任何導言、前置說明、結語、摘要標題、角色敘述。\n"
        "4. 禁止輸出與原文無關的推測或補充欄位（如文件目的/文件類型）。\n"
        "5. 內容必須可對應附件原文。\n"
        f"{hint_block}"
        f"附件內容：\n{combined_text}"
    )


def _ensure_focus_numbered(text: str, max_points: int = 20) -> str:
    s = (text or "").strip()
    if not s: return ""
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    out = []

    # Filter out model boilerplate/meta lines that are not source-document content.
    boilerplate_patterns = [
        r"^以下是整理後的?\s*\d+\s*個?關鍵重點[：:]?\s*$",
        r"^以下為整理後的?\s*\d+\s*個?關鍵重點[：:]?\s*$",
        r"^以下是.*關鍵重點[：:]?\s*$",
        r"^以下為.*關鍵重點[：:]?\s*$",
        r"^整理如下[：:]?\s*$",
        r"^重點如下[：:]?\s*$",
        r"^這份文件是一份由.+發出的正式公文[（(][呈令函][）)].*$",
        r"^由於原始文件內容較為簡[練略].*以下為[您你].*關鍵重點.*$",
        r"^以下為[您你].*拆解並整理.*關鍵重點.*$",
    ]

    def _strip_leading_ord(v: str) -> str:
        t = (v or "").strip()
        # 去除行首既有點次，避免「重點15：14. ...」這種重複編號
        t = re.sub(r"^\d+\s*[\.\、\)）:：]\s*", "", t)
        return t.strip()

    for i, ln in enumerate(lines[:max_points], 1):
        if any(re.match(pat, ln, flags=re.IGNORECASE) for pat in boilerplate_patterns):
            continue
        if re.match(r"^\s*重點\s*\d+\s*[:：]\s*\*\*[^*]{1,24}\*\*\s*[:：].+$", ln):
            continue
        m = re.match(r"^重點\s*\d+\s*[：:]\s*(.*)$", ln)
        if m:
            body = _strip_leading_ord(m.group(1))
            if not body:
                continue
            out.append(f"重點{i}：{body}")
        else:
            body = _strip_leading_ord(ln)
            if not body:
                continue
            out.append(f"重點{i}：{body}")
    # Re-number after filtering so numbers remain contiguous.
    renum = []
    for idx, row in enumerate(out[:max_points], 1):
        body = re.sub(r"^重點\s*\d+\s*[：:]\s*", "", row).strip()
        if body:
            renum.append(f"重點{idx}：{body}")
    return "\n".join(renum).strip()
