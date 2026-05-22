from django.conf import settings
from webapps.llm.llm_factory import get_chat_model

NO_DATA_ANSWER = "目前知識庫尚無足夠資料回答此問題。"


def generate_answer(question: str, context: str) -> str:
    if not context.strip():
        return NO_DATA_ANSWER

    # 優先使用數位雙生子系統專屬的 PROVIDER 設定，否則自動 Fallback 至專案全局 settings.MODEL_TYPE
    provider = getattr(settings, "DIGITAL_TWIN_KB_LLM_PROVIDER", None)
    if not provider or not provider.strip():
        provider = getattr(settings, "MODEL_TYPE", "OLLAMA")

    if provider.lower() in {"none", "disabled"}:
        return _fallback_summary(context)

    model_type = provider.upper()
    
    # 僅讀取 settings 中子系統專屬的模型名稱，其餘 Fallback 與環境變數讀取一律交給 LLM_FACTORY 內部統一決定
    model_name = None
    if model_type == "OLLAMA":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OLLAMA_MODEL", None)
    elif model_type == "OPENAI":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OPENAI_MODEL", None)

    # 若 settings 載入的模型名稱為空字串，則視為未指定，以讓 LLM_FACTORY 底層進行全局模型 Fallback
    if not model_name or not model_name.strip():
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


def generate_general_answer(question: str) -> str:
    """當知識庫查無資料時，由通用 LLM 提供專業回答"""
    provider = getattr(settings, "DIGITAL_TWIN_KB_LLM_PROVIDER", None)
    if not provider or not provider.strip():
        provider = getattr(settings, "MODEL_TYPE", "OLLAMA")

    if provider.lower() in {"none", "disabled"}:
        return "目前知識庫尚無足夠資料回答此問題，且未啟用通用 LLM 服務。"

    model_type = provider.upper()

    # 僅讀取 settings 中子系統專屬的模型名稱，其餘 Fallback 與環境變數讀取一律交給 LLM_FACTORY 內部統一決定
    model_name = None
    if model_type == "OLLAMA":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OLLAMA_MODEL", None)
    elif model_type == "OPENAI":
        model_name = getattr(settings, "DIGITAL_TWIN_KB_OPENAI_MODEL", None)

    # 若 settings 載入的模型名稱為空字串，則視為未指定，以讓 LLM_FACTORY 底層進行全局模型 Fallback
    if not model_name or not model_name.strip():
        model_name = None

    try:
        # 使用 llm_factory 獲取統一的 LangChain Chat Model 實例
        llm = get_chat_model(
            model_type=model_type,
            model_name=model_name,
            timeout=120,
        )
        
        prompt = f"""您是一位極其專業且知識淵博的「工業4.0、數位孿生、智慧製造、真實物理模擬與系統架構」頂級專家。
請針對以下問題，撰寫一篇【結構嚴謹、內容詳實、具有高度知識含金量、可以直接作為專業維基知識庫建檔】的繁體中文詳細解答。

問題：{question}

為確保本篇回答未來自動存入知識庫後具備極高的參考與檢索價值，請務必遵循以下撰寫規範：
1. 【定義與概述】：清晰且專業地定義該技術、平台、標準或名詞的核心概念與背景脈絡。
2. 【核心技術架構/主要特色】：分點詳細且具體地說明其關鍵技術指標、運作原理、主要優勢或平台特性。
3. 【應用範疇與實務場景】：具體列舉其在智慧製造、數位孿生、工業模擬或其他相關領域的典型實務應用場景與實務效益。
4. 【產業影響或未來趨勢】：簡述其對相關產業的變革性影響，或未來的技術發展動向。
5. 【內容長度與細緻度】：請勿給出敷衍、短小或過於簡略的答覆。請盡可能充實每個章節的論述深度與細節（字數建議在 800 至 1500 字之間，條理清晰、層次分明）。
"""
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
        return f"currently unavailable: {str(e)}"
