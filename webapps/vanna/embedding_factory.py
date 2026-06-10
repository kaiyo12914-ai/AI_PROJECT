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
    return int(getattr(settings, "NL2SQL_EMBEDDING_DIMENSION", 1024) or 1024)


def get_nl2sql_embedding_provider() -> str:
    return _normalize_provider(getattr(settings, "NL2SQL_EMBEDDING_PROVIDER", "OLLAMA"))


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


def get_nl2sql_embedding_model():
    provider = get_nl2sql_embedding_provider()

    if provider == "GOOGLE":
        model_name = str(
            getattr(
                settings,
                "NL2SQL_GOOGLE_EMBEDDING_MODEL",
                getattr(settings, "NL2SQL_EMBEDDING_MODEL", "models/text-embedding-004"),
            )
            or "models/text-embedding-004"
        )
        return _build_google_embeddings(model_name=model_name)

    if provider == "OPENAI":
        model_name = str(
            getattr(
                settings,
                "NL2SQL_OPENAI_EMBEDDING_MODEL",
                getattr(settings, "NL2SQL_EMBEDDING_MODEL", "text-embedding-3-small"),
            )
            or "text-embedding-3-small"
        )
        return _build_openai_embeddings(model_name=model_name)

    model_name = str(
        getattr(
            settings,
            "NL2SQL_OLLAMA_EMBEDDING_MODEL",
            getattr(settings, "NL2SQL_EMBEDDING_MODEL", "snowflake-arctic-embed2"),
        )
        or "snowflake-arctic-embed2"
    )
    base_url = str(
        getattr(
            settings,
            "NL2SQL_OLLAMA_BASE_URL",
            getattr(settings, "OLLAMA_BASE_URL", "http://mpcai.mpc.mil.tw:11434"),
        )
        or "http://mpcai.mpc.mil.tw:11434"
    )
    return _build_ollama_embeddings(model_name=model_name, base_url=base_url)
