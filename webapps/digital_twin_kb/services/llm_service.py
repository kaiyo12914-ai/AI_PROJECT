from django.conf import settings

from webapps.llm.llm_factory import get_chat_model

NO_DATA_ANSWER = "目前無可用的檢索內容，請提供更具體問題或先匯入知識文件。"


def _resolve_provider() -> str:
    provider = getattr(settings, "DIGITAL_TWIN_KB_LLM_PROVIDER", None)
    if not provider or not str(provider).strip():
        provider = getattr(settings, "MODEL_TYPE", "LM_STUDIO")
    return str(provider).strip().upper()


def _resolve_model_name(model_type: str) -> str | None:
    if model_type == "OPENAI":
        m = getattr(settings, "DIGITAL_TWIN_KB_OPENAI_MODEL", None)
        return m.strip() if isinstance(m, str) and m.strip() else None
    return None


def generate_answer(question: str, context: str, history_block: str = "") -> str:
    if not context.strip():
        return NO_DATA_ANSWER

    model_type = _resolve_provider()
    if model_type.lower() in {"none", "disabled"}:
        return _fallback_summary(context)

    model_name = _resolve_model_name(model_type)
    try:
        llm = get_chat_model(
            model_type=model_type,
            model_name=model_name,
            timeout=120,
        )
        prompt = _prompt(question, context, history_block=history_block)
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return content.strip() or _fallback_summary(context)
    except Exception:
        return _fallback_summary(context)


def generate_general_answer(question: str, history_block: str = "") -> str:
    model_type = _resolve_provider()
    if model_type.lower() in {"none", "disabled"}:
        return "目前未設定可用 LLM。"

    model_name = _resolve_model_name(model_type)
    try:
        llm = get_chat_model(
            model_type=model_type,
            model_name=model_name,
            timeout=120,
        )
        prompt = (
            "你是數位孿生知識助理。若無檢索內容，請根據一般產業知識提供保守且可執行的建議，"
            "避免捏造具體法規、內部制度或未提供的數據。\n\n"
            f"使用者問題：{question}\n\n"
            f"歷史對話摘要與近期輪次：\n{history_block or '(none)'}\n"
        )
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        ans = content.strip()
        return ans or "目前無法產生答案，請稍後再試。"
    except Exception as exc:
        return f"currently unavailable: {exc}"


def _prompt(question: str, context: str, history_block: str = "") -> str:
    return (
        "你是數位孿生知識助理。請僅根據提供的檢索內容與歷史脈絡回答，"
        "避免杜撰來源。若資訊不足，請明確指出缺口。\n\n"
        f"使用者問題：\n{question}\n\n"
        f"歷史對話摘要與近期輪次：\n{history_block or '(none)'}\n\n"
        f"檢索內容：\n{context}\n"
    )


def _fallback_summary(context: str) -> str:
    return "目前 LLM 暫不可用，先提供檢索摘要：\n" + context[:2000]
