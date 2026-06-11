from __future__ import annotations

import os

from django.conf import settings


def _normalize_provider(provider: str | None) -> str:
    value = str(provider or "").strip().upper()
    if value == "LM_STUDIO":
        return "OLLAMA"
    if value in {"GOOGLE", "OLLAMA", "OPENAI"}:
        return value
    return "OLLAMA"


def expected_embedding_dimension() -> int:
    return int(getattr(settings, "GLOBAL_EMBEDDING_DIMENSION", 1024) or 1024)


def get_shared_embedding_provider() -> str:
    return _normalize_provider(getattr(settings, "GLOBAL_EMBEDDING_PROVIDER", "OLLAMA"))


def get_shared_embedding_model_name() -> str:
    provider = get_shared_embedding_provider()
    if provider == "GOOGLE":
        return str(
            getattr(
                settings,
                "GLOBAL_GOOGLE_EMBEDDING_MODEL",
                getattr(settings, "GLOBAL_EMBEDDING_MODEL", "models/text-embedding-004"),
            )
            or "models/text-embedding-004"
        )
    if provider == "OPENAI":
        return str(
            getattr(
                settings,
                "GLOBAL_OPENAI_EMBEDDING_MODEL",
                getattr(settings, "GLOBAL_EMBEDDING_MODEL", "text-embedding-3-small"),
            )
            or "text-embedding-3-small"
        )
    return str(
        getattr(
            settings,
            "GLOBAL_OLLAMA_EMBEDDING_MODEL",
            getattr(settings, "GLOBAL_EMBEDDING_MODEL", "snowflake-arctic-embed2"),
        )
        or "snowflake-arctic-embed2"
    )


def get_shared_embedding_base_url() -> str:
    return str(
        getattr(
            settings,
            "GLOBAL_OLLAMA_EMBEDDING_BASE_URL",
            getattr(settings, "OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434"),
        )
        or "http://mpcai.mpc.mil.tw:11434"
    )


def _build_google_embeddings(*, model_name: str):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Google Gemini embeddings.")
    return GoogleGenerativeAIEmbeddings(model=model_name, google_api_key=api_key)


def _build_openai_embeddings(*, model_name: str):
    from langchain_openai import OpenAIEmbeddings

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings.")
    return OpenAIEmbeddings(model=model_name, api_key=api_key)


def _build_ollama_embeddings(*, model_name: str, base_url: str):
    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        from langchain_community.embeddings import OllamaEmbeddings

    return OllamaEmbeddings(model=model_name, base_url=base_url)


def get_shared_embedding_model():
    provider = get_shared_embedding_provider()
    model_name = get_shared_embedding_model_name()

    if provider == "GOOGLE":
        return _build_google_embeddings(model_name=model_name)
    if provider == "OPENAI":
        return _build_openai_embeddings(model_name=model_name)
    return _build_ollama_embeddings(
        model_name=model_name,
        base_url=get_shared_embedding_base_url(),
    )


# Backward-compatible aliases for legacy NL2SQL callers.
get_nl2sql_embedding_provider = get_shared_embedding_provider
get_nl2sql_embedding_model = get_shared_embedding_model
