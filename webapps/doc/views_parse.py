# webapps/doc/views_parse.py
from __future__ import annotations

import io
import json
import os
import re
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple, Dict, Any

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from webapps.portal.decorators import require_node
from webapps.llm.llm_factory import get_chat_model
from webapps.doc.utils_login import get_login_user_idno, get_login_user_name, get_login_user_org

# 🛡️ 物理修復：正確從 views_helpers 引入，不再使用不存在的 service 路徑
from webapps.doc.views_helpers import (
    _to_text,
    _extract_text_by_ext,
    _build_attach_focus_prompt,
    _ensure_focus_numbered,
)

from webapps.doc.views_parse_meta import (
    LEVEL_LABEL,
    _load_org_level_map,
    _normalize_org_text,
    _normalize_point_text,
    _strip_point_prefixes,
    _is_non_key_point_text,
    _clean_attachment_text,
    _is_doc_ref_line,
    _is_header_meta_line,
    _pick_header_lines,
    _extract_recipient_candidates,
    _recipient_block_bounds,
    _normalize_header_line,
    _compact_spaced_cjk,
    _extract_header_org_doc_type,
    _extract_specific_org_from_line,
    _infer_org_and_level,
    _extract_doc_meta,
)
from webapps.doc.views_parse_subject import (
    _extract_doc_subject as _extract_doc_subject_ext,
    _extract_doc_subject_fallback as _extract_doc_subject_fallback_ext,
)

def _extract_doc_subject(text: str) -> str:
    return _extract_doc_subject_ext(text, _compact_spaced_cjk)


def _extract_doc_subject_fallback(text: str) -> str:
    return _extract_doc_subject_fallback_ext(text, _compact_spaced_cjk)


def _find_issued_title(text: str) -> str:
    subj = _extract_doc_subject(text)
    m_subj = re.search(r"(?:令發|令頒|頒發|函報|函陳|函送)\s*[「『]?(.*?)[」』]?(?:\s*[乙一]則|，|請照辦|。|$)", subj)
    return m_subj.group(1).strip() if m_subj else ""

def _resolve_writer_identity_local(request: HttpRequest) -> str:
    org = get_login_user_org(request)
    if org == "MPC": return "本中心"
    if org in ["202", "205", "209", "401"]: return "本廠"
    return "本單位"

def _preprocess_incoming_text_local(text: str, from_org: str, self_refer: str, level: str = "") -> str:
    if not text: return ""
    out = text
    target_org_name = re.sub(r"^(受文者|主旨|依主旨)[:：\s]*", "", (from_org or "").strip()) or "對方單位"
    writer_self_aliases = ["本局", "本部", "本廠", "本處", "本中心", "本室", "本所", "本會", "本組", "本分局"]
    for alias in writer_self_aliases:
        if alias != self_refer: out = out.replace(alias, target_org_name)
    
    if level in ("FROM_SUPERIOR", "FROM_DIRECT_SUPERIOR"):
        for hon in ["貴中心", "貴單位", "貴廠", "貴處", "貴局", "貴部", "貴所", "貴會", "貴組", "貴分局"]:
            out = out.replace(hon, self_refer)
    elif level == "FROM_SUBORDINATE":
        for hon in ["鈞局", "鈞部", "鈞廠", "鈞處", "鈞中心", "鈞所", "鈞會", "鈞組", "鈞分局", "大中心", "大部"]:
            out = out.replace(hon, self_refer)
    return out


def _extract_recipient_org(text: str) -> str:
    """
    受文單位擷取（來文檔專用）。
    """
    lines = [_compact_spaced_cjk(x.strip()) for x in _pick_header_lines(text) if (x or "").strip()]
    if not lines:
        return ""

    stop_pat = re.compile(
        r"^(主旨|說明|附件|發文字號|發文日期|檔號|保存年限|密等|速別|地址|電話|傳真|聯絡人|電子信箱)\s*[:：]"
    )
    def _clean_candidate(v: str) -> str:
        t = _compact_spaced_cjk(v or "")
        # If OCR merged multiple fields into one line, trim at next known field key.
        t = re.split(
            r"(?:發文日期|發文字號|主旨|說明|附件|檔號|保存年限|密等|速別)\s*[:：]",
            t,
            maxsplit=1,
        )[0].strip()
        t = re.split(r"[、,，;；]", t, maxsplit=1)[0].strip()
        return t

    for i, raw in enumerate(lines[:40]):
        m = re.match(r"^受\s*文\s*者\s*[:：]\s*(.*)$", raw)
        if not m:
            continue
        inline = _clean_candidate((m.group(1) or "").strip())
        if inline:
            return inline
        for j in range(i + 1, min(i + 6, len(lines))):
            ln = (lines[j] or "").strip()
            if not ln or stop_pat.match(ln) or re.match(r"^[令函呈]$", ln):
                break
            if re.match(r"^.+(?:\s|　)?[令函呈]\s*$", ln):
                break
            if re.match(r"^[一-龥A-Za-z0-9○〇０0]{1,10}\s*[:：]", ln):
                break
            cand = _clean_candidate(ln)
            if cand:
                return cand

    compact_text = _compact_spaced_cjk(text or "")
    m_inline = re.search(r"受\s*文\s*者\s*[:：]\s*([^\r\n]+)", compact_text)
    if m_inline:
        cand = _clean_candidate(m_inline.group(1))
        if cand:
            return cand

    # Fallback: some official docs only expose recipient in 正本 line.
    m_copy = re.search(r"正本\s*[:：]\s*([^\r\n]+)", compact_text)
    if m_copy:
        cand = _clean_candidate(m_copy.group(1))
        if cand:
            return cand
    return ""


def _is_incoming_doc_text(text: str) -> bool:
    """
    來文檔判別：
    - 檔案內容有發文字號、發文日期等欄位，視為來文檔
    - 否則視為附件檔
    """
    t = _compact_spaced_cjk(text or "")
    if not t:
        return False
    score = 0
    if re.search(r"發文日期\s*[:：]", t):
        score += 2
    if re.search(r"發文字號\s*[:：]", t):
        score += 2
    if re.search(r"受\s*文\s*者\s*[:：]", t):
        score += 1
    if re.search(r"主旨\s*[:：]", t):
        score += 1
    return score >= 3


def _split_file_texts_by_kind(
    file_texts: List[Tuple[str, str, str]]
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str, str]]]:
    incoming_docs: List[Tuple[str, str, str]] = []
    attachment_docs: List[Tuple[str, str, str]] = []
    for item in file_texts:
        _name, raw, _clean = item
        if _is_incoming_doc_text(raw):
            incoming_docs.append(item)
        else:
            attachment_docs.append(item)
    if not incoming_docs and file_texts:
        incoming_docs = [file_texts[0]]
        attachment_docs = file_texts[1:]
    return incoming_docs, attachment_docs


def _extract_description_paragraphs(text: str, max_items: int = 8) -> List[str]:
    """
    來文「說明」段落完整擷取（每段合併為完整句段）。
    """
    lines = [_compact_spaced_cjk(x.strip()) for x in (text or "").splitlines() if (x or "").strip()]
    if not lines:
        return []

    start = -1
    for i, ln in enumerate(lines):
        if re.match(r"^說明\s*[:：]?\s*$", ln) or re.match(r"^說明\s*[:：]\s*.+$", ln):
            start = i
            break
    if start < 0:
        return []

    sec_stop = re.compile(r"^(附件|正本|副本|抄送|主旨|受文者|檔號|保存年限)\s*[:：]")
    ord_pat = re.compile(r"^([一二三四五六七八九十百千]+|\d+)\s*[、.．)）]\s*(.*)$")

    out: List[str] = []
    cur = ""

    m_inline = re.match(r"^說明\s*[:：]\s*(.+)$", lines[start])
    if m_inline and (m_inline.group(1) or "").strip():
        cur = (m_inline.group(1) or "").strip()

    for ln in lines[start + 1 :]:
        if sec_stop.match(ln):
            break
        m_ord = ord_pat.match(ln)
        if m_ord:
            if cur:
                out.append(cur.strip())
            cur = (m_ord.group(2) or "").strip()
            continue
        if re.match(r"^第\s*\d+\s*頁", ln):
            continue
        if cur:
            cur = f"{cur} {ln}".strip()
        else:
            cur = ln

    if cur:
        out.append(cur.strip())

    cleaned: List[str] = []
    for x in out:
        t = re.sub(r"\s+", " ", x).strip()
        if t and len(t) >= 4:
            cleaned.append(t)
        if len(cleaned) >= max_items:
            break
    return cleaned


def _extract_numbered_points(summary_text: str) -> List[str]:
    out: List[str] = []
    meta_pat = re.compile(r"^(發文日期|發文字號|來文主旨|主旨)\s*[:：]")
    non_focus_pat = re.compile(
        r"^(附件(?:檔案)?名稱|附件檔名|解密條件(?:或保密期限)?|保密期限|文件總頁數|總頁數|頁數|(?:令的)?地址)\s*[:：]"
    )
    for ln in (summary_text or "").splitlines():
        m = re.match(r"^重點\s*\d+\s*[:：]\s*(.+)$", (ln or "").strip())
        if not m:
            continue
        t = _compact_spaced_cjk((m.group(1) or "").strip())
        if meta_pat.match(t):
            continue
        if non_focus_pat.match(t):
            continue
        if _is_address_like_text(t):
            continue
        if _is_speed_level_like_text(t):
            continue
        if t:
            out.append(t)
    return out


def _extract_doc_ref_ids(text: str) -> List[str]:
    t = _compact_spaced_cjk(text or "")
    if not t:
        return []
    out: List[str] = []
    seen = set()
    for m in re.finditer(r"字第\s*([A-Za-z0-9○〇０-９一二三四五六七八九十百千\-]+)\s*號", t):
        ref = re.sub(r"\s+", "", (m.group(1) or "").strip())
        if not ref or ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _filter_points_by_anchor_doc_no(points: List[str], anchor_doc_no: str) -> List[str]:
    """
    Keep points tied to current incoming doc number.
    If a point contains ref ids but none match anchor_doc_no, drop it as cross-case noise.
    """
    anchor_ids = _extract_doc_ref_ids(anchor_doc_no)
    if not anchor_ids:
        return points or []
    anchor_set = set(anchor_ids)
    out: List[str] = []
    for p in points or []:
        refs = _extract_doc_ref_ids(p)
        if refs and anchor_set.isdisjoint(set(refs)):
            continue
        out.append(p)
    return out


def _is_address_like_text(text: str) -> bool:
    t = _compact_spaced_cjk((text or "").strip())
    if not t:
        return False

    if re.search(r"(地址|住址|通訊處)\s*[:：]", t):
        return True

    # Typical TW address pattern: 縣/市 + 區/鄉/鎮 + 路/街/大道 ... + 號
    if re.search(
        r"(?:縣|市).{0,12}(?:鄉|鎮|市|區).{0,12}(?:路|街|大道).{0,12}(?:段)?(?:.{0,8}(?:巷|弄))?.{0,12}[0-9０-９]+號",
        t,
    ):
        return True

    # Fallback: region marker + road marker + house number marker.
    if (
        re.search(r"(?:台|臺|新北|桃園|新竹|苗栗|台中|臺中|彰化|南投|雲林|嘉義|台南|臺南|高雄|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江).{0,12}(?:縣|市)", t)
        and re.search(r"(?:路|街|大道|段|巷|弄).{0,12}[0-9０-９]+號", t)
    ):
        return True

    return False


def _is_speed_level_like_text(text: str) -> bool:
    t = _compact_spaced_cjk((text or "").strip())
    if not t:
        return False
    if re.search(r"(速別|速件|最速件|普通件)\s*[:：]", t):
        return True
    if re.match(r"^(最速件|速件|普通件)$", t):
        return True
    return False


def _collect_focus_point_candidates(summary_text: str) -> List[str]:
    points: List[str] = []
    skip_regex = [
        r"聯絡電話\s*[:：]", r"檔\s*號\s*[:：]", r"保存年限\s*[:：]", r"承辦人\s*[:：]",
        r"一般公務資訊", r"受文者[:：]", r"【擬稿說明", r"民國\s*\d+\s*年.*[字第].*號",
    ]
    for raw in (summary_text or "").splitlines():
        content = _strip_point_prefixes(raw)
        if len(content) < 6:
            continue
        if _is_non_key_point_text(content):
            continue
        if _is_address_like_text(content):
            continue
        if _is_speed_level_like_text(content):
            continue
        if re.search(r"^(這是.+（層級|【擬稿說明第一點固定引述】)", content):
            continue
        if any(re.search(pat, content) for pat in skip_regex):
            continue
        points.append(content)
    return points


def _extract_attachment_points(
    attachment_docs: List[Tuple[str, str, str]],
    llm,
    *,
    extra_hint: str = "",
    max_points: int = 10,
) -> Tuple[str, List[str]]:
    if not attachment_docs:
        return "", []
    combined = "\n\n".join([x[2] for x in attachment_docs if (x[2] or "").strip()]).strip()
    if not combined:
        return "", []
    prompt = _build_attach_focus_prompt(combined, extra_hint=extra_hint)
    summary_raw = _to_text(llm.invoke(prompt)).strip()
    summary_text = _ensure_focus_numbered(summary_raw, max_points=20)
    summary_text = _postprocess_focus_points(summary_text, max_points=20)
    points = _collect_focus_point_candidates(summary_text)

    def _extract_attachment_title(text: str) -> str:
        """
        從附件原文擷取主標題（優先抓「主旨:」；其次抓第一個非 metadata 行）。
        """
        lines = [(_compact_spaced_cjk(x or "").strip()) for x in (text or "").splitlines() if (x or "").strip()]
        if not lines:
            return ""

        # 0) 正文大標題硬匹配（優先）：...注意事項 / ...要點 / ...規定
        for ln in lines[:220]:
            n = re.sub(r"[\s\u3000]+", "", ln)
            if len(n) < 8 or len(n) > 64:
                continue
            if re.match(r"^(主旨|說明|附件|受文者|發文日期|發文字號|速別|密等|編號)[:：]", n):
                continue
            if re.match(r"^[一二三四五六七八九十]+\s*[、.．:]", n):
                continue
            if re.search(r"(注意事項|要點|規定)$", n):
                return re.sub(r"[,，。．\s]+$", "", n).strip()

        # 1) 主旨行（含 OCR 空白變體）
        for ln in lines[:120]:
            n = re.sub(r"[\s\u3000]+", "", ln)
            if n.startswith("\u4e3b\u65e8\uff1a") or n.startswith("\u4e3b\u65e8:"):
                val = n.split("：", 1)[1] if "：" in n else (n.split(":", 1)[1] if ":" in n else "")
                val = re.sub(r"[,，。．\s]+$", "", val).strip()
                if val:
                    return val

        # 2) fallback：第一個不是 metadata 的行
        meta_heads = (
            "\u53d7\u6587\u6a5f\u95dc", "\u767c\u6587\u65e5\u671f", "\u767c\u6587\u5b57\u865f",
            "\u901f\u5225", "\u5bc6\u7b49", "\u9644\u4ef6", "\u8aaa\u660e",
            "\u53d7\u6587\u8005", "\u6a94\u865f", "\u4fdd\u5b58\u5e74\u9650",
            "\u7de8\u865f", "\u672c\u4ef6", "\u6b63\u672c", "\u526f\u672c", "\u6284\u9001",
        )
        headline_candidates: List[str] = []
        for ln in lines[:160]:
            n = re.sub(r"[\s\u3000]+", "", ln)
            if any(n.startswith(h + "：") or n.startswith(h + ":") for h in meta_heads):
                continue
            if len(n) < 6:
                continue
            # Skip numbered bullets/section markers (一、/(一)/1.)
            if re.match(r"^[一二三四五六七八九十]+\s*[、.．:]", n):
                continue
            if re.match(r"^[\(（][一二三四五六七八九十\d]+[\)）]", n):
                continue
            if re.match(r"^\d+\s*[、.．:]", n):
                continue
            # Prefer headline-like lines: medium length, mostly CJK, no colon.
            cjk_cnt = len(re.findall(r"[\u4e00-\u9fff]", n))
            if cjk_cnt >= 8 and ("：" not in n and ":" not in n) and 8 <= len(n) <= 48:
                headline_candidates.append(n)
                continue
            # Fallback candidate
            headline_candidates.append(n)
        if headline_candidates:
            # Prefer body-title semantics over incoming subject style.
            def _score_title(x: str) -> tuple:
                cjk = len(re.findall(r"[\u4e00-\u9fff]", x))
                has_keyword = 1 if re.search(r"(注意事項|要點|規定|計畫|通報)", x) else 0
                bad_start = 1 if re.match(r"^(呈|奉|本件|請|依據|依)", x) else 0
                # rank: keyword first, then non-bad-start, then CJK count/length
                return (has_keyword, -bad_start, cjk, len(x))

            headline_candidates.sort(key=_score_title, reverse=True)
            picked = headline_candidates[0]
            return re.sub(r"[,，。．\s]+$", "", picked).strip()
        return ""

    title = _extract_attachment_title(combined)
    if title:
        title_key = _normalize_point_text(title)
        if title_key and not any(_normalize_point_text(p) == title_key for p in points):
            points = [title] + points

    return prompt, points[:max_points]


def _format_focus_summary_v3(
    *,
    sender_org: str,
    recipient_org: str,
    doc_date: str,
    doc_no: str,
    doc_subject: str,
    incoming_desc: List[str],
    incoming_point1: str,
    attachment_points: List[str],
    max_incoming_desc: int = 8,
    max_attach: int = 20,
) -> str:
    sender = (sender_org or "").strip() or "未辨識機關"
    recipient = (recipient_org or "").strip() or "未辨識單位"
    date_text = (doc_date or "").strip() or "未辨識"
    no_text = (doc_no or "").strip() or "未辨識"
    subject_text = (doc_subject or "").strip() or "未提供主旨"
    lines: List[str] = [
        f"來文機關: {sender}",
        f"受文機關: {recipient}",
        f"發文日期: {date_text}",
        f"發文字號: {no_text}",
        f"主旨: {subject_text}",
    ]
    for i, p in enumerate((incoming_desc or [])[:max_incoming_desc], 1):
        lines.append(f"說明{i}: {p}")
    if (incoming_point1 or "").strip():
        lines.append(f"擬稿說明第一點固定引述: {incoming_point1.strip()}")
    for i, p in enumerate((attachment_points or [])[:max_attach], 1):
        lines.append(f"附件重點{i}: {p}")
    return "\n".join(lines)

def _inject_org_level_point(
    summary_text: str,
    org: str,
    level: str,
    doc_date: str,
    doc_no: str,
    doc_type: str,
    doc_subject: str,
    full_text_for_search: str = "",
    max_points: int = 20,
) -> str:
    org_clean = re.sub(r"^(受文者|主旨|依主旨)[:：\s]*", "", (org or "").strip())
    org_clean = re.sub(r"\s*[令函簽報]$", "", org_clean).strip()
    # Do NOT override org from full body text; body may contain many unrelated units.
    # Only apply header fallback when org is missing.
    if not org_clean:
        h_org, _ = _extract_header_org_doc_type(full_text_for_search[:1200])
        if h_org:
            org_clean = h_org

    label = LEVEL_LABEL.get(level, "層級未知")
    dt_text = doc_type if doc_type in ("令", "函", "呈") else "函"
    ref_date = re.sub(r"發文日期\s*[:：]\s*", "", (doc_date or "")).replace("中華民國", "民國").replace("民前", "民國").strip()
    ref_no = re.sub(r"發文字號\s*[:：]\s*", "", (doc_no or "")).strip()
    subject_clean = _extract_doc_subject(full_text_for_search) or doc_subject or "（未提供主旨）"
    
    verb = "奉" if level in ("FROM_DIRECT_SUPERIOR", "FROM_SUPERIOR") else "依"
    quote_stmt = f"{verb}{org_clean}{ref_date}{ref_no}{dt_text}辦理(如附呈)。"
    issued_title = _find_issued_title(full_text_for_search)
    if dt_text == "令" and issued_title: quote_stmt = f"{verb}{org_clean}{ref_date}{ref_no}令修頒「{issued_title}」辦理(如附呈)。"

    point1_content = f"【擬稿說明第一點固定引述】：{quote_stmt}"
    point2_content = f"這是{org_clean} （{label}）的{dt_text}，主旨：{subject_clean}"

    points: List[str] = []
    skip_regex = [r"聯絡電話\s*[:：]", r"檔\s*號\s*[:：]", r"保存年限\s*[:：]", r"承辦人\s*[:：]", r"一般公務資訊", r"受文者[:：]", r"【擬稿說明", r"民國\s*\d+\s*年.*[字第].*號"]

    for raw in (summary_text or "").splitlines():
        content = _strip_point_prefixes(raw)
        if len(content) < 6: continue
        if _is_non_key_point_text(content): continue
        if _is_address_like_text(content): continue
        if _is_speed_level_like_text(content): continue
        if re.search(r"^(這是.+（層級|【擬稿說明第一點固定引述】)", content):
            continue
        if any(re.search(pat, content) for pat in skip_regex): continue
        points.append(content)

    final_list: List[str] = [point1_content, point2_content]
    for p in points:
        if not any(_normalize_point_text(p) == _normalize_point_text(prev) for prev in final_list): final_list.append(p)

    return "\n".join([f"重點{i}：{txt}" for i, txt in enumerate(final_list[:max_points], 1)])

def _find_best_doc_metadata(file_texts: List[Tuple[str, str, str]]) -> Dict[str, Any]:
    best_meta = {"org": "", "level": "UNKNOWN", "date": "", "no": "", "type": "函", "raw_text": ""}
    max_score = -1
    for _name, raw, _clean in file_texts:
        date, no, dtype = _extract_doc_meta(raw)
        org, level = _infer_org_and_level(raw)
        h_org, h_kind = _extract_header_org_doc_type(raw)
        # Prioritize files that contain usable top-header org/kind.
        score = 0.0
        score += 6.0 if h_org else 0.0
        score += 6.0 if h_kind in ("令", "函", "呈") else 0.0
        score += 2.0 if no else 0.0
        score += 1.0 if date else 0.0
        score += 2.0 if org else 0.0
        score += 1.0 if dtype != "函" else 0.5
        if score > max_score:
            max_score = score
            best_meta = {"org": org, "level": level, "date": date, "no": no, "type": dtype, "raw_text": raw}

    # Safety fallback from header parser.
    if best_meta.get("raw_text"):
        h_org, h_kind = _extract_header_org_doc_type(best_meta.get("raw_text", ""))
        if not best_meta.get("org") and h_org:
            best_meta["org"] = h_org
        if (best_meta.get("type") or "") not in ("令", "函", "呈") and h_kind in ("令", "函", "呈"):
            best_meta["type"] = h_kind

    # Fallback: infer bureau from doc_no prefix + subject wording when header extraction is weak.
    raw_text = best_meta.get("raw_text", "") or ""
    subject = _extract_doc_subject(raw_text)
    if not (subject or "").strip():
        subject = _extract_doc_subject_fallback(raw_text)
    doc_no = best_meta.get("no", "") or ""
    if (not best_meta.get("org")) and ("國備" in doc_no or "本局" in subject):
        best_meta["org"] = "國防部軍備局"
    if best_meta.get("org") == "國防部軍備局" and (best_meta.get("level") or "UNKNOWN") == "UNKNOWN":
        best_meta["level"] = "FROM_DIRECT_SUPERIOR"
    if (best_meta.get("type") or "") == "函":
        subj = subject or ""
        if "請照辦" in subj or "令發" in subj or ("國備" in doc_no):
            best_meta["type"] = "令"

    # Cross-file hard correction:
    # If any attachment clearly shows header "...廠 呈", force submit-doc semantics.
    for _name, raw, _clean in file_texts:
        h_org2, h_kind2 = _extract_header_org_doc_type(raw)
        if h_kind2 == "呈":
            best_meta["type"] = "呈"
            if h_org2:
                best_meta["org"] = h_org2
            if (best_meta.get("level") or "UNKNOWN") == "UNKNOWN":
                if re.search(r"第[○０0一二三四五六七八九十]{1,4}廠|[0-9０-９]{3}廠", h_org2 or ""):
                    best_meta["level"] = "FROM_SUBORDINATE"
            break

    # Hard org fallback across all files:
    # if any file contains full unit title with plant number, use it directly.
    full_org_hit = ""
    for _name, raw, _clean in file_texts:
        t = _compact_spaced_cjk(raw or "")
        m_full = re.search(
            r"(國防部軍備局生產製造中心第[○０0一二三四五六七八九十]{1,4}廠)",
            t,
        )
        if m_full:
            full_org_hit = m_full.group(1).strip()
            break
    if full_org_hit:
        best_meta["org"] = full_org_hit
        if (best_meta.get("level") or "UNKNOWN") == "UNKNOWN":
            best_meta["level"] = "FROM_SUBORDINATE"
        if (best_meta.get("type") or "") not in ("令", "函", "呈"):
            best_meta["type"] = "呈"

    # Subject semantic correction for submit-doc style.
    subj2 = _extract_doc_subject(best_meta.get("raw_text", "") or "")
    if not (subj2 or "").strip():
        subj2 = _extract_doc_subject_fallback(best_meta.get("raw_text", "") or "")
    if (best_meta.get("type") or "") == "函":
        if re.match(r"^(呈|檢送).*(請核示|請鑒核)", subj2 or ""):
            best_meta["type"] = "呈"
    if (best_meta.get("type") or "") == "呈" and (best_meta.get("level") or "UNKNOWN") == "UNKNOWN":
        best_meta["level"] = "FROM_SUBORDINATE"
    return best_meta


def _normalize_doc_type_by_level(doc_type: str, level: str) -> str:
    """
    Business correction:
    - 下級單位來文，若未明確辨識出「呈」而落為「函」，改判為「呈」。
    """
    dt = (doc_type or "").strip()
    lv = (level or "").strip().upper()
    if lv == "FROM_SUBORDINATE" and dt == "函":
        return "呈"
    if dt in ("令", "函", "呈"):
        return dt
    return "函"


def _map_kind_to_doc_type(kind: str) -> str:
    k = (kind or "").strip()
    if k == "呈":
        return "submit_draft"
    if k == "函":
        return "letter_draft"
    if k == "令":
        return "order_draft"
    return "letter_draft"


def _safe_inferred_org(org: str) -> str:
    v = (org or "").strip()
    return v if v else "未辨識機關"


def _build_inferred_debug(best_meta: Dict[str, Any], file_texts: List[Tuple[str, str, str]]) -> Dict[str, Any]:
    dbg: Dict[str, Any] = {
        "chosen_org": best_meta.get("org", ""),
        "chosen_level": best_meta.get("level", ""),
        "chosen_kind": best_meta.get("type", ""),
        "header_hits": [],
    }
    for name, raw, _clean in file_texts[:6]:
        h_org, h_kind = _extract_header_org_doc_type(raw or "")
        if h_org or h_kind:
            dbg["header_hits"].append({"file": name, "org": h_org, "kind": h_kind})
    return dbg

def _build_fixed_incoming_point1(
    org: str,
    level: str,
    doc_date: str,
    doc_no: str,
    doc_type: str,
    doc_subject: str,
    full_text_for_search: str = "",
) -> str:
    injected = _inject_org_level_point(
        "",
        org,
        level,
        doc_date,
        doc_no,
        doc_type,
        doc_subject,
        full_text_for_search=full_text_for_search,
        max_points=2,
    )
    first_line = (injected.splitlines()[0] if injected else "").strip()
    if not first_line:
        return ""

    # Normalize legacy numbering prefix, e.g. "重點1：".
    first_line = re.sub(r"^\s*重點\s*\d+\s*[:：]\s*", "", first_line).strip()

    # Strip fixed-marker prefix from value; marker is now used as the outer field label.
    for prefix in (
        "【擬稿說明第一點固定引述】：",
        "【擬稿說明第一點固定引述】:",
        "擬稿說明第一點固定引述：",
        "擬稿說明第一點固定引述:",
    ):
        if first_line.startswith(prefix):
            return first_line[len(prefix):].strip()
    return first_line


@csrf_exempt
@require_node("doc", api=True)
def api_parse_attachments_focus(request: HttpRequest):
    if request.method != "POST": return JsonResponse({"ok": False, "error": "method not allowed"}, status=405)
    
    try:
        upload_files = request.FILES.getlist("attachments")
        stash_files = _load_stashed_as_uploadedfiles_local(request)
        all_files = list(upload_files) + list(stash_files)
        
        if not all_files:
            return JsonResponse({"ok": False, "error": "no_attachments_found"}, status=400)
        
        file_texts: List[Tuple[str, str, str]] = [] 
        for i, f in enumerate(all_files[:20], 1):
            try:
                raw_bytes = _read_file_bytes(f)
                name = getattr(f, "name", f"file_{i}")
                # 🛡️ 物理修復：使用從 views_helpers 正確引入的函數
                text = _extract_text_by_ext(io.BytesIO(raw_bytes), name) or ""
                cleaned = _clean_attachment_text(text)
                if text: file_texts.append((name, text, cleaned))
            except Exception as e:
                print(f"[DEBUG] extract failed for {name}: {e}")
                
        if not file_texts: 
            return JsonResponse({"ok": False, "error": "all_files_empty"}, status=400)
        
        incoming_docs, attachment_docs = _split_file_texts_by_kind(file_texts)
        source_docs = incoming_docs or file_texts
        best_meta = _find_best_doc_metadata(source_docs)
        best_meta["type"] = _normalize_doc_type_by_level(best_meta.get("type", ""), best_meta.get("level", ""))
        combined_text = "\n\n".join([p[2] for p in file_texts]).strip()
        
        llm = get_chat_model()
        self_refer = _resolve_writer_identity_local(request)
        extra_hint = (request.POST.get("prompt") or "")

        incoming_raw_text = best_meta.get("raw_text", "") or (source_docs[0][1] if source_docs else combined_text)
        washed_incoming_text = _preprocess_incoming_text_local(
            incoming_raw_text, best_meta["org"], self_refer, level=best_meta["level"]
        )

        # 來文說明：直接抽「說明」段落，保留每段完整語義。
        incoming_desc = _extract_description_paragraphs(washed_incoming_text, max_items=8)
        incoming_desc = _filter_points_by_anchor_doc_no(incoming_desc, best_meta.get("no", ""))
        incoming_desc = [x for x in incoming_desc if not _is_address_like_text(x)]
        incoming_desc = [x for x in incoming_desc if not _is_speed_level_like_text(x)]

        # ?????????????????????????????????????????
        # ??? LLM ???????1..n??????????????????
        incoming_prompt = ""


        # 附件重點：只看附件檔，不混來文檔。
        attach_prompt, attachment_points = _extract_attachment_points(
            attachment_docs,
            llm,
            extra_hint=extra_hint,
            max_points=20,
        )
        attachment_points = [x for x in attachment_points if not _is_address_like_text(x)]
        attachment_points = [x for x in attachment_points if not _is_speed_level_like_text(x)]

        sender_org = _extract_header_org_doc_type(incoming_raw_text)[0] or _safe_inferred_org(best_meta.get("org", ""))
        recipient_org = _extract_recipient_org(incoming_raw_text)
        incoming_point1 = _build_fixed_incoming_point1(
            best_meta.get("org", ""),
            best_meta.get("level", ""),
            best_meta.get("date", ""),
            best_meta.get("no", ""),
            best_meta.get("type", ""),
            _extract_doc_subject(best_meta.get("raw_text", "")) or best_meta.get("subject", ""),
            full_text_for_search=best_meta.get("raw_text", "") or combined_text,
        )
        summary_text = _format_focus_summary_v3(
            sender_org=sender_org,
            recipient_org=recipient_org,
            doc_date=best_meta.get("date", ""),
            doc_no=best_meta.get("no", ""),
            doc_subject=_extract_doc_subject(best_meta.get("raw_text", "")) or best_meta.get("subject", ""),
            incoming_desc=incoming_desc,
            incoming_point1=incoming_point1,
            attachment_points=attachment_points,
            max_incoming_desc=8,
            max_attach=20,
        )


        debug_obj = _build_inferred_debug(best_meta, file_texts)
        debug_obj["incoming_files"] = [x[0] for x in incoming_docs]
        debug_obj["attachment_files"] = [x[0] for x in attachment_docs]

        combined_prompt = incoming_prompt
        if attach_prompt:
            combined_prompt = f"{incoming_prompt}\n\n-----\n[附件重點 Prompt]\n{attach_prompt}"

        return JsonResponse(
            {
                "ok": True,
                "summary_text": summary_text,
                "prompt": combined_prompt,
                "inferred": {
                    "org": sender_org or _safe_inferred_org(best_meta.get("org", "")),
                    "recipient_org": recipient_org or "未辨識單位",
                    "level": best_meta.get("level", ""),
                    "doc_kind": best_meta.get("type", ""),
                    "doc_type": _map_kind_to_doc_type(best_meta.get("type", "")),
                    "debug": debug_obj,
                },
            },
            status=200,
        )
            
    except Exception as e:
        import traceback
        return JsonResponse({"ok": False, "error": str(e), "trace": traceback.format_exc()}, status=500)

@csrf_exempt
@require_node("doc", api=True)
def api_parse_attachments(request: HttpRequest):
    try:
        upload_files = request.FILES.getlist("attachments")
        stash_files = _load_stashed_as_uploadedfiles_local(request)
        all_files = list(upload_files) + list(stash_files)
        if not all_files: return JsonResponse({"ok": False, "error": "no_attachments"}, status=400)
        out_files = []
        combined_parts = []
        for i, f in enumerate(all_files[:20], 1):
            name = getattr(f, "name", f"file_{i}")
            try:
                raw = _read_file_bytes(f)
                text = _extract_text_by_ext(io.BytesIO(raw), name) or ""
                out_files.append({"name": name, "ok": True, "chars": len(text)})
                if text: combined_parts.append(f"【附件：{name}】\n{text}")
            except Exception as e:
                out_files.append({"name": name, "ok": False, "error": str(e)})
        return JsonResponse({"ok": True, "files": out_files, "combined_text": "\n\n".join(combined_parts).strip()}, status=200)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

def _read_file_bytes(f) -> bytes:
    try: f.seek(0)
    except: pass
    data = f.read()
    try: f.seek(0)
    except: pass
    return data or b""

def _load_stashed_as_uploadedfiles_local(request: HttpRequest) -> List[SimpleUploadedFile]:
    user_id = get_login_user_idno(request) or "anonymous"
    try:
        media_root = str(getattr(settings, "MEDIA_ROOT", "media"))
        stash_dir = Path(media_root) / "doc" / "sybase_stash" / user_id
    except:
        stash_dir = Path("media") / "doc" / "sybase_stash" / user_id
        
    tokens_raw = ""
    if request.method == "POST":
        tokens_raw = request.POST.get("sybAttachTokens") or request.POST.get("syb_tokens") or ""
        if not tokens_raw:
            try:
                body = json.loads(request.body.decode("utf-8"))
                tokens_raw = body.get("sybAttachTokens") or body.get("syb_tokens") or ""
            except: pass
    if not tokens_raw: tokens_raw = request.GET.get("sybAttachTokens") or ""
    
    # 🛡️ 實體緩存物理隔離：過濾掉空字串並去重，確保不會讀取到無關檔案
    tokens = list(dict.fromkeys([t.strip() for t in str(tokens_raw).split(",") if t.strip() and len(t.strip()) > 5]))
    
    files = []
    if not tokens: return []
    
    if stash_dir.exists():
        for token in tokens:
            # 物理精確匹配：只抓取當前 Token 開頭的檔案，避免 glob 泛配造成的混雜
            for p in stash_dir.glob(f"{token}__*"):
                if p.is_file():
                    try:
                        fname = p.name.split("__", 1)[-1] if "__" in p.name else p.name
                        files.append(SimpleUploadedFile(name=fname, content=p.read_bytes()))
                    except: pass
    return files

def _dedupe_points(points_text: str, max_points: int = 20) -> str:
    lines = [ln.strip() for ln in (points_text or "").splitlines() if ln.strip()]
    out, seen = [], set()
    for ln in lines:
        content = re.sub(r"^重點\s*\d+\s*[:：]\s*", "", ln)
        key = _normalize_point_text(content)
        if not key or key in seen: continue
        seen.add(key)
        out.append(content)
        if len(out) >= max_points: break
    return "\n".join([f"重點{i}：{p}" for i, p in enumerate(out, 1)])


def _postprocess_focus_points(summary_text: str, max_points: int = 20) -> str:
    """
    LLM response post-processing:
    remove non-key fieldized rows and re-number.
    """
    blocked_heads = {
        "發文單位", "公文類別", "簽署首長", "首長軍階", "報告狀態", "密等及解密條件或保密期限",
        "擬辦", "建議", "請示", "研處意見",
    }
    lines = [ln.strip() for ln in (summary_text or "").splitlines() if ln.strip()]

    kept: List[str] = []
    candidates: List[str] = []
    for ln in lines:
        body = _strip_point_prefixes(ln)
        body_plain = re.sub(r"\*\*(.*?)\*\*", r"\1", body).strip()
        if body_plain:
            candidates.append(body_plain)

        # block rows like "發文單位：..." (with/without markdown **)
        m = re.match(r"^([A-Za-z\u4e00-\u9fff]{2,16})\s*[:：]\s*.+$", body_plain)
        if m:
            head = (m.group(1) or "").strip()
            if head in blocked_heads:
                continue

        if _is_non_key_point_text(body_plain):
            continue
        if _is_address_like_text(body_plain):
            continue
        if _is_speed_level_like_text(body_plain):
            continue

        # Second-stage drafting cues must not leak into stage-1 key points.
        if re.search(r"(擬辦|建議|請示|研處意見)\s*[:：]", body_plain):
            continue

        kept.append(body_plain)
        if len(kept) >= max_points:
            break

    # Keep enough stage-1 facts: if strict filters over-prune, fallback to lightweight filtering.
    if len(kept) < min(8, max_points):
        seen = { _normalize_point_text(x) for x in kept }
        for body_plain in candidates:
            if len(body_plain) < 8:
                continue
            if re.search(r"(擬辦|建議|請示|研處意見)\s*[:：]", body_plain):
                continue
            if _is_address_like_text(body_plain):
                continue
            if _is_speed_level_like_text(body_plain):
                continue
            key = _normalize_point_text(body_plain)
            if not key or key in seen:
                continue
            kept.append(body_plain)
            seen.add(key)
            if len(kept) >= min(8, max_points):
                break

    return "\n".join([f"重點{i}：{x}" for i, x in enumerate(kept, 1)])
