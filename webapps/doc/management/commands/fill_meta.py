# fill_meta.py
from __future__ import annotations
import json
import re
from copy import deepcopy
from typing import Any, Dict, List, Tuple


# ----------------------------
# 1) doc_type -> doc_kind
# ----------------------------
DOC_KIND_MAP = {
    "sign_memo": "簽呈",
    "submit_draft": "呈",
    "order_draft": "令",
    "letter_draft": "函",
    "note": "便籤",
}


# ----------------------------
# 2) meta templates (依附檔欄位骨架)
#    你可依機關實際欄位再微調
# ----------------------------
META_TPL_SIGN_MEMO: Dict[str, Any] = {
    "draft_unit": "○○○○組",
    "handler": "○○○",
    "phone": "○○○ 65XXXX",

    "speed": "普通",
    "security_level": "",
    "declassify_condition": "",
    "declassify_limit": "否",

    "legal_basis": "",
    "attachments": "",

    "official_seal_level": 4,
    "secrecy_line": "否",

    "decision": "",
    "submit_mode": "簽稿併呈",

    "year_no": "11x",
    "classification_no": "xxxxxx",
    "retention_years": 5,
    "microfilm": "否",

    "sign_date_y": "11x",
    "sign_date_m": "x",
    "sign_date_d": "x",

    "approval_roles": "主任、○○副主任、○○副主任、○○主任、組長",
    "approval_layout": "雙排",
    "approval_owner": "○○主任",

    "seal_unit": "○○○○中心",
    "seal_title": "○○主任",
}

META_TPL_SUBMIT_DRAFT: Dict[str, Any] = {
    "agency_address": "115011臺北○○○○○○號",
    "postal_code": "",
    "recipient_address": "",
    "full_name": "國○○○○○○○○○中心",
    "fax": "",

    "recipient": "",
    "handler": "○○○",
    "phone": "02-27850XXX1#XXXXXX",

    "speed": "普通件",
    "security_level": "",
    "declassify_condition": "",
    "declassify_limit": "否",

    "doc_year": "○○○",
    "doc_month": "○○",
    "doc_day": "○○",
    "doc_word": "○○○○",
    "doc_no": "11XXXXXXXX",

    "attachments": "",

    "official_seal_level": 5,
    "secrecy_line": "○○○",

    "year_no": 115,
    "classification_no": "081803",
    "retention_years": 15,

    "signature": "主　任　○○○",

    "approval_roles": "主任*001、兵工副主任*016、測量副主任*015、政戰主任*003、組長*004",
    "approval_layout": "雙排",
    "approval_owner": "主任",
}

META_TPL_ORDER_DRAFT: Dict[str, Any] = {
    "speed": "普通",
    "security_level": "",
    "attachments": "",
    "main_recipient": "各單位",
    "copy_recipient": "",
    "effective_date": "○年○月○日",
}

META_TPL_LETTER_DRAFT: Dict[str, Any] = {
    "recipient": "○○單位/○○股份有限公司",
    "copy_recipient": "○○單位",
    "attachments": "",
    "speed": "普通",
    "security_level": "",
    "doc_date": "○年○月○日",
    "doc_no": "",
    "handler": "○○○",
    "phone": "○○○ 65XXXX",
}

META_TPL_NOTE: Dict[str, Any] = {
    "owner": "○○○",
    "created_at": "○年○月○日",
    "category": "",
    "related_case": "",
}


def meta_template_for(doc_type: str) -> Dict[str, Any]:
    if doc_type == "sign_memo":
        return deepcopy(META_TPL_SIGN_MEMO)
    if doc_type == "submit_draft":
        return deepcopy(META_TPL_SUBMIT_DRAFT)
    if doc_type == "order_draft":
        return deepcopy(META_TPL_ORDER_DRAFT)
    if doc_type == "letter_draft":
        return deepcopy(META_TPL_LETTER_DRAFT)
    if doc_type == "note":
        return deepcopy(META_TPL_NOTE)
    # default fallback
    return {
        "handler": "○○○",
        "phone": "○○○ 65XXXX",
        "attachments": "",
        "security_level": "",
    }


# ----------------------------
# 3) robust parser: 允許檔案內有多段 JSON 陣列連續貼
# ----------------------------
def parse_multiple_json_arrays(text: str) -> List[Dict[str, Any]]:
    """
    允許輸入長這樣：
      [ {...}, {...} ]
      [ {...} ]
      [ {...}, {...}, {...} ]
    會全部合併成一個 list。
    """
    # 移除 BOM / 前後空白
    text = text.lstrip("﻿").strip()
    if not text:
        return []

    items: List[Dict[str, Any]] = []

    decoder = json.JSONDecoder()
    idx = 0
    n = len(text)
    while idx < n:
        # skip whitespace
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break

        obj, end = decoder.raw_decode(text, idx)
        idx = end

        if isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict):
                    items.append(it)
        elif isinstance(obj, dict):
            items.append(obj)
        # else ignore non-dict/list root

    return items


# ----------------------------
# 4) merge helper
# ----------------------------
def merge_meta(existing: Any, tpl: Dict[str, Any]) -> Dict[str, Any]:
    """
    保留 existing 已填值，補上 tpl 缺的鍵。
    """
    if not isinstance(existing, dict):
        existing = {}
    out = deepcopy(tpl)
    for k, v in existing.items():
        out[k] = v
    return out


def score_item(it: Dict[str, Any]) -> Tuple[int, int, int]:
    """
    去重時挑較完整者：
    1) tags 數量多者優先
    2) description 長者優先
    3) content 長者優先
    """
    tags = it.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    desc = it.get("description") or ""
    content = it.get("content") or ""
    return (len(tags), len(str(desc)), len(str(content)))


def normalize_title(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="input json file (can contain multiple arrays)")
    p.add_argument("--output", default="output.json", help="output json file")
    args = p.parse_args()

    raw = open(args.input, "r", encoding="utf-8").read()
    items = parse_multiple_json_arrays(raw)

    fixed: List[Dict[str, Any]] = []
    for it in items:
        doc_type = (it.get("doc_type") or "").strip()
        doc_kind = DOC_KIND_MAP.get(doc_type, "")

        it2 = deepcopy(it)
        it2["title"] = normalize_title(it2.get("title") or "")
        if doc_kind:
            it2["doc_kind"] = doc_kind
        else:
            # 若 doc_type 不在 map，就用 title 前綴猜一次
            t = it2["title"]
            if t.startswith("簽呈"):
                it2["doc_kind"] = "簽呈"
            elif t.startswith("呈稿") or t.startswith("呈"):
                it2["doc_kind"] = "呈"
            elif t.startswith("令稿") or t.startswith("令"):
                it2["doc_kind"] = "令"
            elif t.startswith("函稿") or t.startswith("函"):
                it2["doc_kind"] = "函"
            else:
                it2["doc_kind"] = ""

        tpl = meta_template_for(doc_type)
        it2["meta"] = merge_meta(it2.get("meta"), tpl)

        # tags normalize
        tags = it2.get("tags")
        if isinstance(tags, list):
            it2["tags"] = [str(x).strip() for x in tags if str(x).strip()]
            # 去重但保序
            seen = set()
            out_tags = []
            for x in it2["tags"]:
                if x not in seen:
                    seen.add(x)
                    out_tags.append(x)
            it2["tags"] = out_tags
        else:
            it2["tags"] = []

        fixed.append(it2)

    # 去重：同 doc_type + title
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for it in fixed:
        key = ((it.get("doc_type") or "").strip(), normalize_title(it.get("title") or ""))
        if key not in best:
            best[key] = it
        else:
            if score_item(it) > score_item(best[key]):
                best[key] = it

    out = list(best.values())

    # 穩定排序：doc_type 再 title
    out.sort(key=lambda x: ((x.get("doc_type") or ""), (x.get("title") or "")))

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[OK] input items={len(items)} -> output unique items={len(out)}")
    print(f"[OK] wrote: {args.output}")


if __name__ == "__main__":
    main()
