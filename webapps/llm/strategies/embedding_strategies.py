from __future__ import annotations

import os

from .base import EmbeddingStrategy, EmbeddingStrategyDeps


class GoogleEmbeddingStrategy(EmbeddingStrategy):
    def __init__(self, deps: EmbeddingStrategyDeps) -> None:
        self._deps = deps

    def build(self):
        import importlib.util

        if importlib.util.find_spec("langchain_google_genai") is None:
            fallback = self._deps.resolve_provider_fallback("GOOGLE")
            self._deps.logger.warning("[LLM] GOOGLE embedding provider missing; fallback=%s", fallback)
            if fallback in {"LM_STUDIO", "OLLAMA"}:
                return OllamaEmbeddingStrategy().build()
            if fallback == "OPENAI":
                return OpenAIEmbeddingStrategy().build()

        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Google Gemini embeddings.")
        model = os.getenv("GLOBAL_GOOGLE_EMBEDDING_MODEL", "models/text-embedding-004")
        return GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key)


class OpenAIEmbeddingStrategy(EmbeddingStrategy):
    def build(self):
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
        model = os.getenv("GLOBAL_OPENAI_EMBEDDING_MODEL") or os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIEmbeddings(model=model, api_key=api_key)


class OllamaEmbeddingStrategy(EmbeddingStrategy):
    def build(self):
        try:
            from langchain_ollama import OllamaEmbeddings
        except ImportError:
            from langchain_community.embeddings import OllamaEmbeddings
        base_url = os.getenv("GLOBAL_OLLAMA_EMBEDDING_BASE_URL") or os.getenv("OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434")
        model = os.getenv("GLOBAL_OLLAMA_EMBEDDING_MODEL") or os.getenv("OLLAMA_EMBEDDING_MODEL", "snowflake-arctic-embed2")
        return OllamaEmbeddings(model=model, base_url=base_url)
