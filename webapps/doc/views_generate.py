# webapps/doc/views_generate.py
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.doc.models import DocumentTemplate
from webapps.doc.prompt import build_prompt as build_prompt_v2
from webapps.doc.services.doc_db_router import normalize_doc_plant
from webapps.doc.utils_login import get_login_user_org, get_login_user_idno
from webapps.llm.llm_factory import get_chat_model
from webapps.portal.oracle_emp import get_emp_full_info

from webapps.doc.views_helpers import (
    _safe_str,
    _env_bool,
    _to_text,
    _clean_generated_draft,
    _valid_doc_types_set,
    _templates_visibility_filter,
    _first_subject_line,
    _build_seed_title,
    _build_seed_description,
    _draft_to_sections,
    _normalize_doc_fields,
    _postprocess_official_style,
    _save_template_with_conflict_policy_v2,
)

logger = logging.getLogger(__name__)

_FULL_SUBORDINATE_UNIT_RE = re.compile(
    r"(?:國防部)?軍備局(?:生產製造中心|生製中心)\s*(第[○〇０0一二三四五六七八九十\d]{1,4}廠)"
)
_SHORT_SUBORDINATE_UNIT_RE = re.compile(r"(第[○〇０0一二三四五六七八九十\d]{1,4}廠)")
_FULL_SUBORDINATE_UNIT_PREFIX = "國防部軍備局生產製造中心"


def _normalize_subordinate_unit_short_name(text: str) -> str:
    """
    下轄單位名稱一律使用簡稱（如：第四0一廠），避免輸出完整機關全銜。
    """
    t = text or ""
    if not t.strip():
        return t
    t = _FULL_SUBORDINATE_UNIT_RE.sub(r"\1", t)
    t = re.sub(
        r"(第[○〇０0一二三四五六七八九十\d]{1,4}廠)\s*\1",
        r"\1",
        t,
    )
    return t


def _expand_subordinate_unit_full_name(text: str) -> str:
    """
    將簡銜（如：第401廠）展開為全銜（國防部軍備局生產製造中心第401廠）。
    """
    t = text or ""
    if not t.strip():
        return t
    t = re.sub(
        r"(?<!軍備局生產製造中心)(?<!軍備局生製中心)(第[○〇０0一二三四五六七八九十\d]{1,4}廠)",
        rf"{_FULL_SUBORDINATE_UNIT_PREFIX}\1",
        t,
    )
    return t


def _normalize_explain_unit_names_by_point(explain_text: str) -> str:
    """
    規則：
    - 說明第一點（依據）使用單位全銜。
    - 說明第二點起使用單位簡銜。
    """
    t = (explain_text or "").strip()
    if not t:
        return t

    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    pts: list[str] = []
    for ln in rows:
        m = re.match(r"^[一二三四五六七八九十]+、\s*(.+)$", ln)
        if m:
            pts.append((m.group(1) or "").strip())
        elif pts:
            pts[-1] = f"{pts[-1]} {ln}".strip()
        else:
            pts.append(ln)
    if not pts:
        return t

    out: list[str] = []
    for idx, body in enumerate(pts):
        b = (body or "").strip()
        if idx == 0:
            out.append(_expand_subordinate_unit_full_name(b))
        else:
            out.append(_normalize_subordinate_unit_short_name(b))

    marks = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    return "\n".join([f"{marks[i]}、{out[i]}" for i in range(min(len(out), len(marks)))]).strip()

def _resolve_signer_org(request: HttpRequest, body: Dict[str, Any]) -> tuple[str, str, str]:
    explicit = normalize_doc_plant(str(body.get("plant") or "").strip(), default="") if body.get("plant") else ""
    from_whoami = normalize_doc_plant(get_login_user_org(request), default="")
    plant = explicit or from_whoami or normalize_doc_plant("", default="MPC")

    if plant == "MPC":
        return plant, "MPC", "本中心"
    if plant in {"202", "205", "209", "401"}:
        return plant, f"{plant}廠", "本廠"
    return plant, plant, "本單位"


def _force_inject_fixed_quote(sections: Dict[str, Any], fixed_quote: str) -> Dict[str, Any]:
    """
    【物理強制注入機制】
    確保說明段落的第一點絕對是解析階段產出的固定引述句。
    """
    if not fixed_quote:
        return sections
        
    explain = (sections.get("explain", "") or "").strip()
    if not explain:
        sections["explain"] = f"(一) {fixed_quote}".strip()
        return sections

    # 不覆蓋原有說明：僅前置插入固定引述，原段落完整保留。
    # 若原文已含點次，將其點次整體順延 +1。
    if re.search(r"\([一二三四五六七八九十]+\)", explain):
        map_inc = {
            "一": "二", "二": "三", "三": "四", "四": "五", "五": "六",
            "六": "七", "七": "八", "八": "九", "九": "十",
        }
        def _bump(m: re.Match[str]) -> str:
            ch = m.group(1)
            return f"({map_inc.get(ch, ch)})"
        shifted = re.sub(r"\(([一二三四五六七八九])\)", _bump, explain)
        sections["explain"] = f"(一) {fixed_quote}\n{shifted}".strip()
    else:
        sections["explain"] = f"(一) {fixed_quote}\n(二) {explain}".strip()
    return sections


def _normalize_single_point_action(action_text: str) -> str:
    """
    單點不成行：擬辦只有一點時，去掉前導點次標記（(一) 或 一、）。
    """
    t = (action_text or "").strip()
    if not t:
        return ""
    marks_paren = re.findall(r"\([一二三四五六七八九十]+\)", t)
    marks_cn = re.findall(r"^[一二三四五六七八九十]+、", t, flags=re.M)
    total_marks = len(marks_paren) + len(marks_cn)
    if total_marks == 1:
        t = re.sub(r"^\s*\([一二三四五六七八九十]+\)\s*", "", t).strip()
        t = re.sub(r"^\s*[一二三四五六七八九十]+、\s*", "", t).strip()
    return t


def _force_action_sentence_for_single_point(action_text: str) -> str:
    """
    單點擬辦統一為單句格式（不編號），但不覆蓋為特定案件固定內容。
    多點情境保留原有一、二、條列。
    """
    t = (action_text or "").strip()
    if not t:
        return t
    if _is_single_point_action(t):
        body = re.sub(r"^\s*(擬辦|建議|請示)\s*[:：]\s*", "", t).strip()
        body = re.sub(r"\s+", " ", body).strip()
        if body and (not body.endswith("。")):
            body += "。"
        return body
    return t


def _dedupe_clauses(text: str) -> str:
    """
    【AI 去重機制】
    1. 去除同一句內重複子句（如「並於...報局備查」）。
    2. 縮減重複出現的「本中心」、「本廠」等自稱。
    """
    t = (text or "").strip()
    if not t:
        return ""

    # A. 針對「報局備查」類重複子句的物理去重
    parts = [p.strip() for p in re.split(r"[，,]", t) if p.strip()]
    seen = set()
    out = []
    for p in parts:
        # 去除標點與空白後進行語義去重
        key = re.sub(r"[\s，。、]", "", p)
        # 針對「並於115年2月26日前報局備查」此類特徵進行物理去重
        if "報局備查" in key or "報部備查" in key:
            if "備查" in str(seen): continue 
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    
    # 組合
    t = "，".join(out).strip()
    if not t.endswith("。") and any(p.endswith("。") for p in parts):
        t += "。"

    # B. 針對自稱詞（本中心/本廠）在同一段落過度頻繁出現的壓縮邏輯
    # 邏輯：在一句（以句號隔開）中，若已出現過自稱，後續重複出現則嘗試刪除或代換
    res = re.split(r"([。！])", t)
    final_sentences = []
    
    # 定義自稱詞集合
    self_refs = ["本中心", "本廠", "本局", "本部", "本處", "本所", "本會", "本組", "本分局", "本單位"]
    
    i = 0
    while i < len(res):
        s = res[i]
        punc = res[i+1] if i+1 < len(res) else ""
        
        # 針對每一句，如果出現兩次以上的自稱，只保留第一個
        for ref in self_refs:
            if s.count(ref) > 1:
                # 找到第一個出現的位置，其餘刪除
                parts_ref = s.split(ref)
                s = parts_ref[0] + ref + "".join(parts_ref[1:])
        
        final_sentences.append(s + punc)
        i += 2
        
    return "".join(final_sentences).strip()


def _normalize_action_points(action_text: str, max_points: int = 2) -> str:
    """
    擬辦後置規則：
    1) 若為條列點次，最多保留前 2 點。
    2) 每點內去除重複子句。
    """
    t = (action_text or "").strip()
    if not t:
        return ""

    # Support both "(一)" and "一、" styles.
    marks = re.findall(r"\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、", t)
    if not marks:
        return _dedupe_clauses(t)

    if re.search(r"[一二三四五六七八九十]+、", t):
        rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
        pts2: list[tuple[str, str]] = []
        for ln in rows:
            m = re.match(r"^([一二三四五六七八九十]+)、\s*(.+)$", ln)
            if m:
                pts2.append((f"{m.group(1)}、", _dedupe_clauses(m.group(2))))
        if pts2:
            pts2 = pts2[: max(1, int(max_points))]
            return "\n".join([f"{m} {b}".strip() for m, b in pts2]).strip()

    tokens = re.split(r"(\([一二三四五六七八九十]+\))", t)
    pts: list[tuple[str, str]] = []
    i = 1
    while i < len(tokens):
        mark = (tokens[i] or "").strip()
        body = (tokens[i + 1] if i + 1 < len(tokens) else "").strip()
        if mark:
            pts.append((mark, _dedupe_clauses(body)))
        i += 2

    if not pts:
        return _dedupe_clauses(t)

    pts = pts[: max(1, int(max_points))]
    return "\n".join([f"{m} {b}".strip() for m, b in pts]).strip()


def _is_single_point_action(action_text: str) -> bool:
    t = (action_text or "").strip()
    if not t:
        return False
    # Count only leading list markers per line; continuation lines are not new points.
    marker_lines = re.findall(
        r"(?m)^\s*(?:\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、)\s*",
        t,
    )
    if len(marker_lines) >= 2:
        return False
    if len(marker_lines) == 1:
        return True
    marks = re.findall(r"\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、", t)
    if len(marks) >= 2:
        return False
    return True


def _check_quality_gate_readonly(
    *,
    explain_text: str,
    action_text: str,
    fixed_quote: str,
) -> dict:
    """
    Stage-1 integration: read-only quality gate check.
    Does not block output; only returns pass/fail details for logging/observability.
    """
    explain = (explain_text or "").strip()
    action = (action_text or "").strip()
    quote = (fixed_quote or "").strip()
    violations: list[str] = []

    rows = [ln.strip() for ln in explain.splitlines() if ln.strip()]
    first_line = rows[0] if rows else ""
    explain_joined = "\n".join(rows)

    if quote and quote not in first_line:
        violations.append("Q1_FIXED_QUOTE_NOT_IN_POINT1")

    opinion_rows = [ln for ln in rows if "研處意見" in ln]
    if len(opinion_rows) != 1:
        violations.append("Q3_RESEARCH_OPINION_COUNT_INVALID")
    elif rows and rows[-1] != opinion_rows[0]:
        violations.append("Q3_RESEARCH_OPINION_NOT_LAST")

    has_request_excerpt = any(("針對「" in ln or '針對"' in ln) for ln in rows)
    if not has_request_excerpt:
        violations.append("Q2_REQUEST_EXCERPT_MISSING")

    banned = ("請照辦", "請查照", "務請", "請辦理")
    if any(x in explain_joined or x in action for x in banned):
        violations.append("Q5_BANNED_COMMAND_TONE")

    if _is_single_point_action(action) and "一、" in action:
        violations.append("Q6_SINGLE_ACTION_NUMBERED")

    return {
        "mode": "readonly",
        "passed": len(violations) == 0,
        "violations": violations,
    }


def _reduce_explain_point12_overlap(explain_text: str) -> str:
    """
    說明一/二去重策略：
    - 說明一：保留完整法源（日期/字號/奉/依）。
    - 說明二：若重複完整法源片段，改為「依前揭字號」並保留任務內容。
    """
    t = (explain_text or "").strip()
    if not t:
        return ""
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if len(rows) < 2:
        return t

    def _body(line: str) -> str:
        return re.sub(r"^\s*[一二三四五六七八九十]+、\s*", "", line).strip()

    b1 = _body(rows[0])
    b2 = _body(rows[1])
    if not b1 or not b2:
        return t

    # Extract long legal-reference-like segment from point1.
    ref_m = re.search(r"(民國.*?字第.*?號[令函]?|字第.*?號[令函]?)", b1)
    ref = (ref_m.group(1) if ref_m else "").strip()

    # If point2 duplicates legal reference, compress it.
    if ref and ref in b2:
        b2 = b2.replace(ref, "前揭字號")
    b2 = re.sub(r"依據?\s*前揭字號", "依前揭字號", b2)
    b2 = re.sub(r"依\s*前揭字號", "依前揭字號", b2)

    # If still too similar, force point2 to avoid legal-reference clone.
    k1 = re.sub(r"[\s，。、；：:（）()]", "", b1)
    k2 = re.sub(r"[\s，。、；：:（）()]", "", b2)
    if k1 and k2 and (k1 in k2 or k2 in k1):
        b2 = re.sub(r"(民國.*?號[令函]?|字第.*?號[令函]?)", "前揭字號", b2)
        if not b2.startswith("依前揭字號"):
            b2 = f"依前揭字號，{b2}".strip("，")

    # 去除法源克隆後，若說明二不再具有任務必要語意，直接刪除
    b2_clean = re.sub(r"(依前揭字號[，,、]?)", "", b2)
    b2_clean = re.sub(r"(前揭字號[，,、]?)", "", b2_clean)
    b2_clean = re.sub(r"(民國.*?號[令函]?|字第.*?號[令函]?)", "", b2_clean)
    b2_clean = re.sub(r"[，。、；：:（）()\s]", "", b2_clean)
    task_kw = ("辦理", "執行", "完成", "提報", "管制", "宣導", "查核", "整備", "盤點", "回報", "期限", "時限", "對象", "範圍")
    has_task_semantics = any(k in b2 for k in task_kw)
    pure_ref_patterns = (
        "依第一點",
        "依前揭",
        "前揭字號",
        "如附呈",
        "奉前揭",
    )
    is_pure_reference_sentence = any(p in b2 for p in pure_ref_patterns) and (len(b2_clean) < 20)
    if (not has_task_semantics) or len(b2_clean) < 10 or is_pure_reference_sentence:
        del rows[1]
        return "\n".join(rows).strip()

    rows[1] = re.sub(r"^\s*[一二三四五六七八九十]+、\s*.*$", f"二、{b2}", rows[1])
    # 重新編號，避免刪除後號次斷裂
    marks = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    out = []
    for i, ln in enumerate(rows):
        body = re.sub(r"^\s*[一二三四五六七八九十]+、\s*", "", ln).strip()
        if body:
            out.append(f"{marks[i]}、{body}")
    return "\n".join(out).strip()


def _ensure_explain_four_points(explain_text: str) -> str:
    """
    說明段固定補齊四項：
    一、法源依據
    二、案件事實/要求
    三、執行重點/先期摘述
    四、研處意見
    """
    t = (explain_text or "").strip()
    if not t:
        return t
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not rows:
        return t

    def _body(line: str) -> str:
        return re.sub(r"^\s*[一二三四五六七八九十]+、\s*", "", line).strip()

    bodies = [_body(x) for x in rows if _body(x)]
    if not bodies:
        return t

    # Find research-opinion row
    ro_idx = -1
    for i, b in enumerate(bodies):
        if "研處意見" in b:
            ro_idx = i
            break
    if ro_idx < 0:
        bodies.append("研處意見：請就執行計畫、分工期程、回報節點及風險管控措施綜整辦理。")
        ro_idx = len(bodies) - 1

    pre = bodies[:ro_idx]
    ro = bodies[ro_idx]

    while len(pre) < 3:
        if len(pre) == 1:
            pre.append("依前揭字號，就本案辦理對象、範圍及期程完成作業規劃。")
        elif len(pre) == 2:
            pre.append("針對來文要求已先期完成執行重點摘述，並納入後續管制。")
        else:
            pre.append("奉相關來文辦理。")

    pre = pre[:3]
    out_bodies = pre + [ro]
    marks = ["一", "二", "三", "四"]
    return "\n".join([f"{marks[i]}、{out_bodies[i]}" for i in range(4)]).strip()


def _force_action_multiline_and_cap2(action_text: str) -> str:
    """
    擬辦規則：
    1) 最多 2 點
    2) 多點一定換行（每點一行）
    """
    t = (action_text or "").strip()
    if not t:
        return ""

    # Normalize CRLF for parsing.
    s = t.replace("\r\n", "\n")
    pattern = re.compile(r"(\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、)\s*")
    matches = list(pattern.finditer(s))
    if not matches:
        return t

    items: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
        body = s[start:end].strip()
        body = re.sub(r"^\s*(擬辦|建議|請示)\s*[:：]\s*", "", body).strip()
        if not body:
            continue
        items.append(body)
        if len(items) >= 2:
            break

    if not items:
        return t
    if len(items) == 1:
        return items[0]

    return f"一、{items[0]}\n二、{items[1]}"


def _ensure_research_opinion_label(explain_text: str) -> str:
    """
    強制確保說明(四)帶有「研處意見：」字樣。
    例：
    - (四) ：內容  -> (四) 研處意見：內容
    - (四) 內容    -> (四) 研處意見：內容
    """
    t = (explain_text or "").strip()
    if not t:
        return ""

    def _repl(m: re.Match[str]) -> str:
        body = (m.group(1) or "").strip()
        if body.startswith("研處意見"):
            return f"(四) {body}"
        body = re.sub(r"^[:：]\s*", "", body)
        return f"(四) 研處意見：{body}" if body else "(四) 研處意見："

    out = re.sub(
        r"\(四\)\s*([^\n]*)",
        _repl,
        t,
        count=1,
    )
    # If no (四), append one to keep official template complete.
    if "(四)" not in out:
        out = out.rstrip() + "\n(四) 研處意見：請核示。"
    return out


def _enforce_research_opinion_axis(explain_text: str) -> str:
    """
    研處意見強制主軸：
    - 擬依來文辦理
    - 執行計畫
    - 具體作為與因應規劃
    如有窒礙，敘明執行困難與建議處置；
    並避免否定語句與空泛建議。
    """
    t = (explain_text or "").strip()
    if not t:
        return t

    m = re.search(r"\(四\)\s*([^\n]*)", t)
    if not m:
        return t

    body = (m.group(1) or "").strip()
    body = re.sub(r"^研處意見\s*[:：]?\s*", "", body).strip()
    body_norm = re.sub(r"\s+", "", body)

    has_axis = (
        ("擬依來文辦理" in body_norm)
        or ("執行計畫" in body_norm)
        or ("具體作為與因應規劃" in body_norm)
    )
    bad_words = ("不宜", "不建議", "暫緩", "不予", "無法", "俟", "再議", "另案", "原則不同意")
    is_vague = len(body) < 16 or any(w in body for w in bad_words)

    # Keep LLM-authored content; do not overwrite with a fixed template sentence.
    if (not has_axis) or is_vague:
        normalized = body
        if not normalized:
            normalized = "請就執行計畫、具體作為與因應規劃綜整研處意見，並敘明窒礙與建議處置。"
        replacement = f"(四) 研處意見：{normalized}"
        t = re.sub(r"\(四\)\s*[^\n]*", replacement, t, count=1)

    return t


def _dedupe_explain_points(explain_text: str) -> str:
    t = (explain_text or "").strip()
    if not t:
        return ""
    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    out: list[str] = []
    seen = set()
    kept_norm_bodies: list[str] = []

    def _norm_body(line: str) -> str:
        x = re.sub(r"^\([一二三四五六七八九十]+\)\s*", "", line).strip()
        x = re.sub(r"^[一二三四五六七八九十]+、\s*", "", x).strip()
        x = re.sub(r"^【?擬稿說明第一點固定引述】?\s*[:：]\s*", "", x).strip()
        x = re.sub(r"\s+", "", x)
        x = re.sub(r"[，、。；;:：]", "", x)
        return x

    def _similar(a: str, b: str) -> bool:
        if not a or not b:
            return False
        # If one normalized sentence largely contains the other, treat as duplicate semantics.
        short, long = (a, b) if len(a) <= len(b) else (b, a)
        if short and short in long and (len(short) / max(1, len(long))) >= 0.68:
            return True
        # Token overlap fallback for long near-duplicates.
        sa = set(re.findall(r"[\u4e00-\u9fff]{2,}", a))
        sb = set(re.findall(r"[\u4e00-\u9fff]{2,}", b))
        if sa and sb:
            inter = len(sa & sb)
            union = len(sa | sb)
            return union > 0 and (inter / union) >= 0.72
        return False

    for ln in lines:
        key = _norm_body(ln)
        if key in seen:
            continue
        if any(_similar(key, kept) for kept in kept_norm_bodies):
            continue
        seen.add(key)
        kept_norm_bodies.append(key)
        out.append(ln)
    return "\n".join(out).strip()


def _parse_explain_points(explain_text: str) -> list[str]:
    t = (explain_text or "").strip()
    if not t:
        return []
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    pts: list[str] = []
    for ln in rows:
        m = re.match(r"^(?:\(([一二三四五六七八九十]+)\)|([一二三四五六七八九十]+)、)\s*(.+)$", ln)
        if m:
            pts.append((m.group(3) or "").strip())
        elif pts:
            pts[-1] = f"{pts[-1]} {ln}".strip()
    if not pts and t:
        pts = [t]
    return pts


def _score_explain_point(text: str) -> int:
    s = (text or "").strip()
    if not s:
        return -999
    score = 0
    kw_high = ("依", "據", "主旨", "辦理", "計畫", "作為", "因應", "期程", "分工", "回報", "風險")
    kw_mid = ("附件", "配合", "執行", "督導", "檢核", "盤點", "整備")
    score += sum(3 for k in kw_high if k in s)
    score += sum(1 for k in kw_mid if k in s)
    if re.search(r"(民國|中華民國|\d{3}年|\d{4}年|字第|號)", s):
        score += 4
    if len(s) < 12:
        score -= 3
    return score


def _cap_explain_points_with_evaluation(explain_text: str, max_points: int = 4) -> str:
    """
    說明評核機制：
    - 先保留第一點（通常為依據引述）
    - 其餘依關鍵詞/文號日期訊號評分擇優
    - 最多四點
    - 第(四)點強制為研處意見
    """
    pts = _parse_explain_points(explain_text)
    if not pts:
        pts = ["依來文辦理。"]

    first = pts[0]
    rest = pts[1:]
    rest_scored = sorted(
        [(idx, _score_explain_point(p), p) for idx, p in enumerate(rest)],
        key=lambda x: (x[1], -x[0]),
        reverse=True,
    )

    selected = [first]
    for _idx, _sc, p in rest_scored:
        # 保留研處意見給最後一點，不先塞進前面
        if re.search(r"研處意見", p):
            continue
        selected.append(p)
        if len(selected) >= max(1, max_points - 1):
            break

    # 研處意見固定當最後一點
    opinion = ""
    for p in pts:
        if "研處意見" in p:
            opinion = p
            break
    if not opinion:
        opinion = "研處意見：請依來文與附件事實提出具體執行作為及風險處置。"
    if not opinion.startswith("研處意見"):
        opinion = f"研處意見：{opinion}"
    selected.append(opinion)

    selected = selected[:max(1, max_points)]
    marks = ["一", "二", "三", "四"]
    return "\n".join([f"({marks[i]}) {p}" for i, p in enumerate(selected[:4])]).strip()


def _extract_candidates_from_attachments(attachments_text: str) -> list[str]:
    t = (attachments_text or "").strip()
    if not t:
        return []
    out: list[str] = []
    for raw in t.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^(?:重點|來文重點|來文說明|附件重點)\s*\d+\s*[:：]\s*", "", line).strip()
        if not line:
            continue
        if re.search(r"^【?擬稿說明第一點固定引述】?\s*[:：]", line):
            continue
        if re.search(r"^這是.+的[令函呈]", line):
            continue
        if "研處意見" in line:
            continue
        out.append(line)
    return out


def _compress_action_text(action_text: str, max_points: int = 2) -> str:
    """
    擬辦壓縮：
    - 若為長段落（無點次）則拆句後轉為最多二點
    - 若為點次條列，維持既有最多二點規則
    """
    t = (action_text or "").strip()
    if not t:
        return ""

    # Already itemized: reuse existing limiter.
    if re.search(r"\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、", t):
        return _normalize_action_points(t, max_points=max_points)

    # Long paragraph: pick top 2 meaningful sentences.
    sents = [x.strip() for x in re.split(r"[。；;]\s*", t) if x.strip()]
    if not sents:
        return t

    picked: list[str] = []
    for s in sents:
        if len(s) < 8:
            continue
        if s in picked:
            continue
        picked.append(s)
        if len(picked) >= max(1, int(max_points)):
            break
    if not picked:
        picked = [sents[0]]

    marks = ["一", "二"]
    return "\n".join([f"({marks[i]}) {picked[i]}。".strip() for i in range(min(len(picked), 2))]).strip()


def _is_vague_todo_action_line(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    vague_patterns = (
        r"並?將相關風險與影響.*(評估|研析)",
        r"提出(具體)?(因應|應對)措施",
        r"持續(追蹤|辦理|精進|滾動修正)",
        r"強化(管控|宣導|落實)",
        r"請.*依規定辦理$",
    )
    if any(re.search(p, s) for p in vague_patterns):
        # allow if sentence contains hard execution signals
        if re.search(r"(於|在)\s*\d+\s*(日|小時|分鐘)內|回報|核備|檢附|函送|簽核", s):
            return False
        return True
    return False


def _prune_vague_action_points(action_text: str, max_points: int = 2) -> str:
    t = (action_text or "").strip()
    if not t:
        return ""
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    items: list[tuple[str, str]] = []
    for ln in rows:
        m = re.match(r"^([一二三四五六七八九十]+)、\s*(.+)$", ln)
        if m:
            items.append((m.group(1), m.group(2).strip()))
        else:
            items.append(("", ln))

    kept: list[str] = []
    for _mark, body in items:
        if _is_vague_todo_action_line(body):
            continue
        kept.append(body.rstrip("。") + "。")
        if len(kept) >= max(1, int(max_points)):
            break

    if not kept:
        # fallback: keep first line to avoid empty output
        first = items[0][1] if items else t
        kept = [first.rstrip("。") + "。"]

    marks = ["一", "二"]
    return "\n".join([f"{marks[i]}、{kept[i]}" for i in range(min(len(kept), 2))]).strip()


def _remove_ni_word_in_action(action_text: str) -> str:
    """
    Remove '擬' wording in action content as requested by business rule.
    Keep heading label '擬辦' outside this function.
    """
    t = (action_text or "").strip()
    if not t:
        return ""
    # Common drafting verbs
    t = re.sub(r"擬依", "依", t)
    t = re.sub(r"擬將", "將", t)
    t = re.sub(r"擬於", "於", t)
    t = re.sub(r"如擬", "", t)
    # standalone leading 擬
    t = re.sub(r"(^|[，。；;\s])擬(?=[^\s])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def _merge_explain_with_attachment_candidates(
    explain_text: str,
    attachments_text: str,
    max_points: int = 4,
) -> str:
    """
    將既有點位與候選點位放入同一評分池，再擇優保留至最多四點
    （最後一點保留研處意見）。
    """
    pts = _parse_explain_points(explain_text)
    if not pts:
        pts = ["依來文辦理。"]

    opinion = ""
    body_pts: list[str] = []
    for p in pts:
        if "研處意見" in p and not opinion:
            opinion = p
        else:
            body_pts.append(p)

    candidates = _extract_candidates_from_attachments(attachments_text)
    # Build a unified pool: existing points + candidate points.
    # Keep existing points as part of competition (with a small tie-break boost),
    # not unconditional keep.
    pool: list[tuple[str, int, int, str]] = []
    # origin: "existing" | "candidate", score, ordinal, text
    for i, x in enumerate(body_pts):
        pool.append(("existing", _score_explain_point(x) + 1, i, x))
    for i, x in enumerate(candidates):
        pool.append(("candidate", _score_explain_point(x), i, x))

    deduped: list[tuple[str, int, int, str]] = []
    seen = set()
    for origin, score, ordinal, text in pool:
        k = re.sub(r"\s+", "", text or "")
        if not k or k in seen:
            continue
        seen.add(k)
        deduped.append((origin, score, ordinal, text))

    scored = sorted(
        deduped,
        key=lambda row: (row[1], 1 if row[0] == "existing" else 0, -row[2]),
        reverse=True,
    )
    selected_body: list[str] = []
    for _origin, _score, _ord, text in scored:
        selected_body.append(text)
        if len(selected_body) >= max(1, max_points - 1):
            break

    if not opinion:
        opinion = "研處意見：請依來文與附件事實提出具體執行作為及風險處置。"
    if not opinion.startswith("研處意見"):
        opinion = f"研處意見：{opinion}"

    final_pts = selected_body[: max(1, max_points - 1)] + [opinion]
    marks = ["一", "二", "三", "四"]
    return "\n".join([f"({marks[i]}) {p}" for i, p in enumerate(final_pts[:4])]).strip()


def _normalize_self_honorifics(text: str, self_ref: str, doc_type: str) -> str:
    """
    後置稱謂修正：
    若模型誤把我方寫成「貴中心/貴廠/貴單位」，統一改為我方自稱。
    """
    t = (text or "").strip()
    sref = (self_ref or "").strip()
    if not t or not sref:
        return t

    internal_doc_types = {"sign_memo", "note"}
    if doc_type in internal_doc_types:
        repl = {
            "貴中心": sref,
            "貴廠": sref,
            "貴單位": sref,
        }
    else:
        # 對外文稿保守處理：只修正常見自稱誤植，不大範圍替換貴稱
        repl = {
            "本機關": sref,
        }
    for src, dst in repl.items():
        t = t.replace(src, dst)
    return t


def _convert_incoming_directive_to_internal_narrative(text: str, self_ref: str, doc_type: str) -> str:
    """
    將來文指令語態（如「請中心...」）轉為呈文自述語態（如「本中心將...」）。
    僅套用於內部文種，避免影響對外函稿語氣。
    """
    t = (text or "").strip()
    sref = (self_ref or "").strip()
    if not t or not sref:
        return t

    internal_doc_types = {"sign_memo", "note", "submit_draft"}
    if doc_type not in internal_doc_types:
        return t

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    out: list[str] = []
    for ln in lines:
        x = ln
        # 先把「請中心/請本中心/請本廠...」統一成我方自稱
        x = re.sub(r"請\s*(中心|本中心)", sref, x)
        x = re.sub(r"請\s*(本廠|廠)", sref if sref == "本廠" else "本廠", x)
        x = re.sub(r"請\s*(本單位|單位)", sref if sref == "本單位" else "本單位", x)

        # 句首若為我方自稱 + 動詞，補成「本中心將...」的呈文敘述語態
        x = re.sub(rf"^\s*{re.escape(sref)}\s*(?=[^\s])", f"{sref}將", x)
        x = re.sub(rf"^\s*{re.escape(sref)}將將", f"{sref}將", x)

        # 若仍殘留句首「請」，移除命令語氣（保留內容）
        x = re.sub(r"^\s*請\s*", "", x)

        out.append(x)
    return "\n".join(out).strip()


def _extract_plant_mentions(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    found = re.findall(r"(?:第)?(202|205|209|401)\s*廠", t)
    out: list[str] = []
    for x in found:
        if x not in out:
            out.append(x)
    return out


def _infer_execution_context(
    incoming_text: str,
    stage2_facts_text: str,
    signer_org_code: str,
    signer_self_ref: str,
) -> dict[str, str]:
    blob = "\n".join([incoming_text or "", stage2_facts_text or ""]).strip()
    plants = _extract_plant_mentions(blob)
    signer_code = (signer_org_code or "").strip()
    self_ref = (signer_self_ref or "本單位").strip() or "本單位"

    context = {
        "self_ref": self_ref,
        "incoming_org": "",
        "execution_unit": self_ref,
        "relation": "self_execute",
        "hint": "",
    }

    if "軍備局" in blob:
        context["incoming_org"] = "軍備局"
    elif "國防部" in blob:
        context["incoming_org"] = "國防部"

    if signer_code == "MPC" and plants:
        unit = f"第{plants[0]}廠"
        context["execution_unit"] = unit
        context["relation"] = "supervise_subordinate"
        context["hint"] = f"本案應辦單位為{unit}（本單位之直屬下級）；{self_ref}應採督導/管制語氣，敘明分工、期程與回報節點。"
        return context

    if signer_code in {"202", "205", "209", "401"}:
        own = signer_code
        if plants and plants[0] != own:
            context["execution_unit"] = f"第{plants[0]}廠"
            context["relation"] = "coordinate_peer"
            context["hint"] = f"本案涉及{context['execution_unit']}（同層所屬單位）；請以協調配合語氣敘明執行分工與窗口。"
            return context
        context["execution_unit"] = f"第{own}廠"
        context["relation"] = "self_execute"
        context["hint"] = f"本案應由{self_ref}主辦執行，敘明具體作為、完成期限與回報方式。"
        return context

    if plants:
        context["execution_unit"] = f"第{plants[0]}廠"
        context["relation"] = "delegate_execute"
        context["hint"] = f"本案應辦單位為{context['execution_unit']}；{self_ref}請敘明督辦或協調機制。"
    else:
        context["hint"] = f"本案未辨識明確下級執行單位，請以{self_ref}主辦執行語氣敘明具體作為與期程。"
    return context


def _apply_execution_context_to_action(action_text: str, context: dict[str, str], doc_type: str) -> str:
    t = (action_text or "").strip()
    if not t:
        return t
    if doc_type not in {"sign_memo", "note", "submit_draft"}:
        return t

    relation = (context.get("relation") or "").strip()
    self_ref = (context.get("self_ref") or "本單位").strip() or "本單位"
    unit = (context.get("execution_unit") or "").strip()

    if relation == "supervise_subordinate" and unit:
        # Internal sign memo should name the execution unit explicitly, not ambiguous honorifics.
        t = re.sub(r"(貴單位|該單位|受文單位)", unit, t)
        t = re.sub(rf"{re.escape(unit)}{re.escape(unit)}", unit, t)
    else:
        return t

    needs_supervise = not re.search(r"(督導|督辦|督促)", t)
    needs_control = not re.search(r"(管制|追蹤|列管)", t)
    if not (needs_supervise or needs_control):
        return t

    if _is_single_point_action(t):
        lead = f"{self_ref}督導{unit}依來文事項執行"
        if needs_control:
            lead += "，並管制辦理進度與成果回報"
        if not t.startswith(lead):
            t = f"{lead}；{t}".strip("；")
        return t

    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not rows:
        return t
    first = rows[0]
    body = re.sub(r"^[一二三四五六七八九十]+、\s*", "", first).strip()
    prefix = f"{self_ref}督導{unit}依來文事項執行"
    if needs_control:
        prefix += "，並管制辦理進度與成果回報"
    rows[0] = re.sub(r"^[一二三四五六七八九十]+、\s*.+$", f"一、{prefix}。", first) if body else f"一、{prefix}。"
    return "\n".join(rows).strip()


def _action_fallback_from_current_case(
    source_text: str,
    self_ref: str,
    context: dict[str, str],
) -> str:
    relation = (context.get("relation") or "").strip()
    unit = (context.get("execution_unit") or "").strip()
    sref = (self_ref or "本單位").strip() or "本單位"
    if relation == "supervise_subordinate" and unit:
        return f"{sref}督導{unit}依來文事項執行，並管制辦理進度與成果回報。"

    cands = _extract_candidates_from_attachments(source_text)
    if cands:
        top = (cands[0] or "").strip().rstrip("。")
        if top:
            return f"{sref}依來文及附件重點辦理{top}，並管制執行進度與成果回報。"
    return f"{sref}依來文及附件重點辦理，並管制執行進度與成果回報。"


def _sanitize_action_grounding(
    action_text: str,
    source_text: str,
    self_ref: str,
    context: dict[str, str],
    max_points: int = 2,
) -> str:
    """
    Prevent cross-case contamination:
    keep only action lines grounded in current incoming/facts corpus,
    otherwise rebuild from current-case fallback.
    """
    t = (action_text or "").strip()
    src = (source_text or "").strip()
    if not t:
        return _action_fallback_from_current_case(src, self_ref, context)

    # Build a compact lexicon from current-case source.
    lex = []
    seen = set()
    for tok in re.findall(r"[\u4e00-\u9fff]{2,8}|\d{2,4}年\d{1,2}月\d{1,2}日|\d{6,}", src):
        x = (tok or "").strip()
        if len(x) < 2:
            continue
        if x in seen:
            continue
        seen.add(x)
        lex.append(x)
        if len(lex) >= 180:
            break

    whitelist = ("依來文", "辦理", "執行", "分工", "期程", "回報", "督導", "管制", "配合", "整備")

    def _grounded(line: str) -> bool:
        body = re.sub(r"^[一二三四五六七八九十]+、\s*", "", (line or "").strip())
        if not body:
            return False
        hit = 0
        for k in lex:
            if k and k in body:
                hit += 1
                if hit >= 2:
                    return True
        # allow concise managerial lines if they contain at least one source token + known action verbs
        if hit >= 1 and any(w in body for w in whitelist):
            return True
        return False

    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not rows:
        rows = [t]
    kept = [ln for ln in rows if _grounded(ln)]
    if not kept:
        return _action_fallback_from_current_case(src, self_ref, context)
    return "\n".join(kept[: max(1, int(max_points))]).strip()


def _normalize_target_honorifics(text: str, doc_type: str) -> str:
    """
    Normalize recipient-side honorifics by document role.
    Internal sign/note and external drafts use different audience conventions.
    """
    t = (text or "").strip()
    if not t:
        return ""
    internal_doc_types = {"sign_memo", "note"}
    if doc_type in internal_doc_types:
        repl = {
            "大局": "軍備局",
            "鈞局": "軍備局",
            "報大局": "報軍備局",
            "報鈞局": "報軍備局",
        }
        for src, dst in repl.items():
            t = t.replace(src, dst)
    else:
        # External-facing drafts should avoid internal superior honorifics.
        t = t.replace("大局", "軍備局").replace("鈞局", "軍備局")
    return t


def _formalize_analysis_markers(text: str) -> str:
    """
    將口語分析模板改為正式書面語，避免成稿出現
    「必要性在於／風險在於／影響在於」。
    """
    t = (text or "").strip()
    if not t:
        return ""

    # 第一層：將「在於」分析模板改為較正式公文語
    t = re.sub(r"必要性在於", "就必要性而言，", t)
    t = re.sub(r"影響在於", "其可能影響為", t)
    t = re.sub(r"風險在於", "其潛在風險為", t)

    # 第二層：若已是舊版替代詞，持續升級為正式用語
    t = re.sub(r"有其必要，", "就必要性而言，", t)
    t = re.sub(r"其影響為", "其可能影響為", t)
    t = re.sub(r"其風險為", "其潛在風險為", t)
    return t


def _fallback_subject_from_text(draft_text: str, default: str = "（未提供主旨）") -> str:
    t = (draft_text or "").strip()
    if not t:
        return default
    m = re.search(r"主旨\s*[:：]\s*(.+)", t)
    if m:
        return (m.group(1) or "").strip() or default
    first = _first_subject_line(t)
    return (first or "").strip() or default


def _subject_to_single_line(subject_text: str) -> str:
    """
    Keep full subject content while normalizing wrapped lines into one line.
    Avoid truncation caused by taking only the first line.
    """
    s = _safe_str(subject_text).strip()
    if not s:
        return ""
    parts = [x.strip() for x in s.splitlines() if x and x.strip()]
    if not parts:
        return ""
    out = " ".join(parts)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _sanitize_stage1_points_for_stage2(attachments_text: str) -> str:
    """
    Stage isolation contract:
    - Stage1(parse) may contain system/helper rows for display.
    - Stage2(generate) only consumes factual points.
    """
    t = (attachments_text or "").strip()
    if not t:
        return ""
    out: list[str] = []
    for raw in t.splitlines():
        line = (raw or "").strip()
        if not line:
            continue
        line = re.sub(r"^(?:重點|來文重點|來文說明|附件重點)\s*\d+\s*[:：]\s*", "", line).strip()
        if not line:
            continue
        if re.search(r"^【?擬稿說明第一點固定引述】?\s*[:：]", line):
            continue
        if re.search(r"^這是.+（層級|這是.+的[令函呈]", line):
            continue
        if re.search(r"^(擬辦|建議|請示|研處意見)\s*[:：]", line):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _extract_doc_ref_keys(text: str) -> set[str]:
    t = _safe_str(text)
    if not t:
        return set()
    keys: set[str] = set()
    for m in re.finditer(r"字第\s*([A-Za-z0-9○〇０-９一二三四五六七八九十百千\-]+)\s*號", t):
        k = re.sub(r"\s+", "", _safe_str(m.group(1)))
        if k:
            keys.add(f"DOC:{k}")
    for m in re.finditer(r"通(?:電資)?通報\s*([0-9]{5,})\s*號", t):
        k = re.sub(r"\s+", "", _safe_str(m.group(1)))
        if k:
            keys.add(f"BUL:{k}")
    return keys


def _is_address_like_fact(text: str) -> bool:
    t = _safe_str(text).strip()
    if not t:
        return False
    if re.search(r"(地址|住址|通訊處)\s*[:：]", t):
        return True
    if re.search(
        r"(?:縣|市).{0,12}(?:鄉|鎮|市|區).{0,12}(?:路|街|大道).{0,12}(?:段)?(?:.{0,8}(?:巷|弄))?.{0,12}[0-9０-９]+號",
        t,
    ):
        return True
    if (
        re.search(r"(?:台|臺|新北|桃園|新竹|苗栗|台中|臺中|彰化|南投|雲林|嘉義|台南|臺南|高雄|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).{0,12}(?:縣|市)", t)
        and re.search(r"(?:路|街|大道|段|巷|弄).{0,12}[0-9０-９]+號", t)
    ):
        return True
    return False


def _is_speed_level_like_fact(text: str) -> bool:
    t = _safe_str(text).strip()
    if not t:
        return False
    if re.search(r"(速別|速件|最速件|普通件)\s*[:：]", t):
        return True
    if re.match(r"^(最速件|速件|普通件)$", t):
        return True
    return False


def _sanitize_stage2_facts(facts: Any, incoming_text: str = "") -> str:
    if not isinstance(facts, list):
        return ""
    anchor_keys = _extract_doc_ref_keys(incoming_text)
    out: list[str] = []
    for x in facts:
        line = _safe_str(x).strip()
        if not line:
            continue
        line = re.sub(r"^(?:重點|來文重點|來文說明|附件重點)\s*\d+\s*[:：]\s*", "", line).strip()
        if not line:
            continue
        if re.search(r"^【?擬稿說明第一點固定引述】?\s*[:：]", line):
            continue
        if re.search(r"^這是.+（層級|這是.+的[令函呈]", line):
            continue
        if re.search(r"^(擬辦|建議|請示|研處意見)\s*[:：]", line):
            continue
        if _is_address_like_fact(line):
            continue
        if _is_speed_level_like_fact(line):
            continue
        # Cross-case guard: when incoming doc refs are known, drop facts carrying other case refs.
        line_keys = _extract_doc_ref_keys(line)
        if anchor_keys and line_keys and anchor_keys.isdisjoint(line_keys):
            continue
        out.append(line)
    return "\n".join(out).strip()


def _remove_non_owner_obligations(text: str) -> str:
    """
    Remove obligations that are directed to external/global recipients,
    not the current handling unit's own responsibilities.
    """
    t = _safe_str(text).strip()
    if not t:
        return ""
    out = t
    patterns = [
        r"全軍連級以上單位應[^，。；;\n]*",
        r"各(?:級)?單位應[^，。；;\n]*",
        r"受文單位應[^，。；;\n]*",
        r"所屬單位應[^，。；;\n]*",
    ]
    for p in patterns:
        out = re.sub(p, "", out)
    out = re.sub(r"[，,、]{2,}", "，", out)
    out = re.sub(r"^[，,、\s]+", "", out)
    out = re.sub(r"[，,、\s]+$", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _extract_fixed_quote_from_stage2_facts(facts: Any) -> str:
    if not isinstance(facts, list):
        return ""
    for x in facts:
        line = _safe_str(x).strip()
        if not line:
            continue
        m = re.search(r"^(?:【?擬稿說明第一點固定引述】?)\s*[:：]\s*(.+)$", line)
        if not m:
            m = re.search(r"^(?:擬稿說明第一點固定引述)\s*[:：]\s*(.+)$", line)
        if m:
            return (m.group(1) or "").strip()
    return ""


def _extract_subject_from_requirement(requirement: str) -> str:
    t = (requirement or "").strip()
    if not t:
        return ""
    m = re.search(r"主旨\s*[:：]\s*(.+)", t)
    if m:
        return (m.group(1) or "").strip()
    return ""


def _force_explain_first_quote(explain_text: str, fixed_quote: str) -> str:
    def _norm_for_compare(s: str) -> str:
        x = (s or "").strip()
        x = re.sub(r"^【?擬稿說明第一點固定引述】?\s*[:：]\s*", "", x)
        x = x.replace("（", "(").replace("）", ")")
        x = x.replace("，", ",").replace("。", ".").replace("：", ":")
        x = re.sub(r"[\s,，。.:：;；()（）\"'「」『』、]", "", x)
        return x

    t = (explain_text or "").strip()
    q = (fixed_quote or "").strip()
    if not q:
        return t
    if not t:
        return f"一、{q}"
    # Remove duplicated same quote in other points.
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    cleaned: list[str] = []
    q_norm = _norm_for_compare(q)
    for ln in lines:
        body = re.sub(r"^(?:\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、)\s*", "", ln).strip()
        body_norm = _norm_for_compare(body)
        if q_norm and q_norm in body_norm:
            continue
        cleaned.append(body)
    marks = ["一", "二", "三", "四"]
    pts = [q] + cleaned
    pts = pts[:4]
    return "\n".join([f"{marks[i]}、{pts[i]}" for i in range(len(pts))]).strip()


def _convert_ordinal_parentheses_to_cn(text: str) -> str:
    """
    Convert leading "(一) xxx" to "一、xxx" for official style consistency.
    """
    out = []
    for raw in (text or "").splitlines():
        line = (raw or "").rstrip()
        line = re.sub(r"^\s*\(([一二三四五六七八九十]+)\)\s*", r"\1、", line)
        out.append(line)
    return "\n".join(out).strip()


def _normalize_leading_ordinal_duplicates(text: str) -> str:
    """
    移除每行開頭重複點次（例：二、二、... / 二、(二)...），僅保留第一個點次。
    """
    out = []
    for raw in (text or "").splitlines():
        line = (raw or "").rstrip()
        m = re.match(
            r"^\s*((?:(?:\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、)\s*)+)(.+)$",
            line,
        )
        if not m:
            out.append(line)
            continue

        lead = m.group(1) or ""
        body = (m.group(2) or "").strip()
        tokens = re.findall(r"\([一二三四五六七八九十]+\)|[一二三四五六七八九十]+、", lead)
        if len(tokens) <= 1:
            out.append(line)
            continue

        first = tokens[0]
        first = re.sub(r"^\(([一二三四五六七八九十]+)\)$", r"\1、", first)
        out.append(f"{first}{body}")
    return "\n".join(out).strip()


def _dedupe_research_opinion_points(explain_text: str) -> str:
    """
    若說明中出現多個「研處意見」，僅保留最後一個，避免重複段落。
    """
    t = (explain_text or "").strip()
    if not t:
        return t
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not rows:
        return t

    opinion_idx = [i for i, ln in enumerate(rows) if "研處意見" in ln]
    if len(opinion_idx) <= 1:
        return t

    keep = opinion_idx[-1]
    out = [ln for i, ln in enumerate(rows) if ("研處意見" not in ln) or (i == keep)]
    return "\n".join(out).strip()


def _tighten_explain_points(explain_text: str, max_len: int = 72) -> str:
    """
    壓縮說明每點字數，避免生成結果過於冗長。
    """
    t = (explain_text or "").strip()
    if not t:
        return t
    out: list[str] = []
    for ln in [x.strip() for x in t.splitlines() if x.strip()]:
        m = re.match(r"^([一二三四五六七八九十]+)、\s*(.+)$", ln)
        if not m:
            out.append(ln)
            continue
        mark, body = m.group(1), m.group(2).strip()
        if len(body) > max_len:
            # Prefer first sentence/chunk to keep key action clear.
            chunks = [c.strip() for c in re.split(r"[。；;]", body) if c.strip()]
            if chunks:
                body = chunks[0]
            if len(body) > max_len:
                body = body[:max_len].rstrip("，、 ")
            body = body.rstrip("。") + "。"
        out.append(f"{mark}、{body}")
    return "\n".join(out).strip()


def _renumber_explain_ordinals(explain_text: str, max_points: int = 4) -> str:
    """
    說明點次重新連號，避免出現一、二、四、等跳號情況。
    """
    t = (explain_text or "").strip()
    if not t:
        return t
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not rows:
        return t

    bodies: list[str] = []
    for ln in rows:
        m = re.match(r"^[一二三四五六七八九十]+、\s*(.+)$", ln)
        if m:
            bodies.append((m.group(1) or "").strip())
        elif bodies:
            bodies[-1] = f"{bodies[-1]} {ln}".strip()
        else:
            bodies.append(ln)

    bodies = bodies[: max(1, int(max_points))]
    marks = ["一", "二", "三", "四"]
    return "\n".join([f"{marks[i]}、{bodies[i]}" for i in range(min(len(bodies), 4))]).strip()


def _prune_fragmented_explain_points(
    explain_text: str,
    source_facts_text: str,
    max_points: int = 4,
) -> str:
    """
    Remove non-sentence / overly-short explain points in post-processing.
    Keep point1(quote) and research-opinion point.
    """
    t = (explain_text or "").strip()
    if not t:
        return t
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    pts: list[str] = []
    for ln in rows:
        m = re.match(r"^[一二三四五六七八九十]+、\s*(.+)$", ln)
        if m:
            pts.append((m.group(1) or "").strip())
        elif pts:
            pts[-1] = f"{pts[-1]} {ln}".strip()
        else:
            pts.append(ln)

    if not pts:
        return t

    out: list[str] = []
    for i, p in enumerate(pts):
        body = (p or "").strip()
        if not body:
            continue
        # keep first quote point and research-opinion point untouched
        if i == 0 or ("研處意見" in body):
            out.append(body)
            continue
        pure = re.sub(r"^研處意見\s*[:：]\s*", "", body).strip()
        # Too short / phrase-like fragments should be dropped.
        is_fragment = (
            len(pure) < 12
            or pure.endswith("辦理")
            or pure.endswith("辦理。")
            or bool(re.fullmatch(r"(依來文辦理|依案辦理|遵照辦理)[。\.]?", pure))
        )
        if is_fragment:
            continue
        out.append(body)

    if len(out) < 2:
        # backfill from current-case facts to avoid over-pruning
        for cand in _extract_candidates_from_attachments(source_facts_text):
            c = (cand or "").strip()
            if len(c) < 14:
                continue
            if any(c in x or x in c for x in out):
                continue
            out.insert(1 if out else 0, c.rstrip("。") + "。")
            if len(out) >= 2:
                break

    out = out[: max(1, int(max_points))]
    marks = ["一", "二", "三", "四"]
    return "\n".join([f"{marks[i]}、{out[i]}" for i in range(min(len(out), 4))]).strip()


def _ensure_research_opinion_last_cn(explain_text: str, max_points: int = 4) -> str:
    """
    Force '研處意見' to be the last point in 說明 with Chinese ordinals.
    """
    t = (explain_text or "").strip()
    if not t:
        return ""
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    pts: list[str] = []
    for ln in rows:
        m = re.match(r"^[一二三四五六七八九十]+、\s*(.+)$", ln)
        if m:
            pts.append((m.group(1) or "").strip())
        elif pts:
            pts[-1] = f"{pts[-1]} {ln}".strip()
        else:
            pts.append(ln)

    normal: list[str] = []
    opinion = ""
    for p in pts:
        if ("研處意見" in p) and (not opinion):
            opinion = p
        else:
            normal.append(p)
    if not opinion:
        opinion = "研處意見：請依來文與附件事實提出具體執行作為及風險處置。"
    if not opinion.startswith("研處意見"):
        opinion = f"研處意見：{opinion}"
    # Reject overly-short / empty-formula opinion.
    body = re.sub(r"^研處意見\s*[:：]\s*", "", opinion).strip()
    if len(body) < 18 or re.fullmatch(r"(請核示|請鑒核|如擬|敬請核示)[。\.]?", body):
        opinion = "研處意見：請依來文與附件事實提出具體執行作為及風險處置。"
    # Hard ban wording in research-opinion clause.
    opinion = re.sub(r"請核示[。\.]?", "", opinion).strip()
    opinion = re.sub(r"[，,、\s]+$", "", opinion)
    if not opinion.endswith("。"):
        opinion += "。"

    out_pts = normal[: max(1, int(max_points)) - 1] + [opinion]
    marks = ["一", "二", "三", "四"]
    return "\n".join([f"{marks[i]}、{out_pts[i]}" for i in range(min(len(out_pts), 4))]).strip()


def _extract_incoming_request_fact(source_facts_text: str) -> str:
    """
    Prefer a concrete incoming request/requirement sentence from parsed facts.
    """
    facts = _extract_candidates_from_attachments(source_facts_text)
    if not facts:
        return ""

    req_patterns = (
        r"(請|務請|希照|應|須|應即|應於|應遵照|辦理|執行|查照|落實|完成|回報|提報|備查)",
    )
    for f in facts:
        s = (f or "").strip()
        if len(s) < 10:
            continue
        if "研處意見" in s:
            continue
        if any(re.search(p, s) for p in req_patterns):
            return s.rstrip("。")

    # Fallback: first meaningful fact.
    for f in facts:
        s = (f or "").strip()
        if len(s) >= 12 and "研處意見" not in s:
            return s.rstrip("。")
    return ""


def _neutralize_incoming_directive_phrases(text: str) -> str:
    """
    Remove/normalize incoming expectation wording (e.g. 請照辦) into neutral factual phrasing.
    """
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"(，|、)?\s*請照辦\s*", " ", s)
    s = re.sub(r"(，|、)?\s*請(?:查照|辦理|配合辦理)\s*", " ", s)
    s = re.sub(r"(，|、)?\s*務請\s*", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" ，、。")
    return s


def _inject_request_excerpt_to_explain_mid(explain_text: str, source_facts_text: str, max_points: int = 4) -> str:
    """
    Put request excerpt in explain point 2 or 3 (before research-opinion point).
    """
    pts = _parse_explain_points(explain_text)
    if not pts:
        return explain_text

    req = _extract_incoming_request_fact(source_facts_text)
    if not req:
        return explain_text

    req_clean = _neutralize_incoming_directive_phrases(req)
    req_line = f"針對「{req_clean or req}」先期完成需求摘述與執行重點對應。"

    # Already present -> keep.
    joined = re.sub(r"\s+", "", " ".join(pts))
    if re.sub(r"\s+", "", req) in joined or "針對「" in joined:
        return explain_text

    opinion_idx = None
    for i, p in enumerate(pts):
        if "研處意見" in p:
            opinion_idx = i
            break

    # target position: point2, or point3 when point2 already occupied by fixed quote/body.
    insert_at = 1 if len(pts) <= 2 else 2
    if opinion_idx is not None:
        insert_at = min(insert_at, opinion_idx)

    pts.insert(insert_at, req_line)

    # Cap points, but keep research-opinion if exists.
    if len(pts) > max(1, int(max_points)):
        if opinion_idx is not None:
            opinion_body = None
            for p in pts:
                if "研處意見" in p:
                    opinion_body = p
                    break
            body = [p for p in pts if "研處意見" not in p]
            body = body[: max(1, int(max_points)) - 1]
            pts = body + ([opinion_body] if opinion_body else [])
        else:
            pts = pts[: max(1, int(max_points))]

    marks = ["一", "二", "三", "四"]
    return "\n".join([f"({marks[i]}) {pts[i]}" for i in range(min(len(pts), 4))]).strip()


def _build_dynamic_research_opinion(source_facts_text: str, incoming_level: str = "", self_ref: str = "本單位") -> str:
    facts = _extract_candidates_from_attachments(source_facts_text)
    picked: list[str] = []
    for f in facts:
        s = (f or "").strip()
        if not s:
            continue
        if len(s) < 12:
            continue
        if re.search(r"(研處意見|擬辦|請核示|請鑒核)", s):
            continue
        s2 = _neutralize_incoming_directive_phrases(s.rstrip("。"))
        s2 = _remove_non_owner_obligations(s2)
        if not s2:
            continue
        picked.append(s2)
        if len(picked) >= 2:
            break
    level = (incoming_level or "").strip().lower()
    sref = (self_ref or "").strip() or "本單位"
    if level in {"from_direct_superior", "from_superior", "superior"}:
        relation_clause = "依上級來文指示"
    elif level in {"from_peer", "peer"}:
        relation_clause = "依同級協調事項"
    elif level in {"from_subordinate", "subordinate"}:
        relation_clause = "就所屬單位提報事項"
    else:
        relation_clause = "依來文要求"

    if not picked:
        return f"研處意見：{relation_clause}，{sref}將擬定執行分工與期程，落實辦理並管制回報，併就風險事項滾動管控。"
    if len(picked) == 1:
        return f"研處意見：{relation_clause}，{sref}將就{picked[0]}提出具體處置作為，明確分工、期程與回報節點，並同步辦理風險管控。"
    return f"研處意見：{relation_clause}，{sref}將就{picked[0]}及{picked[1]}辦理整備作為，明定分工期程、回報節點及風險管控措施。"


def _ensure_research_opinion_quality(
    explain_text: str,
    source_facts_text: str,
    incoming_level: str = "",
    self_ref: str = "本單位",
) -> str:
    t = (explain_text or "").strip()
    if not t:
        return t
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    out: list[str] = []
    for ln in rows:
        m = re.match(r"^([一二三四五六七八九十]+)、\s*(.+)$", ln)
        if not m:
            out.append(ln)
            continue
        mark, body = m.group(1), m.group(2).strip()
        if "研處意見" in body:
            # Always rewrite by selected case facts to avoid formulaic repetition.
            body = _build_dynamic_research_opinion(
                source_facts_text,
                incoming_level=incoming_level,
                self_ref=self_ref,
            )
            body = _neutralize_incoming_directive_phrases(body)
            body = _remove_non_owner_obligations(body)
            body = re.sub(r"請核示[。\.]?", "", body).strip()
            if not body.endswith("。"):
                body += "。"
            out.append(f"{mark}、{body}")
        else:
            out.append(ln)
    return "\n".join(out).strip()


def _prune_optional_plan_terms_in_research_opinion(explain_text: str) -> str:
    """
    Enforce optional-plan rule:
    if research-opinion line has no concrete plan signals, remove generic
    mentions of 分工/期程/回報節點 to avoid empty formula wording.
    """
    t = (explain_text or "").strip()
    if not t:
        return t
    rows = [ln.strip() for ln in t.splitlines() if ln.strip()]
    out: list[str] = []
    for ln in rows:
        m = re.match(r"^([一二三四五六七八九十]+)、\s*(.+)$", ln)
        if not m:
            out.append(ln)
            continue
        mark, body = m.group(1), m.group(2).strip()
        if "研處意見" not in body:
            out.append(ln)
            continue

        concrete = bool(
            re.search(
                r"(\d{2,4}年\d{1,2}月\d{1,2}日|\d+\s*(日|天|小時|分鐘)內|期限|里程碑|階段|第[一二三四五六七八九十]\s*階段|由.+(單位|廠|處|組)|於.+前)",
                body,
            )
        )
        if not concrete:
            # Remove optional generic clause when no concrete plan is provided.
            body = re.sub(r"[，,；;]?\s*並?視實需補充分工[、，,]期程及回報節點[。\.]?", "", body).strip()
            body = re.sub(r"[，,；;]?\s*分工[、，,]期程及回報節點[。\.]?", "", body).strip()
            body = re.sub(r"[，,；;]?\s*分工[、，,]期程[、，,]?回報節點[。\.]?", "", body).strip()
            body = re.sub(r"\s{2,}", " ", body).strip("，,；; ")
            if not body.endswith("。"):
                body += "。"
        else:
            # Even with concrete signals, remove generic optional-tail wording.
            body = re.sub(r"[，,；;]?\s*並?視實需補充分工[、，,]期程及回報節點[。\.]?", "。", body).strip()
            body = re.sub(r"\s{2,}", " ", body).strip()
            body = re.sub(r"。。+", "。", body)
        out.append(f"{mark}、{body}")
    return "\n".join(out).strip()


def _draft_to_sections_prefer_last_body(draft_text: str) -> Dict[str, str]:
    """
    Parse duplicated section outputs with policy:
    - 主旨：保留第一個（避免後段覆蓋原始主旨）
    - 說明/擬辦：保留最後一個（通常為模型後段收斂版本）
    """
    text = "\n" + (draft_text or "")
    parts = re.split(r"\n\s*(主旨|說明|擬辦|建議|擬辦建議|辦法)\s*[:：]?", text)
    out: Dict[str, str] = {"subject": "", "explain": "", "action": ""}
    current = ""
    map_key = {
        "主旨": "subject",
        "說明": "explain",
        "擬辦": "action",
        "建議": "action",
        "擬辦建議": "action",
        "辦法": "action",
    }
    for part in parts:
        p = (part or "").strip()
        if not p:
            continue
        if p in map_key:
            current = map_key[p]
            continue
        if not current:
            continue
        if current == "subject":
            if not out.get("subject"):
                out["subject"] = p
            continue
        out[current] = p
    return out


@csrf_exempt
@require_node("doc", api=True)
def api_generate(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))
    valid_doc_types = _valid_doc_types_set()

    doc_type = _safe_str(body.get("doc_type")).strip()
    requirement = _safe_str(body.get("requirement")).strip()
    example_ids = body.get("example_ids", []) or []
    reference_text = _safe_str(body.get("reference_text")).strip()
    incoming_text = _safe_str(body.get("incoming_text")).strip()
    # Deprecated in stage-2 strict mode; keep read for compatibility but never use.
    attachments_text = _safe_str(body.get("attachments_text")).strip()
    fixed_quote = _extract_fixed_quote_from_stage2_facts(body.get("stage2_facts"))
    stage2_facts_text = _sanitize_stage2_facts(body.get("stage2_facts"), incoming_text=incoming_text)
    attachments_text_clean = stage2_facts_text
    incoming_level = _safe_str(body.get("incoming_level")).strip().lower()
    discretion = _safe_str(body.get("discretion")).strip().lower()
    risk = _safe_str(body.get("risk")).strip().lower()

    save_as_template = bool(body.get("save_as_template", False))
    draft_to_save = _safe_str(body.get("draft_to_save")).strip()

    if not doc_type or doc_type not in valid_doc_types:
        return JsonResponse({"ok": False, "error": "doc_type is required and must be valid"}, status=400)
    if not isinstance(example_ids, list):
        return JsonResponse({"ok": False, "error": "example_ids must be a list"}, status=400)
    if not requirement and not (save_as_template and draft_to_save):
        return JsonResponse({"ok": False, "error": "requirement is required"}, status=400)
    if not attachments_text_clean:
        return JsonResponse(
            {
                "ok": False,
                "error": "stage2_facts is required",
                "detail": "第二階段僅接受 stage2_facts[]；請先完成重點解析並勾選至少一項。",
            },
            status=400,
        )

    signer_org_code, signer_org_label, signer_self_ref = _resolve_signer_org(request, body)
    execution_context = _infer_execution_context(
        incoming_text=incoming_text,
        stage2_facts_text=attachments_text_clean,
        signer_org_code=signer_org_code,
        signer_self_ref=signer_self_ref,
    )
    
    # 職能背景
    signer_idno = get_login_user_idno(request)
    signer_full_info = get_emp_full_info(signer_idno) if signer_idno else {}

    # fixed_quote is extracted from stage2_facts[] only (stage-isolated contract).

    example_qs = DocumentTemplate.objects.filter(id__in=example_ids, doc_type=doc_type)
    example_qs = _templates_visibility_filter(example_qs, user=user, is_auth=is_auth)
    examples = list(example_qs.values_list("content_text", flat=True))

    prompt = build_prompt_v2(
        doc_type=doc_type,
        requirement=requirement,
        examples=examples,
        reference_text=reference_text,
        incoming_text=incoming_text,
        attachments_text=attachments_text_clean,
        incoming_level=incoming_level,
        discretion=discretion,
        risk=risk,
        signer_org_code=signer_org_code,
        signer_org_label=signer_org_label,
        signer_self_ref=signer_self_ref,
        fixed_quote=fixed_quote,
        signer_full_info=signer_full_info,
        execution_context_hint=execution_context.get("hint", ""),
    )

    try:
        llm = get_chat_model()
        draft_raw = _to_text(llm.invoke(prompt)).strip() or "(模型未回傳內容)"
        
        # 🛡️ 物理後置處理：修正換行與格式
        draft_text = _clean_generated_draft(draft_raw)
        draft_text = _postprocess_official_style(draft_text)
        draft_text = _normalize_self_honorifics(draft_text, signer_self_ref, doc_type)
        draft_text = _normalize_target_honorifics(draft_text, doc_type)
        draft_text = _convert_incoming_directive_to_internal_narrative(draft_text, signer_self_ref, doc_type)
        draft_text = _formalize_analysis_markers(draft_text)
        draft_text = _normalize_subordinate_unit_short_name(draft_text)

        # 分割段落（重複章節時：主旨取第一組；說明/擬辦取最後一組）
        draft_sections = _draft_to_sections_prefer_last_body(draft_text)
        if not any((draft_sections.get("subject"), draft_sections.get("explain"), draft_sections.get("action"))):
            draft_sections = _draft_to_sections(doc_type, draft_text)
        
        # Stage isolation: do not inject stage-1 helper quote into stage-2 sections.
        draft_sections["explain"] = _ensure_research_opinion_label(_safe_str(draft_sections.get("explain")))
        draft_sections["subject"] = _normalize_self_honorifics(_safe_str(draft_sections.get("subject")), signer_self_ref, doc_type)
        draft_sections["explain"] = _normalize_self_honorifics(_safe_str(draft_sections.get("explain")), signer_self_ref, doc_type)
        draft_sections["subject"] = _normalize_target_honorifics(_safe_str(draft_sections.get("subject")), doc_type)
        draft_sections["explain"] = _normalize_target_honorifics(_safe_str(draft_sections.get("explain")), doc_type)
        draft_sections["subject"] = _convert_incoming_directive_to_internal_narrative(
            _safe_str(draft_sections.get("subject")), signer_self_ref, doc_type
        )
        draft_sections["explain"] = _convert_incoming_directive_to_internal_narrative(
            _safe_str(draft_sections.get("explain")), signer_self_ref, doc_type
        )
        draft_sections["subject"] = _formalize_analysis_markers(_safe_str(draft_sections.get("subject")))
        draft_sections["explain"] = _formalize_analysis_markers(_safe_str(draft_sections.get("explain")))
        draft_sections["subject"] = _normalize_subordinate_unit_short_name(_safe_str(draft_sections.get("subject")))
        draft_sections["explain"] = _normalize_subordinate_unit_short_name(_safe_str(draft_sections.get("explain")))
        if not _safe_str(draft_sections.get("subject")).strip():
            draft_sections["subject"] = (
                _extract_subject_from_requirement(requirement)
                or _fallback_subject_from_text(draft_text)
            )
        # 主旨必須單行；合併換行片段，避免只取第一行造成截斷。
        subject_one_line = _subject_to_single_line(_safe_str(draft_sections.get("subject")))
        if subject_one_line:
            draft_sections["subject"] = subject_one_line
        draft_sections["explain"] = _dedupe_explain_points(_safe_str(draft_sections.get("explain")))
        draft_sections["explain"] = _enforce_research_opinion_axis(_safe_str(draft_sections.get("explain")))
        draft_sections["explain"] = _cap_explain_points_with_evaluation(
            _safe_str(draft_sections.get("explain")), max_points=4
        )
        draft_sections["explain"] = _merge_explain_with_attachment_candidates(
            _safe_str(draft_sections.get("explain")),
            attachments_text_clean,
            max_points=4,
        )
        draft_sections["explain"] = _force_explain_first_quote(
            _safe_str(draft_sections.get("explain")),
            fixed_quote,
        )
        draft_sections["explain"] = _inject_request_excerpt_to_explain_mid(
            _safe_str(draft_sections.get("explain")),
            attachments_text_clean,
            max_points=4,
        )
        draft_sections["explain"] = _convert_ordinal_parentheses_to_cn(
            _safe_str(draft_sections.get("explain"))
        )
        draft_sections["explain"] = _ensure_research_opinion_last_cn(
            _safe_str(draft_sections.get("explain")),
            max_points=4,
        )
        draft_sections["explain"] = _ensure_research_opinion_quality(
            _safe_str(draft_sections.get("explain")),
            attachments_text_clean,
            incoming_level=incoming_level,
            self_ref=signer_self_ref,
        )
        draft_sections["explain"] = _prune_optional_plan_terms_in_research_opinion(
            _safe_str(draft_sections.get("explain"))
        )
        draft_sections["explain"] = _normalize_leading_ordinal_duplicates(
            _safe_str(draft_sections.get("explain"))
        )
        draft_sections["explain"] = _dedupe_research_opinion_points(
            _safe_str(draft_sections.get("explain"))
        )
        draft_sections["explain"] = _force_explain_first_quote(
            _safe_str(draft_sections.get("explain")),
            fixed_quote,
        )
        draft_sections["explain"] = _prune_fragmented_explain_points(
            _safe_str(draft_sections.get("explain")),
            attachments_text_clean,
            max_points=4,
        )
        draft_sections["explain"] = _renumber_explain_ordinals(
            _safe_str(draft_sections.get("explain")),
            max_points=4,
        )
        draft_sections["explain"] = _normalize_explain_unit_names_by_point(
            _safe_str(draft_sections.get("explain"))
        )
        draft_sections["explain"] = _reduce_explain_point12_overlap(
            _safe_str(draft_sections.get("explain"))
        )
        draft_sections["explain"] = _ensure_explain_four_points(
            _safe_str(draft_sections.get("explain"))
        )
            
        # 🛡️ 硬性補足：若 LLM 漏掉擬辦段落，嘗試從全文尋找或強行補上
        if not draft_sections.get("action"):
            # 尋找是否有「擬：」開頭的內容
            m_action = re.search(r"\n\s*(?:擬|擬辦|建議)[:：]\s*(.*)$", draft_text, re.S)
            if m_action:
                draft_sections["action"] = m_action.group(1).strip()
            else:
                draft_sections["action"] = _action_fallback_from_current_case(
                    "\n".join([incoming_text, attachments_text_clean, requirement]).strip(),
                    signer_self_ref,
                    execution_context,
                )

        action_text = _compress_action_text(_safe_str(draft_sections.get("action")), max_points=2)
        action_text = _normalize_single_point_action(action_text)
        action_text = _normalize_self_honorifics(action_text, signer_self_ref, doc_type)
        action_text = _normalize_target_honorifics(action_text, doc_type)
        action_text = _convert_incoming_directive_to_internal_narrative(action_text, signer_self_ref, doc_type)
        action_text = _formalize_analysis_markers(action_text)
        action_text = _convert_ordinal_parentheses_to_cn(action_text)
        action_text = _prune_vague_action_points(action_text, max_points=2)
        action_text = _remove_ni_word_in_action(action_text)
        action_text = _force_action_sentence_for_single_point(action_text)
        action_text = _force_action_multiline_and_cap2(action_text)
        action_text = _apply_execution_context_to_action(action_text, execution_context, doc_type)
        action_text = _sanitize_action_grounding(
            action_text,
            "\n".join([incoming_text, attachments_text_clean, requirement]).strip(),
            signer_self_ref,
            execution_context,
            max_points=2,
        )
        action_text = _remove_non_owner_obligations(action_text)
        action_text = _normalize_subordinate_unit_short_name(action_text)
        draft_sections["action"] = action_text

        # 最終合成純文字版，確保換行清晰
        if _is_single_point_action(action_text):
            action_block = f"擬辦： {action_text}"
        else:
            action_block = f"擬辦：\n{action_text}"
        final_text = f"主旨：{draft_sections.get('subject')}\n\n說明：\n{draft_sections.get('explain')}\n\n{action_block}"

        quality_gate = _check_quality_gate_readonly(
            explain_text=_safe_str(draft_sections.get("explain")),
            action_text=action_text,
            fixed_quote=fixed_quote,
        )
        if quality_gate.get("passed"):
            logger.info("[DOC_SKILL_QG][readonly] passed")
        else:
            logger.warning(
                "[DOC_SKILL_QG][readonly] violations=%s",
                ",".join(quality_gate.get("violations", [])),
            )

        return JsonResponse({
            "ok": True,
            "draft_text": final_text,
            "draft_sections": draft_sections,
            "prompt": prompt,
            "meta": {
                "signer_org_code": signer_org_code,
                "signer_org_label": signer_org_label,
                "execution_unit": execution_context.get("execution_unit"),
                "execution_relation": execution_context.get("relation"),
                "quality_gate": quality_gate,
            },
        }, status=200)

    except Exception as e:
        import traceback
        return JsonResponse({"ok": False, "error": str(e), "trace": traceback.format_exc()}, status=500)

