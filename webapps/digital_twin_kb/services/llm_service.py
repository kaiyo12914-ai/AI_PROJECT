import os
from django.conf import settings
from webapps.llm.llm_factory import get_chat_model

NO_DATA_ANSWER = "目前知識庫尚無足夠資料回答此問題。"


def _resolve_model_name(model_type: str) -> str | None:
    """解析並決定要傳給 LLM_FACTORY 的模型名稱，優先讀取子系統專屬設定，其次 Fallback 至專案通用設定"""
    if model_type == "OLLAMA":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OLLAMA_MODEL", None)
        if not model_name:
            model_name = os.getenv("OLLAMA_MODEL", None)
        return model_name
    elif model_type == "OPENAI":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OPENAI_MODEL", None)
        if not model_name:
            model_name = os.getenv("OPENAI_MODEL", None)
        return model_name
    return None


def generate_answer(question: str, context: str) -> str:
    if not context.strip():
        return NO_DATA_ANSWER

    provider = getattr(settings, "DIGITAL_TWIN_KB_LLM_PROVIDER", "ollama").lower()
    if provider in {"", "none", "disabled"}:
        return _fallback_summary(context)

    model_type = provider.upper()  # "OLLAMA" or "OPENAI"
    model_name = _resolve_model_name(model_type)

    try:
        # 使用 llm_factory 獲取統一的 LangChain Chat Model 實例
        llm = get_chat_model(
            model_type=model_type,
            model_name=model_name,
            timeout=120,
        )
        
        prompt = _prompt(question, context)
        response = llm.invoke(prompt)
        
        if hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)
            
        return content.strip() or _fallback_summary(context)
    except Exception:
        return _fallback_summary(context)


def _prompt(question: str, context: str) -> str:
    return f"""請根據下列知識庫內容回答問題，並保留來源依據。

問題：
{question}

知識庫內容：
{context}
"""


def _fallback_summary(context: str) -> str:
    return "未設定可用 LLM，以下為檢索結果摘要：\n" + context[:2000]


def generate_general_answer(question: str) -> str:
    """當知識庫查無資料時，由通用 LLM 提供專業回答"""
    provider = getattr(settings, "DIGITAL_TWIN_KB_LLM_PROVIDER", "ollama").lower()
    if provider in {"", "none", "disabled"}:
        return "目前知識庫尚無足夠資料回答此問題，且未啟用通用 LLM 服務。"

    model_type = provider.upper()  # "OLLAMA" or "OPENAI"
    model_name = _resolve_model_name(model_type)

    try:
        # 使用 llm_factory 獲取統一的 LangChain Chat Model 實例
        llm = get_chat_model(
            model_type=model_type,
            model_name=model_name,
            timeout=120,
        )
        
        prompt = f"請以專業的數位雙生或工業知識助手身分，用繁體中文詳細且具體地回答以下問題：\n\n問題：{question}"
        response = llm.invoke(prompt)
        
        if hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)
            
        ans = content.strip()
        if ans:
            return f"*(💡 提示：本地知識庫查無此關聯文檔，以下由 AI 通用智慧為您解答)*\n\n{ans}"
        return "目前知識庫尚無足夠資料回答此問題。"
    except Exception as e:
        return f"目前知識庫尚無足夠資料回答此問題，且通用 LLM 查詢失敗：{str(e)}"
