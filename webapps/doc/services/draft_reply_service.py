# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple, Any

from webapps.llm.llm_factory import get_chat_model

ALLOWED_LEVELS = ("FROM_SUPERIOR", "FROM_PEER", "FROM_SUBORDINATE")

LEVEL_RELATIONSHIP = {
    "FROM_SUPERIOR": "對方為上級單位，本單位為下級回覆方（回報／說明式）。",
    "FROM_PEER": "對方為平行單位，雙方無指揮關係（協調／會辦式）。",
    "FROM_SUBORDINATE": "對方為下級單位，本單位為上級回覆方（指導／要求式）。",
}


@dataclass(frozen=True)
class ToneRule:
    level: str
    label: str
    tone: List[str]
    forbidden_phrases: List[str]
    preferred_openers: List[str]
    preferred_phrases: List[str]
    required_sections: List[str]


@lru_cache(maxsize=1)
def load_tone_rules_json() -> Dict[str, Any]:
    rules_path = Path(__file__).resolve().parents[1] / "rules" / "draft_tone_rules.json"
    if not rules_path.exists():
        legacy = Path(__file__).parent / "rules" / "draft_tone_rules.json"
        if legacy.exists():
            rules_path = legacy
        else:
            raise FileNotFoundError(f"draft_tone_rules.json not found: {rules_path}")
    return json.loads(rules_path.read_text(encoding="utf-8"))


def load_tone_rules() -> Dict[str, ToneRule]:
    data = load_tone_rules_json()
    levels = data.get("levels", {})
    out: Dict[str, ToneRule] = {}
    for level, cfg in levels.items():
        out[level] = ToneRule(
            level=level,
            label=cfg.get("label", level),
            tone=cfg.get("tone", []),
            forbidden_phrases=cfg.get("forbidden_phrases", []),
            preferred_openers=cfg.get("preferred_openers", []),
            preferred_phrases=cfg.get("preferred_phrases", []),
            required_sections=cfg.get("required_sections", []),
        )
    return out


def _resolve_writer_identity(login_user_name: str) -> str:
    """
    根據登入者姓名/前綴判斷簽文者單位：
    - 含 MPC -> 自稱「本中心」
    - 含 202/205/209/401 -> 自稱「本廠」
    """
    name = (login_user_name or "").upper().strip()
    if "MPC" in name:
        return "本中心"
    if any(f in name for f in ["202", "205", "209", "401"]):
        return "本廠"
    # 保底
    return "本單位"


def build_llm_instructions(rule: ToneRule, self_refer: str, doc_meta: Dict[str, str]) -> str:
    data = load_tone_rules_json()
    internal = data.get("internal_review", {})
    
    relation = LEVEL_RELATIONSHIP.get(rule.level, "")
    
    # 擷取解析階段產出的固定引述句
    fixed_quote = doc_meta.get("fixed_quote") or ""
    
    internal_tone = "\n".join([f"- {x}" for x in internal.get("tone", [])])
    internal_phrases = "\n".join([f"- {x}" for x in internal.get("preferred_phrases", [])])
    internal_structure = "\n".join([f"- {x}" for x in internal.get("structure", [])])

    quote_instruction = ""
    if fixed_quote:
        quote_instruction = f"4. **說明第一點：必須 100% 引用以下語彙：**\n   「{fixed_quote}」"
    else:
        # 建立備援引述來文範例
        ref_org = doc_meta.get("from_org") or "○○單位"
        ref_date = doc_meta.get("doc_date") or "民國114年○月○日"
        ref_no = doc_meta.get("doc_no") or "○○字第114○○○○○○號"
        quote_instruction = f"4. 說明第一點：必須引述來文依據。參考格式：依{ref_org}{ref_date}{ref_no}函辦理。"

    return f"""
【第一部分：來文背景解析（供參考）】
- 對方層級：{rule.level}（{rule.label}）
- 單位關係：{relation}

【第二部分：內部擬辦核心規範（必須遵守）】
- ✅ 身分自稱：文稿中提及我方單位時，必須統一使用「{self_refer}」。
- ❗ 稱謂轉換規則：當引述或提及對方時，必須將來文中的「本局、本部、本廠」等自稱轉換為具名單位（例如：軍備局、205廠）。嚴禁稱呼對方為「本局」。
{internal_tone}

【第三部分：簽呈結構與用語】
{internal_structure}
{internal_phrases}

【擬稿重點 (Crucial)】
1. 這是「簽呈」，核稿對象是內部主管，內容務必精簡。
2. 主旨：必須是「辦理事項 + 請求核示」，嚴禁出現任何文號。
3. 稱謂角色轉換：**絕對禁止** 沿用來文中的「本局」、「本部」、「本廠」等自稱。
   - 由於來文已透過「重點解析後置洗稿程序」預先轉換為具名單位（如：軍備局、205廠），請直接沿用該具名名稱。
   - 始終站在「{self_refer}」承辦人的角色，向主管提出擬辦建議。
{quote_instruction}
5. 說明二至三：精簡扼要，嚴禁冗長敘事與無意義鋪陳，每段 2-3 句為限。
6. 擬辦：必須提出 1-2 點具體可執行的方案。
7. 視角：始終站在「{self_refer}」的角度向主管回報。
""".strip()


def _preprocess_incoming_text(text: str, from_org: str, self_refer: str) -> str:
    """
    送 LLM 前的前置處理：專門解決「視角翻轉」問題。
    將來文中的「本局/本廠」自稱轉換為具名單位，
    將來文中的「貴中心/貴單位」尊稱轉換為我方自稱（如：本中心）。
    """
    if not text:
        return ""
    
    out = text
    
    # 1. 處理對方的自稱 (若來文單位包含軍備局，則本局->軍備局)
    # 這裡採廣義替換，只要 from_org 有特定關鍵字
    target_name = from_org or "對方單位"
    
    # 常見自稱替換清單
    self_aliases = ["本局", "本部", "本廠", "本處", "本中心", "本室", "本所", "本會", "本組"]
    for alias in self_aliases:
        # 避免誤殺：只有當 alias 不等於 self_refer 時才替換
        if alias != self_refer:
            out = out.replace(alias, target_name)
    
    # 2. 處理對方的尊稱 (貴中心/貴單位 -> 我方自稱)
    honorifics = ["貴中心", "貴單位", "貴廠", "貴處", "貴局", "貴部", "貴所", "貴會", "貴組"]
    for hon in honorifics:
        out = out.replace(hon, self_refer)
        
    return out


def draft_reply(
    doc_id: str,
    from_level: str,
    instruction: str,
    *,
    doc_meta: Dict[str, object] | None = None,
    doc_text: str = "",
    context: str = "",
    login_user_name: str = "",
) -> Dict[str, object]:
    doc_meta = _normalize_doc_meta(doc_meta)
    doc_text = _safe_str(doc_text).strip()
    context = _safe_str(context).strip()

    # ✅ 核心精進：自動從 context (通常包含附件重點) 提取固定引述句
    if "fixed_quote" not in doc_meta:
        m_quote = re.search(r"【擬稿說明第一點固定引述】[:：]\s*(.+?)(?:\r?\n|$)", context)
        if m_quote:
            doc_meta["fixed_quote"] = m_quote.group(1).strip()

    from_org = _safe_str(doc_meta.get("from_org")).strip()
    from_level = resolve_from_level(_safe_str(from_level).strip(), from_org)

    # ✅ 判斷自稱：本中心 vs 本廠
    self_refer = _resolve_writer_identity(login_user_name)

    # ✅ 【新功能】送 LLM 前的前置轉換：視角校正
    # 將原始來文與背景資訊中的「本局/貴中心」翻轉為「軍備局/本中心」
    doc_text = _preprocess_incoming_text(doc_text, from_org, self_refer)
    context = _preprocess_incoming_text(context, from_org, self_refer)

    rules = load_tone_rules()
    rule = rules[from_level]

    llm = get_chat_model()

    system = (
        "你是政府機關資深公文秘書，專精於撰寫高品質「內部簽呈」。"
        f"你目前的簽文角色是「{self_refer}」的承辦人。"
        "你的目標是：將已經過「後置洗稿」預處理的來文內容，轉化為對內簡明、客觀且具備具體建議的簽報。"
        f"核心角色要求：1. 始終代表「{self_refer}」。2. 主旨嚴禁出現文號。3. 稱謂必須具名，嚴禁稱呼對方為本局/貴中心。"
    )

    tone_instructions = build_llm_instructions(rule, self_refer, doc_meta)

    user_prompt = f"""
請根據以下資訊，擬定一份正式的「內部簽呈」草稿。

【使用者特別指示】
{instruction}

【來文檔案摘要】
- 來源單位：{doc_meta.get("from_org", "")}
- 原始主旨：{doc_meta.get("subject", "")}
- 原始日期：{doc_meta.get("doc_date", "")}
- 原始文號：{doc_meta.get("doc_no", "")}

【來文本文內容】
{doc_text}

【我方執行背景與關聯資訊】
{context}

---
【擬稿規範指導】
{tone_instructions}
""".strip()

    resp = llm.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
    )

    draft_text = resp.content if hasattr(resp, "content") else str(resp)

    # 簡單清理與檢查
    missing_sections = []
    for sec in rule.required_sections:
        if sec not in draft_text:
            missing_sections.append(sec)

    return {
        "ok": True,
        "doc_id": doc_id,
        "from_level": from_level,
        "rule_label": rule.label,
        "self_refer": self_refer, # 回報自稱類別
        "draft": draft_text,
        "warnings": [{"type": "missing_sections", "items": missing_sections}] if missing_sections else []
    }


def _normalize_doc_meta(doc_meta: Dict[str, object] | None) -> Dict[str, str]:
    base = {"from_org": "", "subject": "", "doc_date": "", "doc_no": ""}
    if not isinstance(doc_meta, dict):
        return base
    for k in list(base.keys()):
        if k in doc_meta:
            base[k] = str(doc_meta.get(k) or "").strip()
    return base


def _safe_str(x: object) -> str:
    return "" if x is None else str(x)


@lru_cache(maxsize=1)
def load_org_level_map() -> Dict[str, object]:
    rules_path = Path(__file__).resolve().parents[1] / "rules" / "org_level_map.json"
    if not rules_path.exists():
        legacy = Path(__file__).parent / "rules" / "org_level_map.json"
        if legacy.exists():
            rules_path = legacy
        else:
            raise FileNotFoundError(f"org_level_map.json not found: {rules_path}")
    return json.loads(rules_path.read_text(encoding="utf-8"))


def _normalize_org_text(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    t = re.sub(r"[\s　]+", "", t)
    t = re.sub(r"[，,。．、;；:：()（）\\[\\]【】<>《》\"'“”‘’·]+", "", t)
    return t


def _infer_level_from_org(from_org: str) -> str:
    data = load_org_level_map()
    mapping = data.get("mapping", [])
    org_norm = _normalize_org_text(from_org)
    if not org_norm:
        return ""
    for item in mapping:
        pattern = str(item.get("pattern", "")).strip()
        level = str(item.get("level", "")).strip()
        pat_norm = _normalize_org_text(pattern)
        if pat_norm and pat_norm in org_norm:
            return level
    return ""


def resolve_from_level(from_level: str, from_org: str) -> str:
    if from_level in ALLOWED_LEVELS:
        return from_level
    inferred = _infer_level_from_org(from_org)
    if inferred:
        return inferred
    raise ValueError("無法判定來文層級")
