from django.conf import settings
from webapps.llm.llm_factory import get_chat_model

NO_DATA_ANSWER = "目前知識庫尚無足夠資料回答此問題。"


def generate_answer(question: str, context: str) -> str:
    if not context.strip():
        return NO_DATA_ANSWER

    provider = getattr(settings, "DIGITAL_TWIN_KB_LLM_PROVIDER", "ollama").lower()
    if provider in {"", "none", "disabled"}:
        return _fallback_summary(context)

    model_type = provider.upper()  # "OLLAMA" or "OPENAI"
    if model_type == "OLLAMA":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OLLAMA_MODEL", "mistral")
    elif model_type == "OPENAI":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OPENAI_MODEL", getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"))
    else:
        model_name = None

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
