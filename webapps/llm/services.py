# webapps/llm/services.py
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

# loader（保留 TextLoader，避免你大改資料來源流程）
from langchain_community.document_loaders import TextLoader

# ✅ NEW (split packages)
from langchain_ollama import OllamaEmbeddings

from webapps.llm.llm_factory import get_chat_model

logger = logging.getLogger(__name__)

# =========================
# Optional Chroma import (NO chromadb -> degrade)
# =========================
try:
    # ✅ NEW (split package)
    from langchain_chroma import Chroma  # requires chromadb installed
    _CHROMA_OK = True
except Exception:
    Chroma = None  # type: ignore
    _CHROMA_OK = False


# =========================
# Safe output: always return str (downstream no need change)
# =========================
def _to_text(x) -> str:
    if x is None:
        return ""
    
    # 優先取得內容主體 (LangChain AI 訊息通常在 .content)
    content = x.content if hasattr(x, "content") else x
    
    import ast
    # 有些新版模型或 Langchain 版本會把多段結構 (list) 直接先轉成 Python字串 "[(...)]"，這會躲過 isinstance(..., list)
    if isinstance(content, str):
        c_stripped = content.strip()
        if c_stripped.startswith("[") and c_stripped.endswith("]"):
            try:
                parsed = ast.literal_eval(c_stripped)
                if isinstance(parsed, list):
                    content = parsed
            except Exception:
                pass
    
    # 1. 處理列表格式 (Gemini 3 / Flash Preview 常回傳結構化內容如 [{'type': 'text', 'text': '...'}] )
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if "text" in part:
                    parts.append(str(part["text"]))
                elif "content" in part:
                    parts.append(str(part["content"]))
                else:
                    parts.append(str(part))
        return "".join(parts)
    
    # 2. 處理字典格式 (fallback)
    if isinstance(content, dict):
        if "content" in content:
            return str(content.get("content") or "")
        if "text" in content:
            return str(content.get("text") or "")
        return str(content)
        
    # 3. 字串或其他類型
    return str(content)



# =========================
# Config helper
# =========================
@dataclass(frozen=True)
class LLMServiceConfig:
    """
    讓 services.py 可以獨立於 Django settings
    - 在 Django 內使用時，通常不需要傳入 config（會自動嘗試讀 settings / env）
    - 在測試或腳本中可自帶 base_dir/ollama_base_url/embed_model 等
    """
    base_dir: Optional[str] = None
    api_context_path: Optional[str] = None

    ollama_base_url: Optional[str] = None
    ollama_embed_model: Optional[str] = None

    chroma_persist_dir: Optional[str] = None
    rag_k: int = 4


def _get_django_settings():
    """避免 services.py 硬依賴 Django；有 Django 才讀 settings。"""
    try:
        from django.conf import settings  # type: ignore
        return settings
    except Exception:
        return None


def _guess_base_dir(config: Optional[LLMServiceConfig]) -> str:
    s = _get_django_settings()
    if config and config.base_dir:
        return config.base_dir
    if s is not None and getattr(s, "BASE_DIR", None):
        return str(s.BASE_DIR)
    return os.getcwd()


def _get_ollama_base_url(config: Optional[LLMServiceConfig]) -> str:
    if config and config.ollama_base_url:
        return config.ollama_base_url

    v = (os.getenv("OLLAMA_BASE_URL") or "").strip()
    if v:
        return v

    s = _get_django_settings()
    if s is not None:
        v2 = (getattr(s, "OLLAMA_BASE_URL", "") or "").strip()
        if v2:
            return v2

    return "http://mpcai.mpc.mil.tw:11434"


def _get_embed_model(config: Optional[LLMServiceConfig]) -> str:
    """
    ⚠️ 建議 .env 設 OLLAMA_EMBED_MODEL 為 embedding 專用模型
    """
    if config and config.ollama_embed_model:
        return config.ollama_embed_model

    v = (os.getenv("OLLAMA_EMBED_MODEL") or "").strip()
    if v:
        return v

    s = _get_django_settings()
    if s is not None:
        v2 = (getattr(s, "OLLAMA_EMBED_MODEL", "") or "").strip()
        if v2:
            return v2
        v3 = (getattr(s, "OLLAMA_MODEL", "") or "").strip()
        if v3:
            return v3

    return "mistral_small_3_1_2503:latest"


def _get_chroma_persist_dir(config: Optional[LLMServiceConfig]) -> str:
    """
    ✅ 支援 env CHROMA_PERSIST_DIR 方便部署
    """
    if config and config.chroma_persist_dir:
        return config.chroma_persist_dir

    v = (os.getenv("CHROMA_PERSIST_DIR") or "").strip()
    if v:
        return v

    base_dir = _guess_base_dir(config)
    return os.path.join(base_dir, "chroma_db")


# =========================
# Prompt builders
# =========================
def build_chat_messages(user_prompt: str):
    return ChatPromptTemplate.from_messages([
        ("system", "你是專業助理，請用繁體中文回答。"),
        ("user", "{prompt}"),
    ]).format_messages(prompt=user_prompt)


def build_rag_messages(context: str, question: str):
    return ChatPromptTemplate.from_messages([
        ("system", "你是專業助理，請依據提供的資料回答；若資料不足請明確說明資料不足。"),
        ("user", "資料如下：\n{context}\n\n問題：{question}")
    ]).format_messages(context=context, question=question)


def build_translate_prompt(text: str, source_lang: str, target_lang: str) -> str:
    return f"""
你是專業翻譯引擎。請嚴格遵守：
1) 只輸出翻譯結果，不要加任何說明、前言、標題、引號。
2) 保留原文格式（換行、項目符號、編號、標點）。
3) 專有名詞若無把握可保留原文或音譯，但不要亂改。
4) 若 source_lang=auto，請自動判斷語言。

source_lang: {source_lang}
target_lang: {target_lang}

待翻譯內容：
{text}
""".strip()


def build_translate_messages(prompt: str):
    return ChatPromptTemplate.from_messages([
        ("system", "你是專業翻譯引擎，請只輸出翻譯結果。"),
        ("user", "{prompt}"),
    ]).format_messages(prompt=prompt)


# =========================
# Context path resolver (avoid 500)
# =========================
def resolve_context_path(config: Optional[LLMServiceConfig] = None) -> Optional[str]:
    """
    Return path if found, else None (degrade gracefully).
    Priority:
      1) config.api_context_path
      2) Django settings.API_CONTEXT_PATH
      3) env API_CONTEXT_PATH
      4) common locations
    """
    if config and config.api_context_path and os.path.exists(config.api_context_path):
        return config.api_context_path

    s = _get_django_settings()
    p = (getattr(s, "API_CONTEXT_PATH", "") if s is not None else "") or ""
    if p and os.path.exists(p):
        return p

    p = os.getenv("API_CONTEXT_PATH", "") or ""
    if p and os.path.exists(p):
        return p

    base_dir = _guess_base_dir(config)
    module_dir = os.path.dirname(__file__)

    candidates = [
        os.path.join(base_dir, "api.txt"),
        os.path.join(base_dir, "api", "api.txt"),
        os.path.join(base_dir, "api", "knowledge", "api.txt"),
        os.path.join(module_dir, "api.txt"),
        os.path.join(module_dir, "knowledge", "api.txt"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


# =========================
# Ensure Chroma has docs
# =========================
def _ensure_chroma_has_docs(
    *,
    vectorstore,
    context_path: str,
    embeddings,
) -> None:
    """
    新版作法：永遠以 persist_directory 開啟 collection。
    若 collection 目前是空的，才建立索引。
    """
    try:
        existing = vectorstore.get(include=[])
        ids = existing.get("ids") or []
        if ids:
            return
    except Exception:
        # 取不到就略過，直接建索引（最多多寫一次）
        pass

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = TextLoader(context_path, encoding="utf-8").load()
    docs = splitter.split_documents(docs)

    if not docs:
        return

    vectorstore.add_documents(docs)
    if hasattr(vectorstore, "persist"):
        try:
            vectorstore.persist()
        except Exception:
            pass


def _open_vectorstore(config: Optional[LLMServiceConfig]):
    """
    Open persisted Chroma collection and ensure it has documents.
    """
    if not _CHROMA_OK:
        raise RuntimeError("chromadb not available")

    context_path = resolve_context_path(config=config)
    if not context_path:
        raise RuntimeError("context file not found")

    base_url = _get_ollama_base_url(config)
    embed_model = _get_embed_model(config)
    embeddings = OllamaEmbeddings(model=embed_model, base_url=base_url)

    persist_dir = _get_chroma_persist_dir(config)
    os.makedirs(persist_dir, exist_ok=True)

    vectorstore = Chroma(
        collection_name="api_context",
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )

    _ensure_chroma_has_docs(
        vectorstore=vectorstore,
        context_path=context_path,
        embeddings=embeddings,
    )

    return vectorstore


# =========================
# ✅ NEW: RAG context only (for doc system)
# =========================
def try_get_rag_context(
    query: str,
    *,
    config: Optional[LLMServiceConfig] = None,
) -> Tuple[Optional[str], str]:
    """
    Retrieve context only (no LLM answering).
    Returns: (context or None, backend_tag)
    """
    if not _CHROMA_OK:
        return None, "no_chromadb"

    try:
        vectorstore = _open_vectorstore(config)
        k = config.rag_k if config else 4
        retriever = vectorstore.as_retriever(search_kwargs={"k": k})
        docs = retriever.get_relevant_documents(query)
        context = "\n\n".join(d.page_content for d in docs).strip()

        if not context:
            return None, "rag_no_hits"

        return context, "rag_chroma_ctx"

    except Exception as e:
        logger.warning("RAG context unavailable. err=%r", e)
        return None, "rag_ctx_error"


# =========================
# RAG answer (optional)
# =========================
def try_get_rag_answer(
    query: str,
    *,
    temperature: float = 0.2,
    timeout: int = 120,
    config: Optional[LLMServiceConfig] = None,
) -> Tuple[Optional[str], str]:
    """
    Try RAG if chromadb + api.txt exist.
    Returns: (answer or None, backend_tag)
    """
    if not _CHROMA_OK:
        return None, "no_chromadb"

    try:
        llm = get_chat_model(temperature=temperature, timeout=timeout)
        vectorstore = _open_vectorstore(config)

        k = config.rag_k if config else 4
        retriever = vectorstore.as_retriever(search_kwargs={"k": k})
        docs = retriever.get_relevant_documents(query)
        context = "\n\n".join(d.page_content for d in docs).strip()

        if not context:
            return None, "rag_no_hits"

        messages = build_rag_messages(context=context, question=query)
        out = llm.invoke(messages)
        answer = _to_text(out).strip()

        return (answer if answer else None), "rag_chroma"

    except Exception as e:
        logger.warning("RAG unavailable, fallback to pure LLM. err=%r", e)
        return None, "rag_error_fallback"


# =========================
# Public service: chat / translate
# =========================
def chat_core(
    prompt: str,
    *,
    temperature: float = 0.2,
    timeout: int = 120,
    enable_rag: bool = True,
    config: Optional[LLMServiceConfig] = None,
) -> Dict[str, Any]:
    """
    用於 views 層呼叫：
      - 若 chromadb + api.txt OK：用 RAG
      - 否則：純 LLM（AUTO fallback）
    回傳格式維持相容：{"reply":..., "backend":...}
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    rag_backend = "rag_disabled"
    if enable_rag:
        rag_answer, rag_backend = try_get_rag_answer(
            prompt, temperature=temperature, timeout=timeout, config=config
        )
        if rag_answer is not None:
            return {"reply": rag_answer, "backend": rag_backend}

    llm = get_chat_model(temperature=temperature, timeout=timeout)
    messages = build_chat_messages(prompt)
    out = llm.invoke(messages)
    reply = _to_text(out)
    return {"reply": reply, "backend": f"auto_llm_fallback({rag_backend})"}


def translate_core(
    text: str,
    *,
    source_lang: str = "auto",
    target_lang: str = "zh-Hant",
    temperature: float = 0.2,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    永遠使用 llm_factory.get_chat_model()（AUTO fallback）
    回傳格式維持相容：{"translated":..., "backend":...}
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")

    source_lang = (source_lang or "auto").strip()
    target_lang = (target_lang or "zh-Hant").strip()

    prompt = build_translate_prompt(text, source_lang, target_lang)
    messages = build_translate_messages(prompt)

    llm = get_chat_model(temperature=temperature, timeout=timeout)
    out = llm.invoke(messages)
    translated = _to_text(out)
    return {"translated": translated, "backend": "auto_llm"}
