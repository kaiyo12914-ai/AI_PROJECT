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

LEVEL_LABEL = {
    "FROM_DIRECT_SUPERIOR": "直屬上級單位",
    "FROM_SUPERIOR": "上級單位",
    "FROM_PEER": "平行單位",
    "FROM_SUBORDINATE": "下級單位",
    "FROM_EXTERNAL": "外部單位",
}

KNOWN_HEADER_ORGS = [
    "國防部軍備局生產製造中心第四０一廠",
    "國防部軍備局生產製造中心第二０九廠",
    "國防部軍備局生產製造中心第二０五廠",
    "國防部軍備局生產製造中心第二０二廠",
    "國防部軍備局生產製造中心",
    "國防部軍備局",
    "國防部",
]

@lru_cache(maxsize=1)
def _load_org_level_map() -> dict:
    path = Path(__file__).resolve().parent / "rules" / "org_level_map.json"
    if not path.exists():
        legacy = Path(__file__).resolve().parent / "services" / "rules" / "org_level_map.json"
        if legacy.exists(): path = legacy
    return json.loads(path.read_text(encoding="utf-8"))

def _normalize_org_text(s: str) -> str:
    t = (s or "").strip()
    if not t: return ""
    t = t.replace("0", "○").replace("０", "○")
    t = re.sub(r"[\s　]+", "", t)
    t = re.sub(r"[，,。．、;；:：()（）\[\]【】<>《》\"'指標“”指標‘’·、，,。．:：;；\s]+", "", t)
    return t

def _normalize_point_text(s: str) -> str:
    t = (s or "").strip().lower()
    if not t: return ""
    return re.sub(r"[()（）\[\]【】「」\"'指標“”指標‘’·、，,。．:：;；\s]+", "", t)


def _strip_point_prefixes(s: str) -> str:
    """
    Remove repeated numbering prefixes like:
    "重點18： 重點15： 內容" -> "內容"
    """
    t = (s or "").strip()
    if not t:
        return ""
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"^\s*重點\s*\d+\s*[:：]\s*", "", t).strip()
    # Remove leaked inner ordinal markers at the beginning, e.g. "二、...", "(一)...", "1...."
    # Keep this strictly start-anchored to avoid altering body text semantics.
    while True:
        nt = re.sub(
            r"^\s*(?:"
            r"[一二三四五六七八九十百千]+[、.．:：)]|"
            r"\d+[、.．:：)]|"
            r"[（(]\s*[一二三四五六七八九十百千\d]+\s*[)）]"
            r")\s*",
            "",
            t,
        ).strip()
        if nt == t:
            break
        t = nt
    # Remove section-label leakage from stage-1 key points.
    t = re.sub(r"^\s*(主旨|說明|擬辦|建議|請示)\s*[:：]\s*", "", t).strip()
    return t


def _is_non_key_point_text(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return True
    # Normalize markdown emphasis to plain text before checks.
    t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)

    # Fragment / too short to be actionable.
    if len(t) < 8:
        return True

    # Metadata-style lines, not real key points.
    meta_prefix = (
        "文件目的", "文件類型", "文件內容", "文件補正", "文件相關單位",
        "文件相關事件", "文件相關日期", "文件相關人員", "文件相關文件",
        "廠長", "承辦人", "聯絡人", "地址", "電話", "電子信箱",
        "密等及解密條件或保密期限",
        # Stage-2 only terms: must not appear in stage-1 parse_focus output.
        "擬辦", "建議", "請示", "研處意見",
    )
    if any(t.startswith(p + "：") or t.startswith(p + ":") for p in meta_prefix):
        return True

    # Single-field tags frequently hallucinated by LLM.
    if re.match(r"^(主旨|日期|字號|速別|密等|附件|受文者)\s*[:：]\s*.+$", t):
        return True
    if re.match(r"^密等及解密條件或保密期限\s*[:：]?\s*.*$", t):
        return True
    # Non-key metadata narration patterns.
    if re.search(r"(承辦人|簽署人|簽署人職稱|職稱為廠長|文件類別|檔號欄位|保存年限欄位)", t):
        return True
    if re.search(r"(主旨欄位).*(標註|註記).*(無)", t):
        return True
    if re.search(r"^本件公文承辦人為", t):
        return True
    if re.search(r"^文件類別屬於", t):
        return True
    if re.search(r"^文件末尾設有檔號欄位", t):
        return True
    if re.search(r"(附件數量為|附件[為共]\s*[甲乙丙丁一二三四五六七八九十\d]+\s*份?)", t):
        return True
    # Contact metadata should never be treated as key points.
    if re.search(r"(聯絡電話|電話|分機)\s*[:：]?\s*[\d\-()#轉分機 ]+", t):
        return True

    # Officer title/name snippets are metadata, not key points.
    if re.match(r"^(廠長|局長|部長|上校|少將|中將|上將)\s*[:：]?\s*.*$", t):
        return True
    if re.search(r"(廠長|局長|部長).*(少將|中將|上將|上校|中校|少校)", t):
        return True

    # LLM lead-in / narration (not source-document facts).
    leadin_patterns = (
        r"^這份文件是一份由.+發出的正式公文[（(][呈令函][）)]",
        r"^由於原始文件內容較為簡[練略].*以下為[您你].*關鍵重點",
        r"^以下為[您你].*拆解並整理.*關鍵重點",
        r"^本文件(主要)?內容(摘要|如下)",
    )
    if any(re.search(pat, t) for pat in leadin_patterns):
        return True

    # Stage isolation: drafting terms belong to generate-draft stage, not parse-focus stage.
    if re.match(r"^(擬辦|建議|請示|研處意見)\s*[:：]\s*.*$", t):
        return True

    # Fieldized synthetic summaries from LLM (not verbatim source points).
    if re.match(r"^[A-Za-z\u4e00-\u9fff]{2,16}\s*[:：]\s*.+$", t):
        synthetic_field_heads = (
            "發文單位", "公文類別", "簽署首長", "首長軍階", "機密等級", "解密條件",
            "主旨核心", "報告狀態", "正式效力", "辦理目的", "依據日期", "依據形式",
            "事件對象", "事件性質", "附件內容", "附件數量", "行政流程",
        )
        head = re.split(r"[:：]", t, maxsplit=1)[0].strip()
        if head in synthetic_field_heads:
            return True

    synthetic_phrases = (
        "通常用於", "具備法律與行政效力", "體現了", "以下為您", "以下是整理後",
        "由於原始文件內容較為", "拆解並整理", "核心重點",
    )
    if any(p in t for p in synthetic_phrases):
        return True

    return False

def _clean_attachment_text(text: str) -> str:
    lines = (text or "").splitlines()
    out = []
    skip_patterns = [
        r"^第\s*\d+\s*頁.*$", r"^[裝訂線]+$", r"^檔號[:：].*$", r"^保存年限[:：].*$",
        r"^受文者[:：].*$", r"^發文日期[:：].*$", r"^發文字號[:：].*$", r"^密等及解密條件[:：].*$",
        r"^速別[:：].*$", r"^附件[:：].*$", r"^正本[:：].*$", r"^副本[:：].*$",
        r"^聯絡人[:：].*$", r"^電話[:：].*$", r"^傳真[:：].*$", r"^電子信箱[:：].*$",
        r"^地址[:：].*$", r"^本件屬一般公務資訊.*$"
    ]
    for raw in lines:
        line = (raw or "").strip()
        if not line: continue
        should_skip = False
        for pat in skip_patterns:
            if re.match(pat, line, re.IGNORECASE):
                should_skip = True
                break
        if not should_skip: out.append(line)
    return "\n".join(out).strip()

def _is_doc_ref_line(line: str) -> bool:
    s = (line or "").strip()
    if not s: return False
    return bool(re.search(r"發文日期|發文字號|字第|\d{2,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|號令|頒|依據", s))

def _is_header_meta_line(line: str) -> bool:
    s = (line or "").strip()
    if not s: return True
    return bool(re.match(r"^(檔號|保存年限|地址|電話|傳真|承辦人|受文者|主旨|說明|附件|密等|速別)\s*[:：]", s))

def _pick_header_lines(text: str, max_lines: int = 40) -> List[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines: return []
    stop_idx = len(lines)
    for i, t in enumerate(lines):
        if re.search(r"^(主旨|說明|附件)[:：]", t):
            stop_idx = i
            break
    return lines[:min(stop_idx, max_lines)]

def _extract_recipient_candidates(header_lines: List[str], max_lines: int = 40) -> List[str]:
    """
    Extract recipient org candidates from header lines.
    Handles both:
    - 受文者：國防部軍備局...
    - 受文者：
      國防部軍備局...
    """
    lines = [_compact_spaced_cjk(ln) for ln in (header_lines or []) if (ln or "").strip()]
    if not lines:
        return []

    recipients: List[str] = []
    stop_pat = re.compile(
        r"^(主旨|說明|附件|發文字號|發文日期|檔號|保存年限|密等|速別|地址|電話|傳真|聯絡人|電子信箱)\s*[:：]"
    )
    for i, raw in enumerate(lines[:max_lines]):
        m = re.match(r"^受文者\s*[:：]\s*(.*)$", raw)
        if not m:
            continue
        inline = (m.group(1) or "").strip()
        if inline:
            parts = [p.strip() for p in re.split(r"[、,，;；]", inline) if p.strip()]
            recipients.extend(parts)
            continue

        # Multi-line recipient block.
        for j in range(i + 1, min(i + 6, len(lines))):
            ln = (lines[j] or "").strip()
            if not ln or stop_pat.match(ln) or re.match(r"^[令函呈]$", ln):
                break
            # Sender-title line starts; do not absorb into recipients.
            if re.match(r"^.+(?:\s|　)?[令函呈]\s*$", ln):
                break
            # Stop when next explicit field begins.
            if re.match(r"^[一-龥A-Za-z0-9○〇０0]{1,10}\s*[:：]", ln):
                break
            recipients.append(ln)

    # Normalize and dedupe.
    out: List[str] = []
    seen = set()
    for r in recipients:
        rn = _normalize_org_text(r)
        if len(rn) < 3:
            continue
        if rn in seen:
            continue
        seen.add(rn)
        out.append(rn)
    return out


def _recipient_block_bounds(lines: List[str], max_lines: int = 40) -> Tuple[int, int]:
    """
    Return recipient block [start, end] in header, or (-1, -1) if absent.
    """
    if not lines:
        return -1, -1
    stop_pat = re.compile(
        r"^(主旨|說明|附件|發文字號|發文日期|檔號|保存年限|密等|速別|地址|電話|傳真|聯絡人|電子信箱)\s*[:：]"
    )
    for i, raw in enumerate(lines[:max_lines]):
        m = re.match(r"^受文者\s*[:：]\s*(.*)$", raw)
        if not m:
            continue
        inline = (m.group(1) or "").strip()
        if inline:
            return i, i
        end = i
        for j in range(i + 1, min(i + 6, len(lines))):
            ln = (lines[j] or "").strip()
            if not ln or stop_pat.match(ln) or re.match(r"^[令函呈]$", ln):
                break
            if re.match(r"^.+(?:\s|　)?[令函呈]\s*$", ln):
                break
            if re.match(r"^[一-龥A-Za-z0-9○〇０0]{1,10}\s*[:：]", ln):
                break
            end = j
        return i, end
    return -1, -1

def _normalize_header_line(s: str) -> str:
    """
    Normalize common OCR/fullwidth artifacts in official header lines.
    """
    t = (s or "").strip()
    if not t:
        return ""
    # Full-width spaces / punctuation normalization.
    t = t.replace("　", " ").replace("：", ":")
    # Common OCR confusion in this domain: 〇/○/０/0 in unit numbers.
    t = t.replace("〇", "○").replace("０", "0")
    # Collapse repeated spaces.
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _compact_spaced_cjk(s: str) -> str:
    """
    Merge cases like '國 防 部 軍 備 局' -> '國防部軍備局' while preserving separators.
    """
    t = _normalize_header_line(s)
    if not t:
        return ""
    # Remove spaces between CJK chars only.
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    return t.strip()

def _extract_header_org_doc_type(text: str) -> Tuple[str, str]:
    """
    Parse top header for full sender org title and doc kind.
    Examples:
      國防部 令
      國防部軍備局生產製造中心第二０五廠 呈
    """
    lines = [_compact_spaced_cjk(ln) for ln in (text or "").splitlines() if (ln or "").strip()]
    if not lines:
        return "", ""

    # Use area around recipient block as primary header zone.
    # If recipient appears at top (index 0), skip the whole recipient block.
    recv_start, recv_end = _recipient_block_bounds(lines[:40], max_lines=40)
    if recv_start > 0:
        top_zone = lines[:recv_start]
    elif recv_start == 0:
        top_zone = lines[recv_end + 1 : recv_end + 17]
    else:
        top_zone = lines[:16]
    if not top_zone:
        top_zone = lines[:16]

    # Known full-title priority (longest first) to stabilize standardized headers.
    joined_top = "\n".join(top_zone[:20])
    for org in KNOWN_HEADER_ORGS:
        if org in joined_top:
            m_kind = re.search(rf"{re.escape(org)}\s*([令函呈])", joined_top)
            if m_kind:
                return org, m_kind.group(1)

    for idx, ln in enumerate(top_zone):
        if re.search(r"(受文者|主旨|說明|發文字號|發文日期|檔號|保存年限)\s*[:：]", ln):
            continue
        # Accept header like "國防部 令 地址：..." (doc kind not necessarily at line end).
        m = re.match(r"^\s*([一-龥A-Za-z0-9○〇０0第]{2,80}?)(?:\s|　)*([令函呈])(?:\s|　|$)", ln)
        if m:
            org = (m.group(1) or "").strip()
            kind = (m.group(2) or "").strip()
            # Remove accidental trailing metadata keys merged into org.
            org = re.sub(r"(地址|聯絡人|聯絡電話|電子信箱|受文者)\s*[:：].*$", "", org).strip()
            org = re.sub(r"^[,，、\s]+|[,，、\s]+$", "", org)
            org = _compact_spaced_cjk(org)
            if org:
                return org, kind

        # Cross-line header fallback:
        # line N = full org, line N+1 = single "令/函/呈"
        if idx + 1 < len(top_zone):
            next_ln = (top_zone[idx + 1] or "").strip()
            if re.match(r"^[令函呈]$", next_ln):
                org_line = re.sub(r"(地址|聯絡人|聯絡電話|電子信箱|受文者)\s*[:：].*$", "", ln).strip()
                org_line = _compact_spaced_cjk(org_line)
                if re.search(r"[一-龥]", org_line) and len(org_line) >= 2:
                    return org_line, next_ln

    # Cross-line fallback from top area (some PDF extractors collapse title line formatting).
    head = "\n".join(top_zone[:20])
    m2 = re.search(r"([一-龥A-Za-z0-9○〇０0第]{2,40})\s*([令函呈])(?:\s|　|$)", head)
    if m2:
        return _compact_spaced_cjk((m2.group(1) or "").strip()), (m2.group(2) or "").strip()

    # Last-resort fallback for this case family.
    if "國防部" in (text or ""):
        if re.search(r"國防部\s*令", text):
            return "國防部", "令"
        if re.search(r"國防部\s*函", text):
            return "國防部", "函"
        if re.search(r"國防部\s*呈", text):
            return "國防部", "呈"
    return "", ""

def _extract_specific_org_from_line(line: str) -> Tuple[str, str]:
    """
    Prefer the most specific org unit in a full title line.
    Example:
    國防部軍備局生產製造中心第二０五廠 -> 第二０五廠 (FROM_SUBORDINATE)
    """
    s = (line or "").strip()
    if not s:
        return "", ""

    # Match unit tail like 第205廠 / 第二○五廠 / 第二０五廠.
    m = re.search(r"(第[○０0一二三四五六七八九十]{1,4}廠|[0-9０-９]{3}廠)", s)
    if m:
        return m.group(1), "FROM_SUBORDINATE"
    return "", ""

def _infer_org_and_level(text: str) -> Tuple[str, str]:
    data = _load_org_level_map()
    mapping = data.get("mapping", [])
    best_line, best_pattern, best_level, best_score = "", "", "", -1
    header_lines = _pick_header_lines(text)

    header_org, _ = _extract_header_org_doc_type(text)
    if header_org:
        # Prefer most-specific unit in full-title header (e.g., 第二０五廠 / 第401廠).
        sp_org, sp_level = _extract_specific_org_from_line(header_org)
        if sp_org and sp_level:
            return sp_org, sp_level

        org_norm = _normalize_org_text(header_org)
        best_level = ""
        best_score = -1
        for item in mapping:
            pattern, level = str(item.get("pattern") or ""), str(item.get("level") or "")
            pat_norm = _normalize_org_text(pattern)
            if not pat_norm:
                continue
            if pat_norm in org_norm:
                # Prefer longer/specific patterns over parent-org generic matches.
                score = len(pat_norm)
                if level == "FROM_SUBORDINATE":
                    score += 1000
                elif level == "FROM_DIRECT_SUPERIOR":
                    score += 100
                if score > best_score:
                    best_score = score
                    best_level = level
        if best_level:
            return header_org, best_level
        return header_org, "UNKNOWN"
    
    # Strict fallback: only inspect top header lines, avoid body contamination.
    recipients = _extract_recipient_candidates(header_lines[:20], max_lines=20)

    for raw in header_lines[:20]:
        line = _compact_spaced_cjk(raw.strip())
        if "受文者" in line:
            continue
        line_norm = _normalize_org_text(line)
        if not line_norm:
            continue
        if any(r in line_norm for r in recipients if len(r) > 4):
            continue
        if _is_doc_ref_line(line) or _is_header_meta_line(line):
            continue
        # Require organization-like tokens to reduce false matches.
        if not re.search(r"(部|局|司|署|處|中心|廠|院|會|所|隊)", line):
            continue

        specific_org, specific_level = _extract_specific_org_from_line(line)
        if specific_org and specific_level:
            return specific_org, specific_level

        for item in mapping:
            pattern, level = str(item.get("pattern") or ""), str(item.get("level") or "")
            pat_norm = _normalize_org_text(pattern)
            if not pat_norm:
                continue
            if pat_norm in line_norm:
                score = len(pat_norm) + (1000 if level == "FROM_DIRECT_SUPERIOR" else 0)
                if score > best_score:
                    best_line, best_pattern, best_level, best_score = line, pattern, level, score

    return best_line or best_pattern, best_level

def _extract_doc_meta(text: str) -> Tuple[str, str, str]:
    date, doc_no, doc_type = "", "", ""
    date_patterns = [
        r"發文日期\s*[:：]\s*(.+)$",
        r"((?:中華民國|民國|民前)\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日)",
        r"(\d{3,4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"
    ]
    for pattern in date_patterns:
        m = re.search(pattern, text)
        if m:
            date = m.group(1).strip().replace("民前", "民國")
            break

    no_patterns = [
        r"發文字號\s*[:：]\s*(.+)$",
        r"([一-龥]+字第\s*\d+\s*號)",
        r"([A-Z]{1,2}\d+字第\d+號)"
    ]
    for pattern in no_patterns:
        m = re.search(pattern, text)
        if m:
            doc_no = m.group(1).strip()
            break

    header_org, header_kind = _extract_header_org_doc_type(text)
    if header_kind in ("令", "函", "呈"):
        doc_type = header_kind

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    header_content = "\n".join(lines[:40])
    title_zone = re.sub(r"受文者\s*[:：].*?(?=\n\s*[主說明附件])", "", header_content, flags=re.S)
    
    # 文別判斷：
    # 1) 單獨一行「令/函/呈」
    # 2) 全銜尾碼「...令 / ...函 / ...呈」（常見於機關全名 + 文別）
    if not doc_type and (
        re.search(r"^\s*令\s*$", title_zone, re.M)
        or re.search(r"^\s*.+\s令\s*$", title_zone, re.M)
        or "令發" in title_zone
        or "令頒" in title_zone
    ):
        doc_type = "令"
    elif not doc_type and (re.search(r"^\s*函\s*$", title_zone, re.M) or re.search(r"^\s*.+\s函\s*$", title_zone, re.M)):
        doc_type = "函"
    elif not doc_type and (re.search(r"^\s*呈\s*$", title_zone, re.M) or re.search(r"^\s*.+\s呈\s*$", title_zone, re.M)):
        doc_type = "呈"

    if not doc_type and doc_no:
        clean_no = doc_no.replace(" ", "")
        if clean_no.endswith("令"): doc_type = "令"
        elif clean_no.endswith("函"): doc_type = "函"
        elif clean_no.endswith("呈"): doc_type = "呈"

    # 主旨語意校正：主旨若以「呈」起首，優先視為呈文。
    # 可修正 OCR/版頭抽取不穩時，預設落成「函」的誤判。
    m_subj = re.search(r"主旨\s*[:：]\s*(.+)$", text, re.M)
    if m_subj and not doc_type:
        subj = (m_subj.group(1) or "").strip()
        if re.match(r"^呈(?:請|報|核|送|陳|辦|本|有關|就|依)", subj):
            doc_type = "呈"
        elif ("請照辦" in subj or "令發" in subj):
            doc_type = "令"

    # Fallback by official doc-no prefix (military armament bureau).
    if not doc_type and doc_no and ("國備" in doc_no):
        doc_type = "令"

    if not doc_type: doc_type = "函"
    return date, doc_no, doc_type

def _extract_doc_subject(text: str) -> str:
    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.match(r"^主旨\s*[:：]\s*(.+)$", line)
        if m:
            subj = (m.group(1) or "").strip()
            subj = re.sub(r"^(這是主旨|依主旨|主旨|令發|受文者)[:：\s]*", "", subj, flags=re.IGNORECASE)
            subj = re.sub(r"[,，:：、\s]+(?:請|辦理|照辦|呈|報|送)?$", "", subj).strip()
            return subj
    return ""

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
    
    verb = "遵" if level == "FROM_DIRECT_SUPERIOR" else ("奉" if level == "FROM_SUPERIOR" else "依")
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
        for i, f in enumerate(all_files[:10], 1):
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
        
        best_meta = _find_best_doc_metadata(file_texts)
        best_meta["type"] = _normalize_doc_type_by_level(best_meta.get("type", ""), best_meta.get("level", ""))
        combined_text = "\n\n".join([p[2] for p in file_texts]).strip()
        
        llm = get_chat_model()
        self_refer = _resolve_writer_identity_local(request)
        washed_text = _preprocess_incoming_text_local(combined_text, best_meta["org"], self_refer, level=best_meta["level"])
        prompt = _build_attach_focus_prompt(washed_text, extra_hint=(request.POST.get("prompt") or ""))
        summary_raw = _to_text(llm.invoke(prompt)).strip()
        summary_text = _ensure_focus_numbered(summary_raw, max_points=20)
        summary_text = _postprocess_focus_points(summary_text, max_points=20)
        
        summary_text = _inject_org_level_point(
            summary_text, best_meta["org"], best_meta["level"],
            best_meta["date"], best_meta["no"], best_meta["type"],
            _extract_doc_subject(best_meta["raw_text"]),
            full_text_for_search=best_meta["raw_text"] or combined_text, 
            max_points=20
        )
        return JsonResponse(
            {
                "ok": True,
                "summary_text": summary_text,
                "prompt": prompt,
                "inferred": {
                    "org": _safe_inferred_org(best_meta.get("org", "")),
                    "level": best_meta.get("level", ""),
                    "doc_kind": best_meta.get("type", ""),
                    "doc_type": _map_kind_to_doc_type(best_meta.get("type", "")),
                    "debug": _build_inferred_debug(best_meta, file_texts),
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
        for i, f in enumerate(all_files[:10], 1):
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
            key = _normalize_point_text(body_plain)
            if not key or key in seen:
                continue
            kept.append(body_plain)
            seen.add(key)
            if len(kept) >= min(8, max_points):
                break

    return "\n".join([f"重點{i}：{x}" for i, x in enumerate(kept, 1)])
