# llm_client.py
from __future__ import annotations
from typing import List, Optional, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

from webapps.llm.llm_factory import get_chat_model

DEFAULT_SYSTEM = "你是嚴謹的助理，請使用繁體中文回答。"

def chat(prompt: str, system: str = DEFAULT_SYSTEM) -> str:
    """最簡單：給 prompt + system，回傳文字結果（LangChain invoke）。"""
    llm = get_chat_model()
    resp = llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ])
    return getattr(resp, "content", str(resp))

def chat_messages(messages: List[BaseMessage]) -> str:
    """進階：你自己組 messages（LangChain invoke）。"""
    llm = get_chat_model()
    resp = llm.invoke(messages)
    return getattr(resp, "content", str(resp))

def _build_prompt(task: str, text: str) -> str:
    t = (task or "").strip().lower()

    if t == "summary":
        return f"請將以下逐字稿整理成條列重點（最多 12 點），並在最後給一段 3 行內結論：\n\n{text}"

    if t == "polish":
        return f"請將以下文字做校稿潤飾，修正錯字、斷句與口語贅字，但保留原意與專有名詞：\n\n{text}"

    if t == "minutes":
        return (
            "請根據以下逐字稿產出會議記錄，格式包含：\n"
            "1) 會議主題（若未知請推測）\n"
            "2) 討論重點\n"
            "3) 決議事項\n"
            "4) 待辦清單（項目/負責人/期限；負責人與期限若未知請留空）\n\n"
            f"逐字稿：\n{text}"
        )

    if t == "qa":
        return f"請根據以下內容產生 5 題 Q&A（每題含問題與答案），問題要能檢核是否真的看懂內容：\n\n{text}"

    # 預設：不做 task 包裝
    return text

def structured_chat(task: str, text: str, system: str = DEFAULT_SYSTEM) -> str:
    """配合前端：task + text -> prompt -> LangChain invoke。"""
    prompt = _build_prompt(task, text)
    return chat(prompt=prompt, system=system)
