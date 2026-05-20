from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List

from langchain_core.prompts import ChatPromptTemplate

from webapps.llm.llm_factory import get_chat_model

logger = logging.getLogger(__name__)


def _to_text(x: Any) -> str:
    if x is None:
        return ""
    if hasattr(x, "content"):
        try:
            return str(getattr(x, "content") or "").strip()
        except Exception:
            return str(x).strip()
    return str(x).strip()


@dataclass(frozen=True)
class LLMServiceConfig:
    base_dir: Optional[str] = None
    api_context_path: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_embed_model: Optional[str] = None
    rag_k: int = 4


def _target_is_traditional_chinese(target_lang: str) -> bool:
    t = (target_lang or "").strip().lower()
    return t in {"zh-tw", "zh_hant", "zh-hant", "traditional chinese", "繁體中文", "繁中"}


def _has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", s or ""))


def _looks_like_english_only(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) > 80:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9\s.,:;!?'\-_/()]+", s))


def _local_translate_fallback(text: str, target_lang: str) -> str:
    if not _target_is_traditional_chinese(target_lang):
        return text

    word_map = {
        "test": "測試",
        "ok": "可以",
        "hello": "你好",
        "thanks": "謝謝",
        "thank": "感謝",
        "you": "你",
        "yes": "是",
        "no": "否",
        "please": "請",
    }

    def repl(m: re.Match[str]) -> str:
        w = m.group(0)
        return word_map.get(w.lower(), w)

    return re.sub(r"[A-Za-z]+", repl, text)


def build_chat_messages(user_prompt: str):
    return ChatPromptTemplate.from_messages([
        ("system", "你是機關幕僚助理，請以正式、精簡且可執行的方式回答。"),
        ("user", "{prompt}"),
    ]).format_messages(prompt=user_prompt)


def build_rag_messages(context: str, question: str):
    return ChatPromptTemplate.from_messages([
        ("system", "你是機關幕僚助理，請根據提供的參考資料回答；若資料不足請明確說明。"),
        ("user", "參考資料：\n{context}\n\n問題：{question}"),
    ]).format_messages(context=context, question=question)


def build_translate_prompt(text: str, source_lang: str, target_lang: str) -> str:
    return f"""
你是專業翻譯助理。
請將以下內容由 {source_lang} 翻成 {target_lang}。
只輸出翻譯結果，不要加說明。

{text}
""".strip()


def build_translate_messages(prompt: str):
    return ChatPromptTemplate.from_messages([
        ("system", "你是專業翻譯助理。"),
        ("user", "{prompt}"),
    ]).format_messages(prompt=prompt)


def _build_context_from_sources(sources: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for i, s in enumerate(sources[:8], start=1):
        title = str(s.get("title") or "").strip()
        snippet = str(s.get("snippet") or "").strip()
        header = f"[{i}] {title}" if title else f"[{i}]"
        blocks.append(header + ("\n" + snippet if snippet else ""))
    return "\n\n".join(blocks).strip()


def try_get_rag_context(query: str, *, config: Optional[LLMServiceConfig] = None) -> Tuple[Optional[str], str]:
    try:
        from webapps.rag_oracle.retrieve import rag_search
        k = int(config.rag_k) if config else 4
        out = rag_search(query, k=k)
        if not bool(out.get("ok", False)):
            return None, "rag_postgres_error"
        sources = out.get("sources") or []
        if not isinstance(sources, list) or not sources:
            return None, "rag_postgres_no_hits"
        context = _build_context_from_sources([x for x in sources if isinstance(x, dict)])
        return (context if context else None), "rag_postgres_ctx"
    except Exception as e:
        logger.warning("RAG context unavailable. err=%r", e)
        return None, "rag_postgres_exception"


def try_get_rag_answer(
    query: str,
    *,
    temperature: float = 0.2,
    timeout: int = 120,
    config: Optional[LLMServiceConfig] = None,
) -> Tuple[Optional[str], str]:
    context, tag = try_get_rag_context(query, config=config)
    if not context:
        return None, tag
    try:
        llm = get_chat_model(temperature=temperature, timeout=timeout)
        messages = build_rag_messages(context=context, question=query)
        out = llm.invoke(messages)
        answer = _to_text(out).strip()
        return (answer if answer else None), "rag_postgres"
    except Exception as e:
        logger.warning("RAG answer unavailable. err=%r", e)
        return None, "rag_postgres_llm_error"


def chat_core(
    prompt: str,
    *,
    temperature: float = 0.2,
    timeout: int = 120,
    enable_rag: bool = True,
    config: Optional[LLMServiceConfig] = None,
) -> Dict[str, Any]:
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
    return {"reply": _to_text(out), "backend": f"auto_llm_fallback({rag_backend})"}


def translate_core(
    text: str,
    *,
    source_lang: str = "auto",
    target_lang: str = "zh-Hant",
    temperature: float = 0.2,
    timeout: int = 120,
) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")

    source_lang = (source_lang or "auto").strip()
    target_lang = (target_lang or "zh-Hant").strip()

    prompt = build_translate_prompt(text, source_lang, target_lang)
    messages = build_translate_messages(prompt)

    try:
        llm = get_chat_model(temperature=temperature, timeout=timeout)
        out = llm.invoke(messages)
        translated = _to_text(out).strip()

        if (
            _target_is_traditional_chinese(target_lang)
            and translated
            and translated == text
            and _looks_like_english_only(text)
            and not _has_cjk(translated)
        ):
            retry_prompt = f"請將下列英文內容翻譯為繁體中文，只輸出翻譯結果：\n\n{text}"
            retry_out = llm.invoke(build_translate_messages(retry_prompt))
            retry_translated = _to_text(retry_out).strip()
            if retry_translated:
                translated = retry_translated

        return {"translated": translated, "backend": "auto_llm", "fallback": False}
    except Exception as e:
        return {
            "translated": _local_translate_fallback(text, target_lang),
            "backend": "local_rule_fallback",
            "fallback": True,
            "llmError": str(e)[:300],
        }
