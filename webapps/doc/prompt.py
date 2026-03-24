# webapps/doc/prompt.py
from __future__ import annotations

import os
import re
from typing import Optional, List, Dict, Set


# ============================================================
# New-only doc type spec (no legacy compatibility)
# ============================================================

ALLOWED_DOC_TYPES: Set[str] = {"sign_memo", "order_draft", "submit_draft", "letter_draft", "note"}

DOC_TYPE_LABEL: Dict[str, str] = {
    "sign_memo": "簽呈",
    "order_draft": "令稿",
    "submit_draft": "呈稿",
    "letter_draft": "函稿",
    "note": "便籤",
}


def _env_bool(k: str, d: bool = False) -> bool:
    v = (os.getenv(k) or ("1" if d else "0")).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


# ✅ 開發/測試想嚴格一點：PROMPT_STRICT_DOCTYPE=1
_PROMPT_STRICT_DOCTYPE = _env_bool("PROMPT_STRICT_DOCTYPE", False)


def normalize_doc_type(doc_type: str) -> str:
    """
    新制：只允許固定 doc_type。
    """
    dt = (doc_type or "").strip()
    if dt in ALLOWED_DOC_TYPES:
        return dt
    if _PROMPT_STRICT_DOCTYPE:
        raise ValueError(f"invalid doc_type: {dt!r}, allowed={sorted(ALLOWED_DOC_TYPES)}")
    return "submit_draft"


def doc_type_label(doc_type: str) -> str:
    dt = normalize_doc_type(doc_type)
    return DOC_TYPE_LABEL.get(dt, "公文")


# ============================================================
# Incoming level / discretion / risk -> writing intensity
# ============================================================

# 擴充層級：增加 direct_superior
INCOMING_LEVELS: Set[str] = {"direct_superior", "superior", "peer", "subordinate", "external"}
INCOMING_LEVEL_LABEL: Dict[str, str] = {
    "direct_superior": "直屬上級單位來文",
    "superior": "上級/主管機關來文",
    "peer": "平行單位來文",
    "subordinate": "下級/所屬單位來文",
    "external": "外部(民眾/廠商/對外)來文",
}

DISCRETION_LEVELS: Set[str] = {"low", "medium", "high"}
RISK_LEVELS: Set[str] = {"low", "medium", "high"}
LEVEL_AWARE_DOC_TYPES: Set[str] = {"sign_memo", "order_draft", "submit_draft", "letter_draft"}


def _normalize_choice(v: Optional[str], allowed: Set[str], default: str) -> str:
    s = (v or "").strip().lower()
    return s if s in allowed else default


def _infer_incoming_level_from_text(text: Optional[str]) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None

    lower = raw.lower()
    if "from_direct_superior" in lower:
        return "direct_superior"
    if "from_superior" in lower:
        return "superior"
    if "from_peer" in lower:
        return "peer"
    if "from_subordinate" in lower:
        return "subordinate"

    # 關鍵單位權威判定
    if any(k in raw for k in ("國防部", "軍備局")):
        return "direct_superior"
    if any(k in raw for k in ("生產製造中心", "生製中心")):
        return "direct_superior"

    if any(k in raw for k in ("外部", "民眾", "廠商")):
        return "external"
    if any(k in raw for k in ("上級", "長官")):
        return "superior"
    if any(k in raw for k in ("下級", "本廠", "202廠", "205廠", "209廠", "401廠")):
        return "subordinate"
    if any(k in raw for k in ("平行", "同級")):
        return "peer"

    return None


def _resolve_incoming_level(incoming_level: Optional[str], incoming_text: Optional[str]) -> Optional[str]:
    lv = (incoming_level or "").strip().lower()
    # 前端傳來的 superior 若在文字中被判定為 direct_superior，以文字判定為準
    inferred = _infer_incoming_level_from_text(incoming_text)

    if inferred == "direct_superior":
        return inferred
    
    if lv in INCOMING_LEVELS:
        return lv
    return inferred


def _level_gap_by_incoming(incoming_level: str) -> int:
    mapping = {
        "direct_superior": 1,
        "superior": 1,
        "peer": 2,
        "external": 2,
        "subordinate": 3,
    }
    return mapping.get(incoming_level, 2)


def _scale3(v: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(v, 2)


def calc_writing_intensity(
    incoming_level: Optional[str] = None,
    discretion: Optional[str] = None,
    risk: Optional[str] = None,
) -> Dict[str, object]:
    inc = _normalize_choice(incoming_level, INCOMING_LEVELS, "peer")
    dis = _normalize_choice(discretion, DISCRETION_LEVELS, "medium")
    rk = _normalize_choice(risk, RISK_LEVELS, "medium")

    gap = _level_gap_by_incoming(inc)
    dis_s = _scale3(dis)
    risk_s = _scale3(rk)
    score = gap * dis_s * risk_s
    level_1to9 = (score - 1) // 3 + 1

    return {
        "incoming_level": inc,
        "incoming_label": INCOMING_LEVEL_LABEL.get(inc, inc),
        "discretion": dis,
        "risk": rk,
        "gap": gap,
        "score": score,
        "level": level_1to9,
    }


def sign_memo_strategy_hint(meta: Dict[str, object]) -> str:
    inc = str(meta.get("incoming_level"))
    level = int(meta.get("level", 5))
    discretion = str(meta.get("discretion"))
    risk = str(meta.get("risk"))

    base: List[str] = [
        "簽擬策略（依來文層級/裁量/風險自動調整）：",
        f"- 來文層級：{meta.get('incoming_label')}",
        f"- 裁量空間：{discretion}；風險大小：{risk}；寫法強度等級：{level}/9",
    ]

    if inc in ("direct_superior", "superior"):
        base += [
            "- 取向：以『配合執行』為主，避免評論/否定來文；重點放在期程、分工、具體作為與因應規劃。",
            "- 研處意見：應以「擬依來文辦理」、「執行計畫」及「具體作為與因應規劃」為主軸；如有窒礙，應敘明「執行困難與建議處置」，並避免使用否定語句及空泛、非具體之建議用語。",
        ]
    elif inc == "peer":
        base += [
            "- 取向：以『協調回應』為主，可提出條件、修正建議與替代作法。",
            "- 研處意見：若涉及資源/風險，需交代取捨理由與配套。",
        ]
    elif inc == "subordinate":
        base += [
            "- 取向：以『核定判斷』為主，需幫決行長官把關合理性、合規性與資源影響。",
            "- 研處意見：宜提出方案比較（至少A/B）或明確核准/不核准理由，並附風險控管。",
        ]
    else:  # external
        base += [
            "- 取向：以『法遵/對外風險控管』為主，避免主觀評論；必要時提出可回覆方向與依據。",
            "- 研處意見：強調依據、程序正義、可受檢驗的事實與風險因應。",
        ]

    return "\n".join(base)


def strategy_hint_by_doc_type(doc_type: str, meta: Dict[str, object]) -> str:
    dt = normalize_doc_type(doc_type)
    label = doc_type_label(dt)
    core = sign_memo_strategy_hint(meta)
    lines = core.splitlines()
    if lines:
        lines[0] = lines[0].replace("簽擬", "擬稿")
    return f"{label}層級化擬稿策略：\n" + "\n".join(lines)


def format_guide_by_doc_type(doc_type: str) -> str:
    dt = normalize_doc_type(doc_type)

    if dt == "sign_memo":
        return (
            "格式（簽呈）：\n"
            "1) 主旨：以一句話摘要交代『辦理事項 + 請核示/請准予備查』。嚴禁出現任何文號數字。\n"
            "2) 說明：採條列(一、二、三、四)，原則最多四點，且『最後一點必為研處意見』。\n"
            "   - 說明第一點：應固定為引述來文依據及文號。\n"
            "   - 研處意見：以描述「具體因應作為」為主，可就必要性、影響、風險等面向檢討並提出具體作為。\n"
            "3) 擬辦：以 1~2 點為限，交代奉核後之具體行動方案；避免重複句（例如同一期限或同一報局動作重複出現）。\n"
        )
    return "格式：\n1) 主旨\n2) 說明\n3) 擬辦\n"


def hard_rules(doc_type: str) -> str:
    dt = normalize_doc_type(doc_type)
    section_rule = "主旨／說明／擬辦。"

    return (
        "硬性規則：\n"
        "1) 只輸出公文『本文』，不要加 Markdown 語法或 AI 註解。\n"
        "2) 嚴禁複製範例內容，僅參考結構。\n"
        "3) 資料不足處以「○○」保留，不准捏造數據。\n"
        "4) 不輸出機關地址、密等、速別等欄位。\n"
        "4-1) 可在思考時使用「必要性在於／風險在於／影響在於」做分析，但成稿正文不得出現這些口語模板。\n"
        "4-2) 請以精簡完整句撰寫；避免過長複句與冗語，但不得以截斷方式省略語意。\n"
        f"5) 內文段落請使用：{section_rule}\n"
    )


def output_mode_hint(doc_type: str, structured: bool) -> str:
    if not structured: return ""
    dt = normalize_doc_type(doc_type)

    if dt == "sign_memo":
        return (
            "輸出格式要求（結構化）：\n"
            "- 請依序輸出段落與點次：\n"
            "主旨：...（以『……，請核示。』收束）\n"
            "說明：\n"
            "(一) ...（引述依據，100% 採納系統提供之起始語）\n"
            "(二) ...（辦理目的與現況）\n"
            "(三) ...\n"
            "(四) ：...（包含必要性與風險說明）\n"
            "擬辦：\n"
            "(一) ...\n"
        )
    return "輸出格式要求：主旨／說明／擬辦。"


def audience_honorific_hint(doc_type: str, self_ref: str) -> str:
    dt = normalize_doc_type(doc_type)
    sref = (self_ref or "本單位").strip() or "本單位"

    if dt in {"sign_memo", "note"}:
        return (
            "【讀稿人與稱謂硬規則】\n"
            f"- 本文屬內部呈核文，讀稿人為我方長官；我方自稱一律用「{sref}」。\n"
            "- 受文對象（來文機關）與呈文對象（我方長官）不同，不得混用。\n"
            f"- 嚴禁把我方寫成「貴中心/貴廠/貴單位」，若出現請改為「{sref}」。"
        )

    return (
        "【讀稿人與稱謂硬規則】\n"
        f"- 本文屬對外文稿（令稿/呈稿/函稿），發文機關自稱用「{sref}」。\n"
        "- 受文對象可使用「貴單位/貴機關」或具名機關稱呼，但不得與我方自稱混淆。"
    )


def build_prompt(
    doc_type: str,
    requirement: str,
    examples: Optional[List[str]] = None,
    reference_text: Optional[str] = None,
    incoming_text: Optional[str] = None,
    attachments_text: Optional[str] = None,
    structured_output: Optional[bool] = None,
    incoming_level: Optional[str] = None,
    discretion: Optional[str] = None,
    risk: Optional[str] = None,
    signer_org_code: Optional[str] = None,
    signer_org_label: Optional[str] = None,
    signer_self_ref: Optional[str] = None,
    fixed_quote: Optional[str] = None,
    signer_full_info: Optional[Dict[str, str]] = None,
    execution_context_hint: Optional[str] = None,
) -> str:
    examples = examples or []
    dt = normalize_doc_type(doc_type)
    label = doc_type_label(dt)

    req = (requirement or "").strip()
    inc = (incoming_text or "").strip()
    att = (attachments_text or "").strip()
    ref = (reference_text or "").strip()

    # 1. 確定層級
    infer_text = "\n".join([x for x in (inc, att, req) if x and x.strip()])
    resolved_level = _resolve_incoming_level(incoming_level, infer_text)

    self_ref = str(signer_self_ref or "本單位").strip() or "本單位"
    is_internal = dt in {"sign_memo", "note"}

    # Parse execution-context hint into structured fields if possible.
    execution_unit = ""
    relation = ""
    if execution_context_hint:
        m_unit = re.search(r"應辦單位為\s*([^\s（(；;，,。]+)", execution_context_hint)
        if m_unit:
            execution_unit = (m_unit.group(1) or "").strip()
        if "直屬下級" in execution_context_hint or "督導" in execution_context_hint:
            relation = "督導下級"
        elif "平行" in execution_context_hint:
            relation = "平行協調"
        elif "主辦" in execution_context_hint or "自辦" in execution_context_hint:
            relation = "本單位自辦"
    if not execution_unit and is_internal:
        execution_unit = "本單位各相關單位"
    if not relation:
        relation = "本單位自辦"

    parts: List[str] = []
    parts.append("你是一位具十五年以上政府機關工作經驗且熟悉公文撰寫的專業撰稿人員。")
    parts.append(f"請撰寫一份正式的「{label}」公文草稿。")

    # 2) 輸出格式（唯一版本）
    parts.append(format_guide_by_doc_type(dt))

    # 3) 硬規則（集中、避免重複）
    hard = hard_rules(dt) + (
        "6) 禁止輸出重複研處意見；禁止說明點次語意重複。\n"
        "7) 說明各點必須語意完整，不得以截斷方式縮句。\n"
        "8) 主旨不得帶文號；文號與依據僅置於說明第一點。\n"
        "9) 內容不得混入其他文別名稱（例如令稿/函稿）或其語氣。\n"
        "10) 提及下轄廠僅使用簡稱（例如「第四0一廠」），不得使用全銜（例如「國防部軍備局生產製造中心第四0一廠」）。\n"
    )
    if execution_unit and is_internal:
        hard += f"11) 已知應辦單位為「{execution_unit}」時，禁止使用「貴單位/該單位」等模糊稱呼，須直接具名。\n"
    parts.append(hard)

    # 4) 稱謂與受眾（依文別分流，唯一段落）
    if is_internal:
        audience = (
            f"- 文別：內部呈核文（{label}）；讀稿受眾為本單位長官。\n"
            f"- 我方自稱：固定使用「{self_ref}」。\n"
            "- 來文機關與呈核對象不得混用。\n"
            "- 內文禁止出現「貴中心/貴廠/貴單位」指涉我方。"
        )
    else:
        audience = (
            f"- 文別：對外文稿（{label}）；受眾為單位外。\n"
            f"- 我方自稱：固定使用「{self_ref}」。\n"
            "- 對方稱謂：優先具名機關，其次「貴機關/貴單位」。\n"
            "- 禁止使用內部呈核稱謂（如大局/鈞局）以免內外混用。"
        )
    parts.append("【稱謂與受眾】\n" + audience)
    parts.append("【主旨文號規則】\n- 主旨僅寫辦理事項與請核示語，不得出現任何文號或字號。")

    # 5) 關聯判斷（結構化欄位）
    if (execution_context_hint or "").strip():
        tone = "主辦執行"
        if relation == "督導下級":
            tone = "督導+管制"
        elif relation == "平行協調":
            tone = "協調"
        lines = [
            "【應辦單位關聯判斷】",
            f"來文單位: {'軍備局/上級機關' if resolved_level in {'direct_superior', 'superior'} else '其他'}",
            f"本單位: {self_ref}",
            f"應辦單位: {execution_unit}",
            f"關係: {relation}",
            f"擬辦語氣: {tone}",
        ]
        parts.append("\n".join(lines))

    # 6) 固定引述句（可驗證）
    if fixed_quote:
        parts.append(
            "【說明第一點（字元級固定）】\n"
            "說明第一點必須與下列句子完全一致（字元級，不得增刪改字）：\n"
            f"{fixed_quote.replace('(如附呈)', '（如附呈）')}"
        )

    # 7) 策略提示（精簡）
    meta = calc_writing_intensity(resolved_level, discretion, risk)
    parts.append(
        "【層級化擬稿策略（精簡）】\n"
        f"- 來文層級：{meta.get('incoming_label')}\n"
        f"- 裁量/風險：{meta.get('discretion')}/{meta.get('risk')}；強度：{meta.get('level')}/9\n"
        "- 以具體作為為主、分工、期程、回報節點為輔；如無具體規劃則免列分工、期程、回報節點，且不寫空泛原則。"
    )

    # 8) 職能切換
    if signer_full_info:
        dept = str(signer_full_info.get("DEPT") or "").strip()
        office = str(signer_full_info.get("OFFICE") or "").strip()
        focus_hint = ""
        if any(x in dept or x in office for x in ["後勤", "供應", "維修", "裝備"]):
            focus_hint = "側重：零件庫存、MTBF 評估、維修時程及料件供應鏈。"
        elif any(x in dept or x in office for x in ["通資", "資訊", "資安", "系統"]):
            focus_hint = "側重：資安合規、系統備援、頻寬負載及軟硬體相容性。"
        elif any(x in dept or x in office for x in ["管理", "行政", "法制", "企劃"]):
            focus_hint = "側重：SOP 遵循、法規合規性、跨單位會辦建議及風險控管。"
        
        if focus_hint:
            parts.append(f"【🎭 承辦單位專業視角】\n單位職能：{office} / {dept}\n擬辦重點：{focus_hint}")

    # 9) 輸入資料
    if inc: parts.append(f"【來文內容】\n{inc}")
    if att: parts.append(f"【附件內容】\n{att}")
    if ref: parts.append(f"【參考前案】\n{ref}")

    # 10) 需求
    parts.append(f"【撰擬需求】\n{req}")
    parts.append("【請產出完整草稿】")

    return "\n\n".join([p for p in parts if p and str(p).strip()])
