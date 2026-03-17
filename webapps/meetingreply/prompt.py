# webapps/meetingreply/prompt.py
from __future__ import annotations

import os


def build_meeting_reply_prompt(directive: str, injection: str, mode: str = "short") -> str:
    """
    根據模式產生成會議擬答提示詞。
    mode: "short" (簡要版) or "long" (詳答版)
    """
    if mode == "long":
        return _build_prompt_long(directive, injection)
    return _build_prompt_short(directive, injection)


def _build_prompt_short(directive: str, injection: str) -> str:
    return f"""
你是機關幕僚助理，請依下列資訊，產生一份正式、可呈報的「會議彙辦事項擬答（簡要版）」。
請使用繁體中文，語氣正式。

【一、指裁示事項】
{directive if directive else "（未提供）"}

【二、參考注入資訊（參謀想法 + RAG）】
{injection if injection else "（無）"}

要求：
- 200個繁體中文字以內（含標點）
- 直接輸出擬答內容，不要輸出提示詞
- 單一段落輸出（不可使用條列、編號、換行）
- 語氣正式、可呈報
- 直接輸出內容，無需重複描述指裁示事項（不要加任何標題/前綴/說明）
""".strip()


def _build_prompt_long(directive: str, injection: str) -> str:
    return f"""
你是機關幕僚助理，請依下列資訊，產生一份正式、可呈報的「會議彙辦事項擬答（詳答版）」。
請使用繁體中文，語氣正式。

【一、指裁示事項】
{directive if directive else "（未提供）"}

【二、參考注入資訊（參謀想法 + RAG）】
{injection if injection else "（無）"}

要求：
- 400個繁體中文字以內（含標點）
- 直接輸出擬答內容，不要輸出提示詞
- 語氣正式、可呈報
- 分段時請換行並標註一、二、...
- 直接輸出內容，無需重複描述指裁示事項（不要加任何標題/前綴/說明）
""".strip()
